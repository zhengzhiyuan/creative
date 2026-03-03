import os
import time
import re
import pandas as pd
import whisper
from google import genai  # 使用最新的 Google GenAI SDK
from moviepy import VideoFileClip
from tqdm import tqdm
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")

# --- 1. 初始化配置 ---
load_dotenv()
# SDK 会自动从环境变量 GEMINI_API_KEY 中读取，如果没有，可以在这里手动传入
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- 2. 载入转录引擎 ---
print("🤖 正在载入 Whisper (small) 引擎...")
whisper_model = whisper.load_model("small")


# --- 3. Gemini 3 Flash 调用函数 ---

def get_gemini_3_flash_copywriting(transcript, retry_count=0):
    """
    使用官方 SDK 的自适应模型调用
    """
    # 定义模型尝试优先级 (带 models/ 前缀最稳)
    model_pool = [
        "models/gemini-2.0-flash-exp",  # 目前最强的 Flash 预览版
        "models/gemini-1.5-flash",  # 标准 Flash 版
        "models/gemini-1.5-flash-latest",  # 始终指向最新的 1.5 Flash
        "models/gemini-3-flash-preview"  # 如果你的环境已开放 3.0
    ]

    # 根据重试次数选择模型，如果第一个不行，第二次换一个试
    current_model = model_pool[retry_count % len(model_pool)]

    try:
        print(f"📡 正在尝试模型: {current_model} ...")

        response = client.models.generate_content(
            model=current_model,
            contents=f"角色：資深香港娛樂主編。內容：{transcript}\n要求：以毒舌港式口語創作標題黨標題、描述和標籤。格式：TITLE:, DESC:, TAGS:"
        )

        if response and response.text:
            return response.text
        return None

    except Exception as e:
        err_msg = str(e)

        # 如果是 404，说明模型名不对，立刻换下一个模型重试
        if "404" in err_msg or "NOT_FOUND" in err_msg:
            if retry_count < len(model_pool) - 1:
                print(f"⚠️ 模型 {current_model} 未找到，切换下一个...")
                return get_gemini_3_flash_copywriting(transcript, retry_count + 1)

        # 如果是 503 或 429，等一会儿再试同一个或下一个
        if "503" in err_msg or "429" in err_msg:
            if retry_count < 5:
                wait_time = 15
                print(f"⏳ 服务器忙或限流，静默 {wait_time}s 后重试...")
                time.sleep(wait_time)
                return get_gemini_3_flash_copywriting(transcript, retry_count + 1)

        print(f"❌ SDK 最终报错: {err_msg}")
        return None


def parse_output(text):
    """解析 AI 输出的固定格式"""
    t = re.search(r"TITLE:\s*(.*)", text, re.IGNORECASE)
    d = re.search(r"DESC:\s*(.*)", text, re.IGNORECASE)
    ts = re.search(r"TAGS:\s*(.*)", text, re.IGNORECASE)
    return (t.group(1).strip() if t else "标题生成失败",
            d.group(1).strip() if d else "描述生成失败",
            ts.group(1).strip() if ts else "")


# --- 4. 自动化主流程 ---

def start_automation(video_dir, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    csv_path = os.path.join(output_dir, 'youtube_marketing_data.csv')

    # 读取旧数据，支持断点续传
    results = []
    if os.path.exists(csv_path):
        try:
            df_old = pd.read_csv(csv_path)
            # 如果标题包含失败字样，则视为未完成，允许重跑
            df_valid = df_old[~df_old['youtube标题'].str.contains("失败|错误|请求", na=False)]
            results = df_valid.to_dict('records')
            print(f"📊 已有有效记录：{len(results)} 条")
        except:
            pass

    processed_names = {str(r['原文件名']) for r in results}
    all_videos = [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mov'))]
    todo_list = [f for f in all_videos if f not in processed_names]

    if not todo_list:
        print("✅ 任务已全部完成！")
        return

    for filename in tqdm(todo_list, desc="任务总进度"):
        v_path = os.path.join(video_dir, filename)
        # 根据你的习惯，避开 cleansed_P 前缀，使用时间戳
        tmp_audio = os.path.join(output_dir, f"audio_cache_{int(time.time())}.mp3")

        try:
            # 1. 视频转音频
            with VideoFileClip(v_path) as video:
                video.audio.write_audiofile(tmp_audio, logger=None)

            # 2. Whisper 转录文字
            print(f"\n[2/3] 正在转录文字: {filename}")
            result = whisper_model.transcribe(tmp_audio, language='zh', fp16=False)
            content = result['text']

            # 3. SDK 调用 Gemini 3 Flash
            print(f"[3/3] 正在向 Gemini 3 Flash 请求营销文案...")
            ai_text = get_gemini_3_flash_copywriting(content)

            title, desc, tags = ("请求失败", "请求失败", "")
            if ai_text:
                title, desc, tags = parse_output(ai_text)

            results.append({
                "原文件名": filename,
                "旁白内容": content,
                "youtube标题": title,
                "youtube描述": desc,
                "youtube hashtag": tags
            })

            # 实时存盘，防止中途奔溃
            pd.DataFrame(results).to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"✨ {filename} 文案已生成并存盘。")

        except Exception as e:
            print(f"❌ 处理 {filename} 时发生错误: {e}")
        finally:
            if os.path.exists(tmp_audio):
                os.remove(tmp_audio)

    print(f"\n🎉 运行结束！结果保存在: {csv_path}")


if __name__ == "__main__":
    # 配置路径
    input_v = '/Users/huangyun/Desktop/搬运/ENT/test_videos'
    output_v = '/Users/huangyun/Desktop/搬运/ENT/output'
    # start_automation(input_v, output_v)

    get_gemini_3_flash_copywriting('郭碧婷')