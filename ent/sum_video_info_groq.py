import os
import time
import re
import pandas as pd
import whisper
from groq import Groq  # 换成 Groq
from moviepy import VideoFileClip
from tqdm import tqdm
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")

# --- 1. 配置加载 ---
load_dotenv()
# 请在 .env 中添加 GROQ_API_KEY=你的Key
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "在这里直接填入你的gsk_Key也行"
PROXY_URL = os.getenv("HTTPS_PROXY")

if PROXY_URL:
    os.environ['HTTP_PROXY'] = PROXY_URL
    os.environ['HTTPS_PROXY'] = PROXY_URL

# --- 2. 初始化模型 ---
print("🤖 正在载入 Whisper (small) 引擎...")
whisper_model = whisper.load_model("small")

# 初始化 Groq 客户端
client = Groq(api_key=GROQ_API_KEY)


# --- 3. 工具函数 ---

def get_groq_copywriting(transcript):
    # 增加具体的“爆款模版”指导
    prompt = f"""
    你现在是香港《壹週刊》或《東方新地》的资深八卦主编。说话极度毒舌、势利、爱抽水，精通YouTube点击率密码。

    任务：根据以下视频旁白，创作一个让人“不点进去就会错过百亿遗产”的劲爆标题。

    内容：{transcript}

    【写作指南】：
    1. 必须使用港式口语（如：真係、贏麻了、抽水、頂唔順、發錢寒、係咪、咁都得）。
    2. 标题套路：
       - 反转类：[原以为...结果...] 
       - 揭秘类：[向華強終於講真話！...]
       - 对比类：[親生仔不如外姓人？...]
       - 悬念类：[這集豪門劇絕了...]
    3. 情绪要到位：要么替人尴尬，要么替人狂喜，要么疯狂嘲讽。
    4. 严禁使用“这个视频讲述了”、“向华强决定”这种平淡的陈述句。

    严格输出格式：
    TITLE: [这里写一个最劲爆的标题]
    DESC: [这里写一段充满悬念的描述，用港式毒舌风格]
    TAGS: #香港八卦, #向華強, #郭碧婷, #豪門內鬥
    """

    try:
        # 增加 temperature 到 0.9，让它更具创造力和随机性，不再死板
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=1024
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"\n❌ Groq 请求失败: {e}")
        return None


def parse_output(text):
    t = re.search(r"TITLE:\s*(.*)", text, re.IGNORECASE)
    d = re.search(r"DESC:\s*(.*)", text, re.IGNORECASE)
    ts = re.search(r"TAGS:\s*(.*)", text, re.IGNORECASE)
    return (t.group(1).strip() if t else "标题生成失败",
            d.group(1).strip() if d else "描述生成失败",
            ts.group(1).strip() if ts else "")


# --- 4. 主流程 ---

def start_automation(video_dir, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    csv_path = os.path.join(output_dir, 'youtube_marketing_data.csv')

    results = []
    processed_names = set()

    # 读取历史，允许重跑失败的
    if os.path.exists(csv_path):
        try:
            df_old = pd.read_csv(csv_path)
            df_valid = df_old[~df_old['youtube标题'].str.contains("失败|异常", na=False)]
            results = df_valid.to_dict('records')
            processed_names = set(df_valid['原文件名'].astype(str).tolist())
        except:
            pass

    all_videos = [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mov'))]
    todo_list = [f for f in all_videos if f not in processed_names]

    if not todo_list:
        print("✅ 任务已全部完成！")
        return

    for filename in tqdm(todo_list, desc="任务总进度"):
        v_path = os.path.join(video_dir, filename)
        # 避开 cleansed_P 关键字
        tmp_audio = os.path.join(output_dir, f"audio_seg_{int(time.time())}.mp3")

        try:
            # 1. 提取
            with VideoFileClip(v_path) as video:
                video.audio.write_audiofile(tmp_audio, logger=None)

            # 2. 转录
            print(f"\n[2/3] 正在转录: {filename}")
            result = whisper_model.transcribe(tmp_audio, language='zh', fp16=False)
            content = result['text']

            # 3. 文案生成 (Groq)
            print(f"[3/3] 正在向 Groq 请求极速文案...")
            ai_text = get_groq_copywriting(content)

            title, desc, tags = ("API生成失败", "API生成失败", "")
            if ai_text:
                title, desc, tags = parse_output(ai_text)

            results.append({
                "原文件名": filename,
                "旁白内容": content,
                "youtube标题": title,
                "youtube描述": desc,
                "youtube hashtag": tags
            })

            pd.DataFrame(results).to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"✨ {filename} 已完成存档。")

        except Exception as e:
            print(f"❌ 运行报错: {e}")
        finally:
            if os.path.exists(tmp_audio): os.remove(tmp_audio)


if __name__ == "__main__":
    # 配置你的路径
    v_dir = '/Users/huangyun/Desktop/搬运/ENT/test_videos'
    o_dir = '/Users/huangyun/Desktop/搬运/ENT/output'
    start_automation(v_dir, o_dir)

