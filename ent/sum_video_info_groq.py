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
VIDEO_ROOT_DIR = '/Users/huangyun/Desktop/搬运/娱乐副视频/data/收藏/视频'
OUTPUT_BASE_DIR = '/Users/huangyun/Desktop/搬运/ENT/output'

# 自动获取根目录名作为前缀
ROOT_FOLDER_NAME = os.path.basename(os.path.normpath(VIDEO_ROOT_DIR))

# 并发建议：i5 建议 2。如果依然觉得“串词”，请改为 1。
MAX_WORKERS = 2

# --- 2. 初始化引擎与锁 ---
logger.info("正在加載 Whisper 引擎 (small)...")
whisper_model = whisper.load_model("small")
client = Groq(api_key=GROQ_API_KEY)

whisper_lock = threading.Lock()
csv_lock = threading.Lock()


# --- 3. 核心功能函数 ---

def get_groq_json_summary(transcript):
    """请求 Groq 并强制返回 JSON (无地区信息)"""
    model_name = "openai/gpt-oss-safeguard-20b"

    prompt = f"""
    你是香港資深娛樂記者。請對以下內容進行幽默抽水。
    要求：港式口語，標題黨風格。總結嚴格控制在 70 字以內。

    內容：{transcript}

    【指令】：你必須只輸出一個合法的 JSON 對象，不要包含任何解釋。
    格式要求：
    {{
        "summary": "這裡寫70字內的毒舌總結",
        "characters": ["人物A", "人物B"]
    }}
    【注意】：characters 必須是提到的人物姓名數組。
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
    """解析 JSON 字符串 (包含主人翁)"""
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
        # 正则保底
        s_match = re.search(r'"summary":\s*"(.*?)"', raw_json)
        if s_match: summary = s_match.group(1)[:70]

    return summary, characters


# --- 4. 单个视频处理单元 ---

def process_single_video(task_info):
    root, filename, folder_name = task_info
    v_path = os.path.join(root, filename)
    # 使用纳秒级时间戳，彻底防止多线程文件名冲突导致读错音频
    t_audio = os.path.join(OUTPUT_BASE_DIR, f"temp_{os.getpid()}_{time.time_ns()}.mp3")

    try:
        # A. 提取音频
        with VideoFileClip(v_path) as video:
            duration = min(video.duration, 120)
            clip = video.subclipped(0, duration) if hasattr(video, 'subclipped') else video.subclip(0, duration)
            clip.audio.write_audiofile(t_audio, fps=16000, logger=None)

        # B. 转录 (排队 + 禁用上下文记忆)
        with whisper_lock:
            logger.info(f"正在转录: {filename}")
            # condition_on_previous_text=False 解决“视频内容串联”的核心参数
            trans_res = whisper_model.transcribe(
                t_audio,
                language='zh',
                fp16=False,
                condition_on_previous_text=False
            )
            content = trans_res['text']
            # 手动释放内存防止残留
            del trans_res
            gc.collect()

        # C. AI 分析
        raw_json = get_groq_json_summary(content)
        summary, characters = parse_json_output(raw_json)

        return {
            "folder": folder_name,
            "record": {
                "视频文件名": filename,
                "主人翁": characters,
                "总结": summary,
                "语音文字": content.replace('\n', ' ').replace('\r', ' '),  # 清洗换行符防止CSV格式错乱
                "处理时间": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    except Exception as e:
        logger.error(f"处理失败 {filename}: {e}")
        return None
    finally:
        # 强制清理临时文件
        if os.path.exists(t_audio):
            try:
                os.remove(t_audio)
            except:
                pass


# --- 5. 主运行逻辑 ---

def run_all():
    if not os.path.exists(OUTPUT_BASE_DIR): os.makedirs(OUTPUT_BASE_DIR)

    all_tasks = []
    subfolders = [d for d in os.listdir(VIDEO_ROOT_DIR) if os.path.isdir(os.path.join(VIDEO_ROOT_DIR, d))]
    if not subfolders: subfolders = ["."]

    for folder in subfolders:
        folder_path = os.path.join(VIDEO_ROOT_DIR, folder)
        csv_prefix = f"{ROOT_FOLDER_NAME}_{folder}" if folder != "." else ROOT_FOLDER_NAME
        csv_path = os.path.join(OUTPUT_BASE_DIR, f"{csv_prefix}_results.csv")

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

    logger.info(f"🚀 扫描完成。待处理: {len(all_tasks)}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_video = {executor.submit(process_single_video, task): task for task in all_tasks}

        for future in as_completed(future_to_video):
            res = future.result()
            if res:
                f_name = res['folder']
                record = res['record']

                csv_prefix = f"{ROOT_FOLDER_NAME}_{f_name}" if f_name != "." else ROOT_FOLDER_NAME
                out_path = os.path.join(OUTPUT_BASE_DIR, f"{csv_prefix}_results.csv")

                # 加锁写入，确保 CSV 记录不会合并或错位
                with csv_lock:
                    df = pd.DataFrame([record])
                    cols = ["视频文件名", "主人翁", "总结", "语音文字", "处理时间"]
                    df = df[cols]

                    if not os.path.exists(out_path):
                        df.to_csv(out_path, index=False, encoding='utf-8-sig')
                    else:
                        df.to_csv(out_path, mode='a', header=False, index=False, encoding='utf-8-sig')

                logger.info(f"✓ 已完成: {record['视频文件名']}")

    logger.info("🎉 所有任务异步执行完毕。")


if __name__ == "__main__":
    run_all()