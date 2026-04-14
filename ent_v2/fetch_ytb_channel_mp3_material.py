import os
import json
import whisper
import yt_dlp
import threading
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区 =================
PROXY = "http://127.0.0.1:7897"
TOTAL_TASK_LIMIT = 5  # 每次执行程序处理的总任务数（找到5个就停）
MAX_DOWNLOAD_THREADS = 3  # 下载并发数
VIEW_THRESHOLD = 200
MIN_DURATION = 60  # 过滤掉小于60秒的短视频 (Shorts)
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
        """扫描并根据总量限制获取任务"""
        scan_opts = {'proxy': PROXY, 'extract_flat': True, 'quiet': True}
        eligible = []
        url = self.channel_url.split('?')[0].rstrip('/') + '/videos'

        with yt_dlp.YoutubeDL(scan_opts) as ydl:
            print(f"正在扫描频道: {url} ... 🔎")
            try:
                result = ydl.extract_info(url, download=False)
                entries = result.get('entries', [])
                for entry in entries:
                    # 达到 5 个任务上限就停止扫描
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
        """转录逻辑：单线程顺序执行"""
        try:
            print(f"\n[转录队列] 正在处理: {v_id} ... ☕")
            # fp16=False 适配 CPU 环境，避免警告并提高稳定性
            result = self.model.transcribe(audio_path, fp16=False)

            output_data = {
                "title": info.get('title'),
                "url": v_url,
                "content": result["text"].strip()
            }

            output_filename = os.path.join(self.output_dir, f"content_{v_id}.txt")
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            # 清理音频文件
            if os.path.exists(audio_path):
                os.remove(audio_path)

            self._save_history(v_id)
            print(f"✅ 转录完成并存档: {v_id}")
        except Exception as e:
            print(f"❌ 转录失败 {v_id}: {e}")

    def download_and_queue_transcribe(self, v_tuple):
        """下载逻辑：多线程并发执行"""
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

            # 下载完成后，将转录任务送入单线程池排队
            self.transcribe_executor.submit(self.transcribe_task, audio_path, info, v_id, v_url)
            print(f"📦 下载完成，已送入转录队列: {v_id}")

        except Exception as e:
            print(f"❌ 下载失败 {v_id}: {e}")

    def run(self):
        targets = self.get_videos_to_process()
        if not targets:
            print("没有发现符合条件的新视频。💤")
            return

        print(f"🚀 开始流水线: 总任务数 {len(targets)} | 下载并发 {MAX_DOWNLOAD_THREADS} | 顺序转录")

        # 1. 使用并发线程池处理下载
        with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_THREADS) as download_executor:
            # map 会阻塞直到所有下载任务“提交”完成
            download_executor.map(self.download_and_queue_transcribe, targets)

        # 2. 等待所有转录任务完成
        print("\n所有视频已下载完成，正在等待队列中的转录任务结束... ⏳")
        self.transcribe_executor.shutdown(wait=True)
        print("\n✨ 本次程序执行完毕，所有任务已处理。")


if __name__ == "__main__":
    url = "https://www.youtube.com/@%D0%9D%D0%B8%D0%BA%D0%B0%D0%92%D0%B5%D1%80%D0%BE%D0%BD%D0%B8%D0%BA%D0%B0-%D0%BA7%D1%82/videos"
    processor = ConcurrentYTProcessor(url, OUTPUT_DIR)
    processor.run()