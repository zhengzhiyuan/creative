import asyncio
import edge_tts
import os
import random
import numpy as np
import PIL.Image
import subprocess
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip

# --- Pillow 兼容性补丁 ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- 核心配置 ---
INPUT_TXT = "/Users/huangyun/git/creative/output/task_老公車禍癱瘓.公公怕我離婚.幫忙乾活…./2.txt"
SOURCE_VIDEOS_DIR = "/Users/huangyun/Desktop/搬运/sex_creative/游戏波"

BASE_DIR = os.path.dirname(INPUT_TXT)
TEMP_DIR = os.path.join(BASE_DIR, "temp_chunks")
FINAL_MP3 = os.path.join(BASE_DIR, "final_refined_voice.mp3")
FINAL_SRT = os.path.join(BASE_DIR, "subtitle.srt")
FINAL_VIDEO = os.path.join(BASE_DIR, "final_video_output.mp4")

VOICE = "zh-CN-XiaoyiNeural"
TARGET_RES = (1920, 1080)
CLIP_DUR = 4  # 每个片段的时长
MAX_CONCURRENT_REQUESTS = 3  # TTS 并发数


# --- 1. TTS 并发逻辑 ---
async def fetch_tts_chunk(semaphore, index, text, voice, temp_dir):
    """单个 TTS 段的异步请求任务"""
    async with semaphore:
        chunk_mp3 = os.path.join(temp_dir, f"{index}.mp3")
        r_rate = f"{random.randint(-20, -15)}%"
        print(f"   [请求中] 第 {index + 1} 段...")

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

    print(f"开始并发 TTS 合成，共 {len(text_list)} 段...")
    tasks = [fetch_tts_chunk(semaphore, i, text, VOICE, TEMP_DIR) for i, text in enumerate(text_list)]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])

    combined_audio = AudioSegment.empty()
    subtitles_content = []
    current_time_ms = 0

    print("音频下载完毕，开始物理拼接...")
    for index, mp3_path, text in results:
        if mp3_path and os.path.exists(mp3_path):
            try:
                segment = AudioSegment.from_mp3(mp3_path)
                start_time = current_time_ms / 1000.0
                end_time = (current_time_ms + len(segment)) / 1000.0

                # 生成 SRT
                srt_entry = f"{index + 1}\n{format_time(start_time)} --> {format_time(end_time)}\n{text}\n\n"
                subtitles_content.append(srt_entry)

                # 随机停顿增加暧昧感
                pause_dur = random.randint(1500, 2800)
                pause = AudioSegment.silent(duration=pause_dur)

                combined_audio += segment + pause
                current_time_ms += (len(segment) + pause_dur)
                os.remove(mp3_path)
            except Exception as e:
                print(f"音频段 {index} 拼接失败: {e}")

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


# --- 2. 视频逻辑 (修复 AttributeError: 'NoneType' 报错) ---
def create_video(total_duration):
    print(f"开始生成视觉画面，目标时长: {total_duration:.2f}s...")
    all_vids = [os.path.join(SOURCE_VIDEOS_DIR, f) for f in os.listdir(SOURCE_VIDEOS_DIR) if
                f.endswith(('.mp4', '.mov'))]

    if not all_vids:
        print(f"错误：素材目录为空。")
        return

    clips = []
    curr = 0
    opened_vfc = []  # 记录打开的文件对象

    try:
        while curr < total_duration:
            v_path = random.choice(all_vids)
            # 关键：不要在这里使用 with 语句，否则 write_videofile 时读取器会被关闭
            v = VideoFileClip(v_path)
            opened_vfc.append(v)

            dur = min(CLIP_DUR, v.duration)
            start = random.uniform(0, max(0, v.duration - dur))

            # 截取并处理画面
            clip = v.subclip(start, start + dur).without_audio()
            clip = clip.resize(height=TARGET_RES[1])
            if clip.w != TARGET_RES[0]:
                clip = clip.set_position("center").on_color(size=TARGET_RES, color=(0, 0, 0))

            clips.append(clip)
            curr += dur

        print(f"片段提取完成 (共 {len(clips)} 段)，开始合并渲染...")
        final_visual = concatenate_videoclips(clips, method="compose").set_duration(total_duration)

        # 绑定音频
        audio_bg = AudioFileClip(FINAL_MP3)
        result = final_visual.set_audio(audio_bg)

        # 写入文件
        result.write_videofile(
            FINAL_VIDEO,
            codec="h264_videotoolbox",  # 使用苹果硬件加速
            bitrate="5000k",  # 指定码率保证清晰度
            audio_codec="aac",
            fps=24
        )
        audio_bg.close()

    finally:
        # 无论成功失败，统一关闭所有打开的文件句柄，释放内存
        print("清理视频句柄...")
        for c in opened_vfc:
            try:
                c.close()
            except:
                pass


# --- 3. 运行入口 ---
async def main():
    if not os.path.exists(INPUT_TXT):
        print(f"错误：找不到文稿 {INPUT_TXT}")
        return

    with open(INPUT_TXT, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if len(line.strip()) > 5]

    if not lines:
        print("错误：文稿为空。")
        return

    # 1. 执行 TTS
    total_sec = await tts_with_subtitles(lines)

    # 2. 执行视频合成
    create_video(total_sec)

    # 3. 清理临时目录
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

    print("-" * 30)
    print(f"任务圆满完成！")
    print(f"视频路径: {FINAL_VIDEO}")
    print(f"字幕路径: {FINAL_SRT}")
    print("-" * 30)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断任务。")