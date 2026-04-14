import os
import json
import whisper
from yt_dlp import YoutubeDL

# ================= 配置区 =================
PROXY = "http://127.0.0.1:7897"
DOWNLOAD_LIMIT = 3  # 每次下载3个
VIEW_THRESHOLD = 2000  # 播放量阈值
MIN_DURATION = 60  # 过滤长视频
WHISPER_MODEL = "small"  # 你也可以改回 medium，根据你的 Mac 性能定
CONTENT_LIMIT = 1000


# ==========================================

class RobustYouTubeProcessor:
    def __init__(self, channel_url, output_dir):
        self.channel_url = channel_url
        self.output_dir = output_dir
        self.history_file = os.path.join(output_dir, "processed_history.txt")
        if not os.path.exists(self.output_dir): os.makedirs(self.output_dir)
        self.processed_ids = self._load_history()
        self.model = whisper.load_model(WHISPER_MODEL)

    def _load_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def _save_history(self, v_id):
        with open(self.history_file, "a") as f: f.write(f"{v_id}\n")

    def get_videos_to_process(self):
        """扫描频道，找到符合播放量要求的视频"""
        scan_opts = {'proxy': PROXY, 'extract_flat': True, 'quiet': True}
        eligible = []
        with YoutubeDL(scan_opts) as ydl:
            print("Scanning channel... Wait lang po. 🔎")
            try:
                # 确保抓取的是 /videos 列表
                url = self.channel_url.split('?')[0].rstrip('/')
                if not url.endswith('/videos'):
                    url += '/videos'

                result = ydl.extract_info(url, download=False)
                entries = result.get('entries', [])

                print(f"Total videos found: {len(entries)}")

                for entry in entries:
                    if not entry: continue

                    v_id = entry.get('id')
                    # 修复点：如果 v_views 是 None，则取 0
                    v_views = entry.get('view_count') or 0

                    # 过滤：未处理过 + 播放量达标
                    if v_id and v_id not in self.processed_ids:
                        if v_views >= VIEW_THRESHOLD:
                            eligible.append(entry.get('url') or f"https://www.youtube.com/watch?v={v_id}")
                            print(f"✅ Found eligible: {v_id} (Views: {v_views})")

                    if len(eligible) >= DOWNLOAD_LIMIT:
                        break

                return eligible
            except Exception as e:
                print(f"Scan error: {e}")
                return []

    def process_video(self, url):
        """套用你验证成功的 ydl_opts 进行下载"""
        ydl_opts = {
            'format': 'm4a/bestaudio/best',
            'outtmpl': os.path.join(self.output_dir, '%(id)s.%(ext)s'),
            'proxy': PROXY,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                v_id = info['id']
                v_title = info['title']
                # 转换后的文件名
                audio_filename = os.path.join(self.output_dir, f"{v_id}.mp3")

            print(f"Transcribing {v_id}... ☕")
            audio = whisper.load_audio(audio_filename)
            # 截取前 10 分钟
            audio_cut = whisper.pad_or_trim(audio, length=16000 * 600)
            result = self.model.transcribe(audio_cut, fp16=False)

            # 组织 JSON 数据
            content = result["text"].strip()[:CONTENT_LIMIT]
            data = {"title": v_title, "content": content}

            # 保存
            with open(os.path.join(self.output_dir, f"content_{v_id}.txt"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            if os.path.exists(audio_filename): os.remove(audio_filename)
            self._save_history(v_id)
            print(f"Done: {v_id} ✨")

        except Exception as e:
            print(f"Error processing {url}: {e}")

    def run(self):
        urls = self.get_videos_to_process()
        if not urls:
            print("No new videos found. Wala na. 💤")
            return
        for url in urls:
            self.process_video(url)


if __name__ == "__main__":
    channel = input("Enter YouTube Channel URL: ")
    output = "./ytb_contents_final"
    processor = RobustYouTubeProcessor(channel, output)
    processor.run()