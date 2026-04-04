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
INPUT_TXT = "/Users/huangyun/git/creative/output1/task_老公車禍癱瘓/final.txt"
SOURCE_VIDEOS_DIR = "/Users/huangyun/Desktop/搬运/sex_creative/游戏波"

BASE_DIR = os.path.dirname(INPUT_TXT)
TEMP_DIR = os.path.join(BASE_DIR, "temp_chunks")
FINAL_MP3 = os.path.join(BASE_DIR, "final_refined_voice.mp3")
FINAL_SRT = os.path.join(BASE_DIR, "subtitle.srt")
FINAL_VIDEO = os.path.join(BASE_DIR, "final_video_output.mp4")

# 音色建议：zh-CN-ShuoslyNeural (成熟知性), zh-CN-XiaoxiaoNeural (情感细腻)
VOICE = "zh-CN-XiaoxiaoNeural"
TARGET_RES = (1280, 720)  # 720P 对 Intel Mac 更友好
CLIP_DUR = 4
MAX_CONCURRENT_REQUESTS = 3


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

                # 增加段落间停顿
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


# --- 2. 视频逻辑 ---
def create_video(total_duration):
    if total_duration <= 0:
        print("❌ 错误：音频时长为0，取消视频生成。请检查网络或TTS配置。")
        return

    print(f"开始生成视觉画面，目标时长: {total_duration:.2f}s...")
    all_vids = [os.path.join(SOURCE_VIDEOS_DIR, f) for f in os.listdir(SOURCE_VIDEOS_DIR) if
                f.endswith(('.mp4', '.mov'))]

    if not all_vids:
        print("错误：素材目录为空。")
        return

    clips = []
    curr = 0
    opened_vfc = []

    try:
        while curr < total_duration:
            v_path = random.choice(all_vids)
            v = VideoFileClip(v_path)
            opened_vfc.append(v)

            dur = min(CLIP_DUR, v.duration)
            start = random.uniform(0, max(0, v.duration - dur))

            clip = v.subclip(start, start + dur).without_audio()

            # 自动裁切与缩放
            h = clip.h
            clip = clip.crop(y1=int(h * 0.15), y2=h)
            clip = clip.resize(height=TARGET_RES[1])

            if clip.w != TARGET_RES[0]:
                clip = clip.set_position("center").on_color(size=TARGET_RES, color=(0, 0, 0))

            clips.append(clip)
            curr += dur

        print(f"片段提取完成 (共 {len(clips)} 段)，开始合并渲染...")
        final_visual = concatenate_videoclips(clips, method="compose").set_duration(total_duration)

        audio_bg = AudioFileClip(FINAL_MP3)
        result = final_visual.set_audio(audio_bg)

        result.write_videofile(
            FINAL_VIDEO,
            codec="h264_videotoolbox",
            bitrate="5000k",
            audio_codec="aac",
            fps=24,
            threads=4
        )
        audio_bg.close()

    finally:
        print("清理资源句柄...")
        for c in opened_vfc:
            try:
                c.close()
            except:
                pass


# --- 3. 运行入口 (300字智能合并) ---
async def main():
    if not os.path.exists(INPUT_TXT):
        print(f"错误：找不到文稿 {INPUT_TXT}")
        return

    # 读取原始行
    with open(INPUT_TXT, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if len(line.strip()) > 1]

    if not raw_lines:
        print("错误：文稿内容不足。")
        return

    # --- 智能合并逻辑 ---
    MIN_CHAR_COUNT = 200
    processed_chunks = []
    temp_buffer = []
    current_count = 0

    for line in raw_lines:
        temp_buffer.append(line)
        current_count += len(line)

        # 达到阈值进行打包
        if current_count >= MIN_CHAR_COUNT:
            # 使用句号连接，确保 AI 朗读有自然停顿
            full_text = "。".join(temp_buffer)
            processed_chunks.append(full_text)
            temp_buffer = []
            current_count = 0

    # 边界处理：处理最后剩余不足300字的文本
    if temp_buffer:
        processed_chunks.append("。".join(temp_buffer))

    print(f"📥 原始行数: {len(raw_lines)}")
    print(f"📦 合并后 TTS 请求总段数: {len(processed_chunks)}")

    if not processed_chunks:
        print("错误：无有效合成文本内容。")
        return

    # 1. 执行 TTS
    total_sec = await tts_with_subtitles(processed_chunks)

    # 2. 执行视频合成
    create_video(total_sec)

    # 3. 清理临时文件
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
    print(f"视频存储: {FINAL_VIDEO}")
    print("-" * 30)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户手动中断任务。")