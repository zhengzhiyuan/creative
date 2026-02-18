import os
import sys
import subprocess
import shutil
import math
import asyncio
import edge_tts
from concurrent.futures import ThreadPoolExecutor
from faster_whisper import WhisperModel
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, TextClip
import moviepy.video.fx as vfx
from pydub import AudioSegment


# --- 1. 字体路径配置 (针对 Mac) ---
def get_font():
    # 优先使用苹方，支持多国语言且清晰
    paths = [
        "/System/Library/Fonts/Cache/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf"
    ]
    for p in paths:
        if os.path.exists(p): return p
    return "Arial"


# --- 2. TTS 合成 ---
async def generate_voice_safe(text, lang, output_path):
    voice_map = {'en': 'en-US-ChristopherNeural', 'vi': 'vi-VN-NamMinhNeural', 'zh': 'zh-CN-YunxiNeural'}
    voice = voice_map.get(lang, 'en-US-ChristopherNeural')
    try:
        communicate = edge_tts.Communicate(text, voice, rate="-5%")
        await communicate.save(output_path)
    except:
        AudioSegment.silent(duration=100).export(output_path, format="mp3")


def run_tts_worker(args):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(generate_voice_safe(*args))
    loop.close()


# --- 3. 视频排版逻辑 ---
def adapt_shorts_layout(clip, target_size=(1080, 1920)):
    w, h = clip.size
    # 切掉底部 12% 去除原字幕
    clip_no_sub = clip.cropped(y2=int(h * 0.88))
    # 模糊背景 (缩放法)
    bg = clip_no_sub.resized(width=100).resized(target_size).with_effects([vfx.MultiplyColor(0.4)])
    # 主画面居中
    main_v = clip_no_sub.resized(width=target_size[0])
    final_clip = CompositeVideoClip([bg, main_v.with_position("center")], size=target_size)
    # 偶数尺寸修复
    fw = target_size[0] if target_size[0] % 2 == 0 else target_size[0] - 1
    fh = target_size[1] if target_size[1] % 2 == 0 else target_size[1] - 1
    return final_clip.resized((fw, fh))


# --- 4. 主流水线 ---
async def process_video_pipeline(input_path, target_lang='vi'):
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    temp_dir = f"temp_{base_name}"
    os.makedirs(temp_dir, exist_ok=True)

    # A. 音轨分离
    print("🚀 [1/5] 分离音轨...")
    subprocess.run([sys.executable, "-m", "demucs.separate", "--two-stems=vocals", input_path], capture_output=True)
    vocal_wav = f"separated/htdemucs/{base_name}/vocals.wav"
    bgm_wav = f"separated/htdemucs/{base_name}/no_vocals.wav"

    # B. 极速识别
    print("🎙️ [2/5] Faster-Whisper 识别与翻译...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_gen, _ = model.transcribe(vocal_wav, task="translate")
    segments = list(segments_gen)

    # C. 并行配音
    print(f"⏳ [3/5] 合成配音 ({len(segments)}段)...")
    tts_tasks = [(s.text, target_lang, f"{temp_dir}/s_{i}.mp3") for i, s in enumerate(segments)]
    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(run_tts_worker, tts_tasks)

    # 音频缝合
    video_raw = VideoFileClip(input_path)
    full_vocal = AudioSegment.silent(duration=int(video_raw.duration * 1000))
    for i, s in enumerate(segments):
        p = f"{temp_dir}/s_{i}.mp3"
        if os.path.exists(p):
            seg_audio = AudioSegment.from_file(p)
            full_vocal = full_vocal.overlay(seg_audio[:int((s.end - s.start) * 1000)], position=int(s.start * 1000))
    vocal_final_path = f"{temp_dir}/v_final.wav"
    full_vocal.export(vocal_final_path, format="wav")

    # D. 视频排版与字幕制作
    print("🎬 [4/5] 视频排版与字幕叠加...")
    layout_base = adapt_shorts_layout(video_raw)

    # 生成字幕 Clip 列表
    font_p = get_font()
    subtitle_clips = []
    for s in segments:
        duration = s.end - s.start
        if duration <= 0: continue
        txt = TextClip(
            text=s.text, font=font_p, font_size=55, color='yellow',
            stroke_color='black', stroke_width=2, method='caption',
            size=(layout_base.w * 0.85, None)
        ).with_start(s.start).with_duration(duration).with_position(('center', layout_base.h * 0.72))
        subtitle_clips.append(txt)

    # 合成最终画面 (布局 + 字幕)
    final_video = CompositeVideoClip([layout_base] + subtitle_clips)

    # 二创特效
    final_video = final_video.with_effects([vfx.MirrorX(), vfx.MultiplyColor(1.05)])

    # E. 混音与导出
    print("📦 [5/5] 混音并导出视频...")
    bgm = AudioFileClip(bgm_wav).with_volume_scaled(0.45)
    vocal = AudioFileClip(vocal_final_path).with_volume_scaled(2.2)
    final_video = final_video.with_audio(CompositeAudioClip([bgm, vocal]))

    # 分段导出 (每 59 秒一段)
    total_d = final_video.duration
    for i in range(math.ceil(total_d / 59)):
        start, end = i * 59, min((i + 1) * 59, total_d)
        final_video.subclipped(start, end).write_videofile(
            f"Final_Subbed_{base_name}_P{i + 1}.mp4",
            codec="libx264", audio_codec="aac",
            fps=24, threads=8, preset="ultrafast",
            ffmpeg_params=["-pix_fmt", "yuv420p"]
        )

    video_raw.close()
    shutil.rmtree(temp_dir)
    print("✅ 全部完成！现在你可以检查带字幕的成品了。")


if __name__ == "__main__":
    asyncio.run(process_video_pipeline("test_video_150.mp4", "vi"))