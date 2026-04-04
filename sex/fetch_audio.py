import yt_dlp
import os
import shutil
import whisper  # 或者使用 faster_whisper

# --- 配置区 ---
BASE_OUTPUT_DIR = "/Users/huangyun/git/creative/output"  # 你指定的目录
PROXY = "http://127.0.0.1:7897"
CHANNEL_URL = "https://www.youtube.com/@%E8%8C%9C%E8%8C%9C-b1p/videos"
ARCHIVE_FILE = "downloaded_history.txt"

# 初始化 Whisper 模型 (Mac M系列建议用 base 或 small)
print("正在加载 Whisper 模型...")
model = whisper.load_model("base")


def get_video_info(url):
    """获取频道所有视频的基础信息，不下载"""
    ydl_opts = {'proxy': PROXY, 'quiet': True, 'extract_flat': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)['entries']


def download_and_transcribe(video_url, output_path, new_name):
    """下载音频并转录为 txt"""
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
        audio_file = os.path.join(output_path, f"{new_name}.mp3")
        duration = info.get('duration', 0)

        # Whisper 转录
        print(f"正在转录: {new_name}.mp3 ...")
        result = model.transcribe(audio_file)
        with open(os.path.join(output_path, f"{new_name}.txt"), "w", encoding="utf-8") as f:
            f.write(result["text"])

        return duration


def run_pipeline():
    videos = get_video_info(CHANNEL_URL)

    # 分类视频
    high_views = [v for v in videos if (v.get('view_count') or 0) >= 5000 and v.get('duration', 0) > 60]
    low_views = [v for v in videos if (v.get('view_count') or 0) < 5000 and v.get('duration', 0) > 60]

    # 加载历史，过滤掉下过的
    downloaded_ids = []
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, 'r') as f:
            downloaded_ids = f.read().splitlines()

    folder_count = 0
    for main_video in high_views:
        if folder_count >= 3: break
        video_id = main_video['id']
        if video_id in downloaded_ids: continue

        # 1. 创建文件夹
        folder_name = f"task_{main_video['title'][:30].strip()}"
        target_dir = os.path.join(BASE_OUTPUT_DIR, folder_name)
        os.makedirs(target_dir, exist_ok=True)

        # 2. 下载首视频 (命名为 1)
        print(f"\n生成文件夹: {folder_name}")
        main_duration = download_and_transcribe(main_video['url'], target_dir, "1")

        # 记录已下载
        with open(ARCHIVE_FILE, 'a') as f:
            f.write(f"{video_id}\n")

        # 3. 补齐逻辑 (判断是否满 1h / 3600秒)
        if main_duration < 3600 and low_views:
            filler_video = low_views.pop(0)  # 取出一个低播放量视频
            print(f"首视频时长不足1h ({main_duration}s)，正在下载补齐视频...")
            download_and_transcribe(filler_video['url'], target_dir, "2")

        folder_count += 1


if __name__ == "__main__":
    run_pipeline()