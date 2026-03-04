import os
import time
import re
import json
import gc
import pandas as pd
import whisper
import threading
from groq import Groq
from moviepy import VideoFileClip
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import warnings
import logging

# --- 0. 环境与日志配置 ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ENT_Master")
logging.getLogger("httpx").setLevel(logging.WARNING)
warnings.filterwarnings("ignore")

# --- 1. 配置加载 ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# 你的视频根目录
VIDEO_ROOT_DIR = '/Users/huangyun/Desktop/搬运/娱乐副视频/data/关注/387501331587224/视频'
OUTPUT_BASE_DIR = '/Users/huangyun/Desktop/搬运/ENT/output'


# --- 🎯 核心逻辑：生成三级路径文件名 ---
def get_csv_filename_from_path(path):
    # 去除路径末尾的斜杠
    path = path.rstrip('/')
    # 分割路径
    parts = path.split('/')
    # 取最后三级文件夹名 (例如: ['关注', '387501331587224', '视频'])
    last_three = parts[-3:] if len(parts) >= 3 else parts[-1:]
    # 用横线连接
    return "-".join(last_three)


CSV_NAME_BASE = get_csv_filename_from_path(VIDEO_ROOT_DIR)

# 并发建议：i5 建议 2
MAX_WORKERS = 2

# --- 2. 初始化引擎与锁 ---
logger.info("正在加載 Whisper 引擎 (small)...")
whisper_model = whisper.load_model("small")
client = Groq(api_key=GROQ_API_KEY)

whisper_lock = threading.Lock()
csv_lock = threading.Lock()


# --- 3. 核心功能函数 ---

def get_groq_json_summary(transcript):
    """请求 Groq 并强制返回 JSON"""
    model_name = "openai/gpt-oss-safeguard-20b"
    prompt = f"""
    你是香港資深娛樂記者。請對以下內容進行幽默抽水。
    要求：港式口語，標題黨風格。總結嚴格控制在 70 字以內。
    內容：{transcript}
    【指令】：你必須只輸出一個合法的 JSON 對象，格式：
    {{
        "summary": "這裡寫70字內的毒舌總結",
        "characters": ["人物A", "人物B"]
    }}
    """
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API 異常: {e}")
        return None


def parse_json_output(raw_json):
    summary, characters = "解析失敗", "无"
    if not raw_json: return summary, characters
    try:
        clean_json = raw_json.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_json)
        summary = data.get("summary", "解析失敗").replace('\n', ' ').strip()[:70]
        char_list = data.get("characters", [])
        if isinstance(char_list, list):
            characters = "，".join([str(c) for c in char_list]) if char_list else "无"
        elif isinstance(char_list, str):
            characters = char_list
    except:
        s_match = re.search(r'"summary":\s*"(.*?)"', raw_json)
        if s_match: summary = s_match.group(1)[:70]
    return summary, characters


# --- 4. 处理单元 ---

def process_single_video(task_info):
    root, filename, folder_name = task_info
    v_path = os.path.join(root, filename)
    t_audio = os.path.join(OUTPUT_BASE_DIR, f"temp_{os.getpid()}_{time.time_ns()}.mp3")
    try:
        with VideoFileClip(v_path) as video:
            duration = min(video.duration, 120)
            clip = video.subclipped(0, duration) if hasattr(video, 'subclipped') else video.subclip(0, duration)
            clip.audio.write_audiofile(t_audio, fps=16000, logger=None)

        with whisper_lock:
            logger.info(f"正在转录: {filename}")
            trans_res = whisper_model.transcribe(t_audio, language='zh', fp16=False, condition_on_previous_text=False)
            content = trans_res['text']
            del trans_res
            gc.collect()

        raw_json = get_groq_json_summary(content)
        summary, characters = parse_json_output(raw_json)

        return {
            "folder": folder_name,
            "record": {
                "视频文件名": filename,
                "主人翁": characters,
                "总结": summary,
                "语音文字": content.replace('\n', ' ').replace('\r', ' '),
                "处理时间": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    except Exception as e:
        logger.error(f"处理失败 {filename}: {e}")
        return None
    finally:
        if os.path.exists(t_audio):
            try:
                os.remove(t_audio)
            except:
                pass


# --- 5. 主逻辑 ---

def run_all():
    if not os.path.exists(OUTPUT_BASE_DIR): os.makedirs(OUTPUT_BASE_DIR)

    all_tasks = []
    # 如果路径下还有子文件夹，则扫描子文件夹；否则扫描根目录
    subfolders = [d for d in os.listdir(VIDEO_ROOT_DIR) if os.path.isdir(os.path.join(VIDEO_ROOT_DIR, d))]

    # 统一处理任务列表
    targets = subfolders if subfolders else ["."]
    for folder in targets:
        folder_path = os.path.join(VIDEO_ROOT_DIR, folder)
        # 根据三级路径逻辑生成文件名
        final_csv_name = f"{CSV_NAME_BASE}.csv" if folder == "." else f"{CSV_NAME_BASE}-{folder}.csv"
        csv_path = os.path.join(OUTPUT_BASE_DIR, final_csv_name)

        processed = set()
        if os.path.exists(csv_path):
            try:
                processed = set(pd.read_csv(csv_path)['视频文件名'].astype(str).tolist())
            except:
                pass

        if os.path.exists(folder_path):
            for f in os.listdir(folder_path):
                if f.lower().endswith(('.mp4', '.mov', '.mkv')) and f not in processed:
                    all_tasks.append((folder_path, f, folder))

    logger.info(f"🚀 CSV命名规则: {CSV_NAME_BASE}.csv")
    logger.info(f"🚀 待处理视频: {len(all_tasks)}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_video = {executor.submit(process_single_video, task): task for task in all_tasks}
        for future in as_completed(future_to_video):
            res = future.result()
            if res:
                f_name = res['folder']
                record = res['record']
                final_csv_name = f"{CSV_NAME_BASE}.csv" if f_name == "." else f"{CSV_NAME_BASE}-{f_name}.csv"
                out_path = os.path.join(OUTPUT_BASE_DIR, final_csv_name)

                with csv_lock:
                    df = pd.DataFrame([record])
                    cols = ["视频文件名", "主人翁", "总结", "语音文字", "处理时间"]
                    df = df[cols]
                    if not os.path.exists(out_path):
                        df.to_csv(out_path, index=False, encoding='utf-8-sig')
                    else:
                        df.to_csv(out_path, mode='a', header=False, index=False, encoding='utf-8-sig')
                logger.info(f"✓ 已完成并存入: {final_csv_name}")


if __name__ == "__main__":
    run_all()