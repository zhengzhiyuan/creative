import yt_dlp
import os
import whisper
import threading
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
BASE_OUTPUT_DIR = "/Users/huangyun/git/creative/output"
# 历史文件现在动态指向 BASE_OUTPUT_DIR 下
ARCHIVE_FILE = os.path.join(BASE_OUTPUT_DIR, "downloaded_history.txt")

PROXY = "http://127.0.0.1:7897"
CHANNEL_URL = "https://www.youtube.com/@%E8%8C%9C%E8%8C%9C-b1p/videos"

# 全局锁：transcribe_lock 负责保护 CPU 转录，file_lock 负责保护历史文件写入
transcribe_lock = threading.Lock()
file_lock = threading.Lock()

print("正在加载 Whisper 模型...")
# 如果 Intel Mac 依然吃力，可以考虑将 "base" 改为 "tiny"
model = whisper.load_model("base")


def get_video_info(url):
    ydl_opts = {'proxy': PROXY, 'quiet': True, 'extract_flat': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)['entries']


def download_audio(video_url, output_path, new_name):
    ydl_opts = {
        'proxy': PROXY,
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_path, f"{new_name}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return os.path.join(output_path, f"{new_name}.mp3"), info.get('duration', 0)


def safe_transcribe(audio_file, txt_path):
    """确保 Intel CPU 同一时间只跑一个转录任务"""
    with transcribe_lock:
        print(f">>> 开始转录: {os.path.basename(audio_file)}")
        result = model.transcribe(audio_file, language="zh")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result["text"])


def update_history(video_id):
    """线程安全地更新历史记录文件"""
    with file_lock:
        with open(ARCHIVE_FILE, 'a', encoding="utf-8") as f:
            f.write(f"{video_id}\n")


def process_single_task(main_video, low_views_pool, task_index):
    video_id = main_video['id']
    # 文件夹命名去掉非法字符并限制长度
    folder_name = f"task_{main_video['title'][:20].strip()}".replace("/", "_")
    target_dir = os.path.join(BASE_OUTPUT_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    print(f"[任务 {task_index}] 正在并发下载主视频...")

    # 1. 下载主视频
    main_audio, main_duration = download_audio(main_video['url'], target_dir, "1")

    # 2. 排队转录主视频
    safe_transcribe(main_audio, os.path.join(target_dir, "1.txt"))

    # 3. 写入历史记录
    update_history(video_id)

    # 4. 补齐逻辑
    if main_duration < 3600 and low_views_pool:
        # 取出一个低播放视频（注意：由于任务数只有3个，简单pop即可）
        try:
            filler_video = low_views_pool.pop(0)
            print(f"  [任务 {task_index}] 时长不足1h，下载补齐视频...")
            filler_audio, _ = download_audio(filler_video['url'], target_dir, "2")
            safe_transcribe(filler_audio, os.path.join(target_dir, "2.txt"))
        except IndexError:
            pass


def run_pipeline():
    if not os.path.exists(BASE_OUTPUT_DIR):
        os.makedirs(BASE_OUTPUT_DIR)

    print("正在获取频道视频列表...")
    videos = get_video_info(CHANNEL_URL)

    # 这里的过滤逻辑保持不变
    high_views = [v for v in videos if (v.get('view_count') or 0) >= 5000 and v.get('duration', 0) > 60]
    low_views = [v for v in videos if (v.get('view_count') or 0) < 5000 and v.get('duration', 0) > 60]

    # 从 BASE_OUTPUT_DIR 下读取历史
    downloaded_ids = []
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, 'r', encoding="utf-8") as f:
            downloaded_ids = f.read().splitlines()

    tasks_to_run = [v for v in high_views if v['id'] not in downloaded_ids][:3]

    if not tasks_to_run:
        print("没有发现新的高播放量视频。")
        return

    print(f"共发现 {len(tasks_to_run)} 个新任务，准备并发下载...")

    # 并发执行 3 个文件夹任务
    with ThreadPoolExecutor(max_workers=3) as executor:
        for i, video in enumerate(tasks_to_run):
            executor.submit(process_single_task, video, low_views, i + 1)


if __name__ == "__main__":
    run_pipeline()