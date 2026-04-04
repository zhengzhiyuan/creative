import yt_dlp
import os
import whisper
import threading
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
BASE_OUTPUT_DIR = "/Users/huangyun/git/creative/output1"
# 历史文件现在动态指向 BASE_OUTPUT_DIR 下
ARCHIVE_FILE = os.path.join(BASE_OUTPUT_DIR, "downloaded_history.txt")

PROXY = "http://127.0.0.1:7897"
CHANNEL_URL = "https://www.youtube.com/@%E8%8C%9C%E8%8C%9C-b1p/videos"

# 全局锁：transcribe_lock 负责保护 CPU 转录，file_lock 负责保护历史文件写入
transcribe_lock = threading.Lock()
file_lock = threading.Lock()

# 专用转录线程池：max_workers=1 配合 transcribe_lock 确保 Intel CPU 顺序处理转录且不崩溃
transcribe_executor = ThreadPoolExecutor(max_workers=1)

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


def wait_and_merge_fillers(target_dir, filler_futures, filler_txt_paths):
    """等待所有补齐视频转录完成并合并 txt"""
    # 等待该任务关联的所有补齐转录 future 完成
    for future in filler_futures:
        future.result()

    combined_path = os.path.join(target_dir, "combined_fillers.txt")
    with open(combined_path, "w", encoding="utf-8") as outfile:
        for txt_path in filler_txt_paths:
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read() + "\n\n")
    print(f"--- [合并完成] 已生成: {combined_path}")


def process_single_task(main_video, low_views_pool, task_index):
    video_id = main_video['id']
    # 文件夹命名去掉非法字符并限制长度
    folder_name = f"task_{main_video['title'][:20].strip()}".replace("/", "_")
    target_dir = os.path.join(BASE_OUTPUT_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    print(f"[任务 {task_index}] 正在处理主视频: {main_video['title']}")

    # 1. 下载主视频
    main_audio, main_duration = download_audio(main_video['url'], target_dir, "1")

    # 2. 异步提交转录任务（非阻塞）
    transcribe_executor.submit(safe_transcribe, main_audio, os.path.join(target_dir, "1.txt"))

    # 3. 写入历史记录
    update_history(video_id)

    # 4. 补齐逻辑：循环下载直到满足 1h (3600秒)
    current_total_duration = main_duration
    filler_count = 2  # 补齐视频的文件名从 "2" 开始

    filler_futures = []
    filler_txt_paths = []

    while current_total_duration < 3600:
        if not low_views_pool:
            print(f"  [任务 {task_index}] 提示：低播放量池已空，无法继续补齐。")
            break

        try:
            filler_video = low_views_pool.pop(0)
            print(
                f"  [任务 {task_index}] 当前时长 {current_total_duration}s，正在下载第 {filler_count - 1} 个补齐视频...")

            # 下载补齐视频
            filler_audio, filler_duration = download_audio(
                filler_video['url'],
                target_dir,
                str(filler_count)
            )

            # 提交转录并记录路径以便后续合并
            txt_path = os.path.join(target_dir, f"{filler_count}.txt")
            future = transcribe_executor.submit(safe_transcribe, filler_audio, txt_path)

            filler_futures.append(future)
            filler_txt_paths.append(txt_path)

            current_total_duration += filler_duration
            filler_count += 1

        except IndexError:
            break

    # 如果有补齐视频，启动一个后台线程等待转录完成并合并
    if filler_futures:
        threading.Thread(target=wait_and_merge_fillers, args=(target_dir, filler_futures, filler_txt_paths),
                         daemon=True).start()

    print(f"[任务 {task_index}] 下载阶段已完成，转录任务已全部进入队列。当前下载总时长: {current_total_duration}s")


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