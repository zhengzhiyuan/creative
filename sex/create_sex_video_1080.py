import asyncio
import edge_tts
import os
import random
import numpy as np
import PIL.Image
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

# --- Pillow 兼容性补丁 ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- 核心配置 ---
# INPUT_TXT = "/Users/huangyun/git/creative/output1/task_老公車禍癱瘓/final.txt"
INPUT_TXT = "/Users/huangyun/git/creative/output1/task_老公出差去接公公/final.txt"
SOURCE_VIDEOS_DIR = "/Users/huangyun/Desktop/搬运/sex_creative/游戏波/output1080"

BASE_DIR = os.path.dirname(INPUT_TXT)
TEMP_DIR = os.path.join(BASE_DIR, "temp_chunks")
FINAL_MP3 = os.path.join(BASE_DIR, "final_refined_voice.mp3")
FINAL_SRT = os.path.join(BASE_DIR, "subtitle.srt")
FINAL_VIDEO = os.path.join(BASE_DIR, "final_video_output.mp4")

VOICE = "zh-CN-XiaoxiaoNeural"
# 修改点：支持 1080P 分辨率
TARGET_RES = (1920, 1080)
CLIP_DUR = 4
MAX_CONCURRENT_REQUESTS = 3
CHUNK_LIMIT = 600

# 修改点：1080P 建议码率上调至 5000k，画质更清晰
TARGET_BITRATE = "5000k"


# --- 1. TTS 并发逻辑 ---
async def fetch_tts_chunk(semaphore, index, text, voice, temp_dir):
    async with semaphore:
        chunk_mp3 = os.path.join(temp_dir, f"{index}.mp3")
        r_rate = f"{random.randint(-20, -15)}%"
        print(f"   [请求中] 第 {index + 1} 段 (约 {len(text)} 字)...")
        try:
            communicate = edge_tts.Communicate(text, voice, rate=r_rate)
            await communicate.save(chunk_mp3)
            return index, chunk_mp3, text
        except Exception as e:
            print(f"   ❌ 第 {index + 1} 段合成失败: {e}")
            return index, None, text


async def tts_with_subtitles(text_list):
    if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    tasks = [fetch_tts_chunk(semaphore, i, text, VOICE, TEMP_DIR) for i, text in enumerate(text_list)]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])

    combined_audio = AudioSegment.empty()
    subtitles_content = []
    current_time_ms = 0

    for index, mp3_path, text in results:
        if mp3_path and os.path.exists(mp3_path):
            try:
                segment = AudioSegment.from_mp3(mp3_path)
                start_time = current_time_ms / 1000.0
                end_time = (current_time_ms + len(segment)) / 1000.0
                srt_entry = f"{index + 1}\n{format_time(start_time)} --> {format_time(end_time)}\n{text}\n\n"
                subtitles_content.append(srt_entry)
                pause = AudioSegment.silent(duration=random.randint(1500, 2800))
                combined_audio += segment + pause
                current_time_ms += (len(segment) + len(pause))
                os.remove(mp3_path)
            except:
                pass

    if len(combined_audio) > 0:
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


# --- 2. 视频分段逻辑 ---
def create_video(total_duration):
    if total_duration <= 0: return

    all_vids = [os.path.join(SOURCE_VIDEOS_DIR, f) for f in os.listdir(SOURCE_VIDEOS_DIR) if
                f.endswith(('.mp4', '.mov'))]
    if not all_vids:
        print(f"❌ 错误：在 {SOURCE_VIDEOS_DIR} 中未找到预处理后的视频文件！")
        return

    chunk_files = []
    num_chunks = int(np.ceil(total_duration / CHUNK_LIMIT))
    print(f"检测到超长视频，启动分段合成模式：共 {num_chunks} 段...")

    for i in range(num_chunks):
        start_t = i * CHUNK_LIMIT
        end_t = min((i + 1) * CHUNK_LIMIT, total_duration)
        chunk_dur = end_t - start_t
        chunk_path = os.path.join(BASE_DIR, f"temp_part_{i}.mp4")

        print(f"渲染进度: 第 {i + 1}/{num_chunks} 段 ({start_t}s - {end_t}s)...")

        clips = []
        curr_chunk_p = 0
        opened_vfc = []

        while curr_chunk_p < chunk_dur:
            v_path = random.choice(all_vids)
            v = VideoFileClip(v_path, target_resolution=TARGET_RES) # 强制目标分辨率
            opened_vfc.append(v)
            dur = min(CLIP_DUR, v.duration, chunk_dur - curr_chunk_p)
            start = random.uniform(0, max(0, v.duration - dur))
            clip = v.subclip(start, start + dur).without_audio()
            clips.append(clip)
            curr_chunk_p += dur

        visual_chunk = concatenate_videoclips(clips, method="compose")

        with AudioFileClip(FINAL_MP3) as audio_full:
            audio_chunk = audio_full.subclip(start_t, end_t)
            final_chunk = visual_chunk.set_audio(audio_chunk)

            final_chunk.write_videofile(
                chunk_path,
                codec="h264_videotoolbox",
                bitrate=TARGET_BITRATE,
                audio_codec="aac",
                fps=24,
                threads=4,             # 针对 Intel Mac 优化的线程数
                ffmpeg_params=["-movflags", "+faststart"],
                logger="bar"
            )
            audio_chunk.close()

        visual_chunk.close()
        for c in opened_vfc:
            try:
                c.close()
            except:
                pass
        chunk_files.append(chunk_path)

    print("所有分段合成完成，执行最终物理拼接...")
    final_clips = [VideoFileClip(p) for p in chunk_files]
    final_video = concatenate_videoclips(final_clips, method="compose")
    final_video.write_videofile(
        FINAL_VIDEO,
        codec="h264_videotoolbox",
        bitrate=TARGET_BITRATE,
        audio_codec="aac",
        fps=24,
        threads=4,
        ffmpeg_params=["-movflags", "+faststart"],
        logger="bar"
    )

    for c in final_clips: c.close()
    for p in chunk_files:
        try:
            os.remove(p)
        except:
            pass


# --- 3. 运行入口 ---
async def main():
    if not os.path.exists(INPUT_TXT):
        print(f"❌ 找不到输入文稿: {INPUT_TXT}")
        return

    with open(INPUT_TXT, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if len(line.strip()) > 1]
    if not raw_lines: return

    MIN_CHAR_COUNT = 200
    processed_chunks = []
    temp_buffer = []
    current_count = 0
    for line in raw_lines:
        temp_buffer.append(line)
        current_count += len(line)
        if current_count >= MIN_CHAR_COUNT:
            processed_chunks.append("。".join(temp_buffer))
            temp_buffer = []
            current_count = 0
    if temp_buffer: processed_chunks.append("。".join(temp_buffer))

    total_sec = await tts_with_subtitles(processed_chunks)
    create_video(total_sec)

    if os.path.exists(TEMP_DIR):
        for file in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, file))
            except:
                pass
        try:
            os.rmdir(TEMP_DIR)
        except:
            pass

    print("-" * 30 + "\n任务圆满完成！\n" + "-" * 30)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户手动中断。")