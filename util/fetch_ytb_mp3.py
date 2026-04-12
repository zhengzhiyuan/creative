import os
import whisper
from yt_dlp import YoutubeDL

PROXY = "http://127.0.0.1:7897"


def process_youtube_audio(url, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. 全量下载配置：不限制长度，追求极致下载速度
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'outtmpl': os.path.join(output_dir, 'audio_rec_%(id)s.%(ext)s'),
        'proxy': PROXY,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }

    print("Downloading full audio... Mabilis lang ito, relax ka lang. 🚀")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_filename = ydl.prepare_filename(info).replace('.m4a', '.mp3')

        # 2. 调用 Whisper 进行局部解析
        print("Starting Whisper... Only processing the first 5 minutes. ☕")

        model = whisper.load_model("medium")

        # --- 核心优化：只加载音频的前 300 秒 (5分钟) ---
        # whisper.load_audio 会读取整个文件，但我们可以手动截取
        audio = whisper.load_audio(audio_filename)
        # 采样率通常是 16000
        audio_cut = whisper.pad_or_trim(audio, length=16000 * 300)

        # 进行转录
        result = model.transcribe(audio_cut, fp16=False)

        # 3. 截取前 500 个字符并保存
        final_text = result["text"].strip()[:500]

        txt_filename = os.path.join(output_dir, f"transcription_{info['id']}.txt")
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(final_text)

        print(f"Done! 500 chars saved to: {txt_filename} ✨")
        print(f"Snippet: {final_text[:100]}...")

    except Exception as e:
        print(f"Hala, may error: {str(e)}")


if __name__ == "__main__":
    video_url = input("Enter YouTube URL: ")
    target_path = "./ytb_tmp/my_downloads"
    process_youtube_audio(video_url, target_path)