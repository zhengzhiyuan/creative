import asyncio
import edge_tts
import os
import random
import numpy as np
import PIL.Image
import subprocess
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.config import change_settings

# --- 自动寻找 ImageMagick 路径 ---
def find_imagemagick():
    for cmd in ["magick", "convert"]:
        try:
            path = subprocess.check_output(["which", cmd]).decode("utf-8").strip()
            if path:
                return path
        except:
            continue
    return None

IM_PATH = find_imagemagick()
if IM_PATH:
    print(f"找到 ImageMagick 路径: {IM_PATH}")
    change_settings({"IMAGEMAGICK_BINARY": IM_PATH})
else:
    print("错误：未能在系统中找到 ImageMagick，请执行 'brew install imagemagick'")

# --- Pillow 兼容性补丁 ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- 核心配置 ---
INPUT_TXT = "/Users/huangyun/git/creative/output/task_老公車禍癱瘓.公公怕我離婚.幫忙乾活…./1.txt"
SOURCE_VIDEOS_DIR = "/Users/huangyun/Desktop/搬运/sex_creative/游戏波"

BASE_DIR = os.path.dirname(INPUT_TXT)
TEMP_DIR = os.path.join(BASE_DIR, "temp_chunks")
FINAL_MP3 = os.path.join(BASE_DIR, "final_refined_voice.mp3")
FINAL_SRT = os.path.join(BASE_DIR, "subtitle.srt")
FINAL_VIDEO = os.path.join(BASE_DIR, "final_video_output.mp4")

VOICE = "zh-CN-XiaoyiNeural"
TARGET_RES = (1920, 1080)
CLIP_DUR = 4


# --- 1. TTS 逻辑 ---
async def tts_with_subtitles(text_list):
    if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)

    combined_audio = AudioSegment.empty()
    subtitles_content = []
    current_time_ms = 0

    print(f"开始 TTS 合成，共 {len(text_list)} 段...")

    for i, text in enumerate(text_list):
        chunk_mp3 = os.path.join(TEMP_DIR, f"{i}.mp3")
        r_rate = f"{random.randint(-20, -15)}%"

        communicate = edge_tts.Communicate(text, VOICE, rate=r_rate)
        submaker = edge_tts.SubMaker()

        with open(chunk_mp3, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)

        segment = AudioSegment.from_mp3(chunk_mp3)

        start_time = current_time_ms / 1000.0
        end_time = (current_time_ms + len(segment)) / 1000.0

        # 标准 SRT 格式
        srt_entry = f"{i + 1}\n{format_time(start_time)} --> {format_time(end_time)}\n{text}\n\n"
        subtitles_content.append(srt_entry)

        pause_dur = random.randint(1500, 2800)
        pause = AudioSegment.silent(duration=pause_dur)

        combined_audio += segment + pause
        current_time_ms += (len(segment) + pause_dur)
        os.remove(chunk_mp3)

    with open(FINAL_SRT, "w", encoding="utf-8") as f:
        f.writelines(subtitles_content)

    noise = generate_noise(len(combined_audio))
    final_audio = combined_audio.overlay(noise - 55)
    final_audio.export(FINAL_MP3, format="mp3", bitrate="192k")
    return len(combined_audio) / 1000.0


def format_time(seconds):
    millis = int((seconds % 1) * 1000)
    seconds = int(seconds)
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def generate_noise(duration_ms):
    samples = np.random.uniform(-1, 1, int(duration_ms * 44.1))
    return AudioSegment((samples * 32767).astype(np.int16).tobytes(), frame_rate=44100, sample_width=2, channels=1)


# --- 2. 视频逻辑 ---
def create_video(total_duration):
    print("开始生成视觉画面...")
    all_vids = [os.path.join(SOURCE_VIDEOS_DIR, f) for f in os.listdir(SOURCE_VIDEOS_DIR) if
                f.endswith(('.mp4', '.mov'))]

    if not all_vids:
        print(f"错误：素材目录 {SOURCE_VIDEOS_DIR} 为空。")
        return

    clips = []
    curr = 0
    while curr < total_duration:
        v_path = random.choice(all_vids)
        try:
            with VideoFileClip(v_path) as v:
                dur = min(CLIP_DUR, v.duration)
                start = random.uniform(0, max(0, v.duration - dur))
                clip = v.subclip(start, start + dur).without_audio()

                clip = clip.resize(height=TARGET_RES[1])
                if clip.w != TARGET_RES[0]:
                    clip = clip.set_position("center").on_color(size=TARGET_RES, color=(0, 0, 0))

                clips.append(clip)
                curr += dur
        except Exception as e:
            print(f"跳过视频 {v_path}: {e}")

    final_visual = concatenate_videoclips(clips, method="compose").set_duration(total_duration)

    # 字幕生成
    generator = lambda txt: TextClip(txt, font='/System/Library/Fonts/PingFang.ttc',
                                     fontsize=45, color='white', stroke_color='black', stroke_width=1,
                                     method='caption', size=(TARGET_RES[0] * 0.8, None))

    subtitles = SubtitlesClip(FINAL_SRT, generator)

    result = CompositeVideoClip([final_visual, subtitles.set_position(('center', 850))])
    result = result.set_audio(AudioFileClip(FINAL_MP3))

    print("正在渲染最终视频...")
    result.write_videofile(FINAL_VIDEO, codec="libx264", audio_codec="aac", fps=24, threads=4)


# --- 3. 运行入口 ---
async def main():
    with open(INPUT_TXT, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if len(line.strip()) > 5]

    if not lines:
        print("错误：文稿为空。")
        return

    total_sec = await tts_with_subtitles(lines)
    create_video(total_sec)

    if os.path.exists(TEMP_DIR):
        for file in os.listdir(TEMP_DIR):
            os.remove(os.path.join(TEMP_DIR, file))
        os.rmdir(TEMP_DIR)
    print(f"任务完成！保存于: {FINAL_VIDEO}")


if __name__ == "__main__":
    asyncio.run(main())