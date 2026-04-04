import asyncio
import edge_tts
import os
import random
import numpy as np
from pydub import AudioSegment

# --- 核心配置 ---
INPUT_TXT = "/Users/huangyun/git/creative/output/task_老公車禍癱瘓.公公怕我離婚.幫忙乾活…./1.txt"
BASE_DIR = os.path.dirname(INPUT_TXT)
TEMP_DIR = os.path.join(BASE_DIR, "temp_chunks")
FINAL_MP3 = os.path.join(BASE_DIR, "final_refined_voice.mp3")

# --- 女性配音库 (两性赛道精选) ---
# 选项1: zh-CN-XiaoyiNeural (知性、情感厚重，适合婆媳/背叛/纠结类)
# 选项2: zh-CN-XiaoxiaoNeural (温柔、全能，最稳的选择)
# 选项3: zh-CN-XiaozhenNeural (生活化、亲切，像邻家故事)
VOICE = "zh-CN-XiaoyiNeural"

MAX_CHARS = 1000


# --- 逻辑 1：生成独一无二的随机底噪 (去AI指纹) ---
def generate_unique_fingerprint(duration_ms):
    print(f"正在生成唯一物理底噪 (时长: {duration_ms / 1000:.2f}s)...")
    sample_rate = 44100
    num_samples = int((duration_ms / 1000 + 2) * sample_rate)

    # 纯随机数学序列，物理层面不重复
    samples = np.random.uniform(-1, 1, num_samples)
    samples_int16 = (samples * 32767).astype(np.int16)

    return AudioSegment(
        samples_int16.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    )


# --- 逻辑 2：慢速 TTS 合成 (增加情感厚度) ---
async def tts_chunk_refined(text, index):
    file_path = os.path.join(TEMP_DIR, f"part_{index:03d}.mp3")

    # --- 语速深度优化 ---
    # 将语速压在 -20% 到 -15%，让声音变沉稳，解决时间缩水问题
    r_rate = f"{random.randint(-20, -15)}%"
    # 略微降低音调 (-1 到 -3)，让声音听起来更成熟，减少电子音感
    r_pitch = f"{random.randint(-3, -1):+}Hz"

    communicate = edge_tts.Communicate(text, VOICE, rate=r_rate, pitch=r_pitch)
    await communicate.save(file_path)
    return file_path


# --- 逻辑 3：主工作流 ---
async def process_full_audio():
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    if not os.path.exists(INPUT_TXT):
        print(f"找不到输入文件: {INPUT_TXT}")
        return

    with open(INPUT_TXT, "r", encoding="utf-8") as f:
        full_text = f.read()

    # 切分段落
    paragraphs = [p.strip() for p in full_text.split('\n') if len(p.strip()) > 5]
    print(f"文稿解析完成: {len(paragraphs)} 段。使用配音: {VOICE}")

    # 并发合成 (控制在 5 个，保护 Intel Mac)
    semaphore = asyncio.Semaphore(5)

    async def sem_task(p, i):
        async with semaphore:
            return await tts_chunk_refined(p, i)

    tasks = [sem_task(p, i) for i, p in enumerate(paragraphs)]
    audio_files = await asyncio.gather(*tasks)

    print("开始后期处理：注入停顿与物理底噪...")

    # 3. 拼接并加入长停顿
    combined = AudioSegment.empty()
    for file in sorted(audio_files):
        if os.path.exists(file):
            segment = AudioSegment.from_mp3(file)

            # --- 情感化留白 ---
            # 段落间停顿拉长到 1.5s - 2.8s，显著增加总时长
            pause_len = random.randint(1500, 2800)
            pause = AudioSegment.silent(duration=pause_len)

            combined += segment + pause
            os.remove(file)

            # 4. 混入随机物理底噪 (去 AI 指纹)
    unique_noise = generate_unique_fingerprint(len(combined))
    # 噪音压低到极小的背景感 (-55dB)
    bgm_chunk = unique_noise[:len(combined)] - 55
    final_output = combined.overlay(bgm_chunk)

    # 5. 导出成品 (高采样率 + 双声道)
    print("正在导出高品质成品音频...")
    final_output.export(
        FINAL_MP3,
        format="mp3",
        bitrate="192k",
        parameters=["-ar", "44100", "-ac", "2"]
    )

    if os.path.exists(TEMP_DIR):
        os.rmdir(TEMP_DIR)

    print(f"\n" + "=" * 40)
    print(f"【两性故事音频合成完成】")
    print(f"输出文件: {FINAL_MP3}")
    print(f"最终时长预估: 约为原来的 1.25 倍")
    print(f"去AI手段: 极慢语速/动态长停顿/物理随机噪音/声纹微调")
    print("=" * 40)


if __name__ == "__main__":
    asyncio.run(process_full_audio())