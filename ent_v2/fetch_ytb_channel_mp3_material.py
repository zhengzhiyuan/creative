import os
import json
import whisper
import yt_dlp
import threading
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区 =================
PROXY = "http://127.0.0.1:7897"
TOTAL_TASK_LIMIT = 5  # 每次执行程序处理的总任务数
MAX_DOWNLOAD_THREADS = 3  # 下载并发数
VIEW_THRESHOLD = 2000
MIN_DURATION = 60  # 过滤掉短视频 (Shorts)
CONTENT_LIMIT = 1000  # 文本截取字数上限
WHISPER_MODEL = "base"
OUTPUT_DIR = "./ytb_contents_ready"

# 强制将 Node.js 路径加入系统环境
os.environ["PATH"] += os.pathsep + "/usr/local/bin"


# ==========================================

class ConcurrentYTProcessor:
    def __init__(self, channel_url, output_dir):
        self.channel_url = channel_url
        self.output_dir = output_dir
        self.history_file = os.path.join(output_dir, "processed_history.txt")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.processed_ids = self._load_history()
        self.file_lock = threading.Lock()

        print(f"正在初始化 Whisper {WHISPER_MODEL} 模型... 🚀")
        self.model = whisper.load_model(WHISPER_MODEL)

        # 转录执行器：单线程，确保 CPU 任务顺序执行
        self.transcribe_executor = ThreadPoolExecutor(max_workers=1)

    def _load_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def _save_history(self, v_id):
        with self.file_lock:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(f"{v_id}\n")

    def get_videos_to_process(self):
        scan_opts = {'proxy': PROXY, 'extract_flat': True, 'quiet': True}
        eligible = []
        url = self.channel_url.split('?')[0].rstrip('/') + '/videos'

        with yt_dlp.YoutubeDL(scan_opts) as ydl:
            print(f"正在扫描频道: {url} ... 🔎")
            try:
                result = ydl.extract_info(url, download=False)
                entries = result.get('entries', [])
                for entry in entries:
                    if len(eligible) >= TOTAL_TASK_LIMIT:
                        break

                    v_id = entry.get('id')
                    duration = entry.get('duration') or 0
                    v_views = entry.get('view_count')

                    if v_id and len(v_id) == 11 and v_id not in self.processed_ids:
                        if duration >= MIN_DURATION and (v_views is None or v_views >= VIEW_THRESHOLD):
                            eligible.append((f"https://www.youtube.com/watch?v={v_id}", v_id))
                            print(f"  ✅ 发现新任务: {v_id} (约 {int(duration / 60)} 分钟)")

                return eligible
            except Exception as e:
                print(f"扫描失败: {e}")
                return []

    def transcribe_task(self, audio_path, info, v_id, v_url):
        """转录并截取前 1000 字"""
        try:
            print(f"\n[转录队列] 正在处理: {v_id} ... ☕")
            result = self.model.transcribe(audio_path, fp16=False)

            # --- 核心修改：截取前 1000 字 ---
            full_text = result["text"].strip()
            truncated_content = full_text[:CONTENT_LIMIT]
            if len(full_text) > CONTENT_LIMIT:
                truncated_content += "..."  # 添加省略号提示

            output_data = {
                "title": info.get('title'),
                "url": v_url,
                "content": truncated_content
            }

            output_filename = os.path.join(self.output_dir, f"content_{v_id}.txt")
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            if os.path.exists(audio_path):
                os.remove(audio_path)

            self._save_history(v_id)
            print(f"✅ 转录完成(已截取前{CONTENT_LIMIT}字): {v_id}")
        except Exception as e:
            print(f"❌ 转录失败 {v_id}: {e}")

    def download_and_queue_transcribe(self, v_tuple):
        v_url, v_id = v_tuple
        ydl_opts = {
            'proxy': PROXY,
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(self.output_dir, f'{v_id}.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'quiet': True,
            'nocheckcertificate': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"⬇️  正在并行下载: {v_id} ...")
                info = ydl.extract_info(v_url, download=True)
                audio_path = os.path.join(self.output_dir, f"{v_id}.mp3")

            self.transcribe_executor.submit(self.transcribe_task, audio_path, info, v_id, v_url)
            print(f"📦 已送入转录队列: {v_id}")

        except Exception as e:
            print(f"❌ 下载失败 {v_id}: {e}")

    def run(self):
        targets = self.get_videos_to_process()
        if not targets:
            print("没有新任务。💤")
            return

        print(f"🚀 开始流水线: 总数 {len(targets)} | 下载并发 {MAX_DOWNLOAD_THREADS}")

        with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_THREADS) as download_executor:
            download_executor.map(self.download_and_queue_transcribe, targets)

        print("\n下载已全部完成，等待转录队列清空... ⏳")
        self.transcribe_executor.shutdown(wait=True)
        print("\n✨ 任务处理完毕。")


if __name__ == "__main__":
    url = "https://www.youtube.com/@%D0%9D%D0%B8%D0%BA%D0%B0%D0%92%D0%B5%D1%80%D0%BE%D0%BD%D0%B8%D0%BA%D0%B0-%D0%BA7%D1%82/videos"
    processor = ConcurrentYTProcessor(url, OUTPUT_DIR)
    processor.run()