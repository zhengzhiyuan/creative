import os
import time
import re
import argparse
import pandas as pd
import whisper
import requests
from moviepy import VideoFileClip
from tqdm import tqdm
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")

# --- 1. 配置加载 ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROXY_URL = os.getenv("HTTPS_PROXY")

# --- 2. 初始化 Whisper (使用 small 模型) ---
print("🤖 正在载入 Whisper (small) 引擎，请稍候...")
whisper_model = whisper.load_model("small")


# --- 3. 工具函数 ---

def get_gemini_copywriting_via_api(transcript, retry_count=0):
    """
    使用 v1 正式版接口，确保模型兼容性
    """
    # 修改点：v1beta -> v1
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    headers = {'Content-Type': 'application/json'}

    prompt = (
        f"角色：资深香港娱乐主编。要求：极致标题党、毒舌吐槽、港式口语、极致网感。\n"
        f"任务：根据旁白创作 YouTube 营销文案。\n"
        f"内容：{transcript}\n"
        f"输出格式：\nTITLE: [劲爆标题]\nDESC: [吸引人的描述]\nTAGS: [标签]"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

    try:
        response = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=30)
        res_json = response.json()

        if response.status_code == 429:
            # 频率限制处理
            wait_time = 15
            print(f"\n⏳ 频率限制，等待 {wait_time}s 重试...")
            time.sleep(wait_time)
            return get_gemini_copywriting_via_api(transcript, retry_count + 1) if retry_count < 3 else None

        if 'candidates' in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text']
        else:
            # 如果 v1 还是不行，尝试 v1beta (双重保险)
            if "not found" in str(res_json).lower() and "v1" in url:
                print("🔄 v1 路径未找到，尝试切换 v1beta 路径...")
                backup_url = url.replace("/v1/", "/v1beta/")
                response = requests.post(backup_url, json=payload, headers=headers, proxies=proxies, timeout=30)
                res_json = response.json()
                if 'candidates' in res_json:
                    return res_json['candidates'][0]['content']['parts'][0]['text']

            print(f"\n⚠️ API 依旧返回异常: {res_json}")
            return None

    except Exception as e:
        print(f"\n⚠️ 网络连接失败: {e}")
        return None


def parse_output(text):
    """解析 AI 输出"""
    t = re.search(r"TITLE:\s*(.*)", text, re.IGNORECASE)
    d = re.search(r"DESC:\s*(.*)", text, re.IGNORECASE)
    ts = re.search(r"TAGS:\s*(.*)", text, re.IGNORECASE)
    return (t.group(1).strip() if t else "标题提取失败",
            d.group(1).strip() if d else "描述提取失败",
            ts.group(1).strip() if ts else "")


# --- 4. 主流程 ---

def start_automation(video_dir, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    csv_path = os.path.join(output_dir, 'youtube_marketing_data.csv')

    results = []
    processed_names = set()

    # 读取已有记录，跳过已成功的，允许重试失败的
    if os.path.exists(csv_path):
        try:
            df_old = pd.read_csv(csv_path)
            # 如果标题里有“失败”字样，这次就重跑
            df_valid = df_old[~df_old['youtube标题'].str.contains("失败|异常", na=False)]
            results = df_valid.to_dict('records')
            processed_names = set(df_valid['原文件名'].astype(str).tolist())
            print(f"📊 已加载有效历史记录：{len(processed_names)} 条")
        except:
            pass

    all_videos = [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mov'))]
    todo_list = [f for f in all_videos if f not in processed_names]

    if not todo_list:
        print("✅ 没有待处理的视频。")
        return

    for filename in tqdm(todo_list, desc="总进度"):
        v_path = os.path.join(video_dir, filename)
        # 严格避开关键词，使用时间戳命名
        tmp_audio = os.path.join(output_dir, f"audio_temp_{int(time.time())}.mp3")

        try:
            # 1. 提取音频
            print(f"\n[1/3] 正在提取音频: {filename}")
            with VideoFileClip(v_path) as video:
                video.audio.write_audiofile(tmp_audio, logger=None)

            # 2. 识别文字
            print(f"[2/3] 正在转录内容...")
            result = whisper_model.transcribe(tmp_audio, language='zh', fp16=False, verbose=True)
            content = result['text']

            # 3. 请求 Gemini
            print(f"[3/3] 正在向 Gemini 请求文案...")
            ai_text = get_gemini_copywriting_via_api(content)

            title, desc, tags = ("API 响应失败", "API 响应失败", "")
            if ai_text:
                title, desc, tags = parse_output(ai_text)

            results.append({
                "原文件名": filename,
                "旁白内容": content,
                "youtube标题": title,
                "youtube描述": desc,
                "youtube hashtag": tags
            })

            # 实时存盘
            pd.DataFrame(results).to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"✨ {filename} 处理完成并保存。")

        except Exception as e:
            print(f"❌ 处理 {filename} 时发生未知错误: {e}")
        finally:
            if os.path.exists(tmp_audio):
                os.remove(tmp_audio)

    print(f"\n🎉 所有任务处理完毕！最终文件路径: {csv_path}")


if __name__ == "__main__":
    # 请确保路径正确
    input_v = '/Users/huangyun/Desktop/搬运/ENT/test_videos'
    output_v = '/Users/huangyun/Desktop/搬运/ENT/output'
    start_automation(input_v, output_v)