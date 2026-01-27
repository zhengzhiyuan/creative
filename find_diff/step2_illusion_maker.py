import os
import random
import asyncio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# === MoviePy 2.2.1 专用导入 ===
from moviepy import (
    VideoFileClip, ImageClip, ColorClip, TextClip,
    CompositeVideoClip, clips_array, AudioFileClip,
    CompositeAudioClip, concatenate_audioclips,
    concatenate_videoclips
)
import moviepy.video.fx as vfx
import edge_tts

# ================= 配置区域 =================
W, H = 1080, 1920
FONT_PATH = "Impact.ttf"
# Mac用户: "/System/Library/Fonts/Apple Color Emoji.ttc"
# Win用户: "seguiemj.ttf"
EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"

SFX_TICK = "assets/sfx/tick.mp3"
SFX_BOOM = "assets/sfx/boom.mp3"
# 需要一个神奇的音效 (可选，没有也没事)
SFX_MAGIC = "assets/sfx/boom.mp3"

TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+25%"  # 语速适中，因为要引导

# ================= 14天 Emoji 数据配置 =================
# 对应上面的下载素材
DAY_CONFIG = {
    "day1": {"main": "🔴", "odd": "🛑", "name": "Iron Man"},
    "day2": {"main": "🤢", "odd": "🤮", "name": "Hulk"},
    "day3": {"main": "🕷️", "odd": "🐜", "name": "Spidey"},
    "day4": {"main": "⚡", "odd": "✨", "name": "Pikachu"},
    "day5": {"main": "🤡", "odd": "👺", "name": "Joker"},
    "day6": {"main": "🛡️", "odd": "⚙️", "name": "Cap"},
    "day7": {"main": "🖤", "odd": "💣", "name": "Venom"},
    "day8": {"main": "🍄", "odd": "🌹", "name": "Mario"},
    "day9": {"main": "🟨", "odd": "🟧", "name": "SpongeBob"},
    "day10": {"main": "🍌", "odd": "🌙", "name": "Minion"},
    "day11": {"main": "🦇", "odd": "🦅", "name": "Batman"},
    "day12": {"main": "⚔️", "odd": "🔪", "name": "Deadpool"},
    "day13": {"main": "❄️", "odd": "🧊", "name": "Elsa"},
    "day14": {"main": "🚀", "odd": "🛸", "name": "Buzz"}
}


# ================= 辅助函数 =================

def create_text_img_pil(text, size, color='white', font_size=100, stroke_color='black'):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 处理颜色值
    if color == 'white':
        color = (255, 255, 255)
    elif color == 'red':
        color = (255, 0, 0)
    elif color == '#FFFF00':
        color = (255, 255, 0)
    elif color == 'yellow':
        color = (255, 255, 0)
    elif color == 'black':
        color = (0, 0, 0)
    elif isinstance(color, str) and color.startswith('#'):
        # 处理十六进制颜色
        hex_color = color.lstrip('#')
        color = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    if stroke_color == 'black':
        stroke_color = (0, 0, 0)
    elif stroke_color == 'white':
        stroke_color = (255, 255, 255)

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (size[0] - text_w) / 2, (size[1] - text_h) / 2
    draw.text((x, y), text, font=font, fill=color, stroke_width=6, stroke_fill=stroke_color)
    return np.array(img)


def create_emoji_grid(main, odd, rows=7, cols=6):
    """生成 Emoji 矩阵"""
    img = Image.new("RGBA", (W, 1000), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    target_r = random.randint(0, rows - 1)
    target_c = random.randint(0, cols - 1)

    cell_w = W // cols
    cell_h = 1000 // rows
    font_size = int(min(cell_w, cell_h) * 0.8)

    try:
        font = ImageFont.truetype(EMOJI_FONT_PATH, font_size, index=0)
    except:
        font = ImageFont.load_default()

    for r in range(rows):
        for c in range(cols):
            char = odd if (r == target_r and c == target_c) else main
            x = c * cell_w + (cell_w - font_size) / 2
            y = r * cell_h + (cell_h - font_size) / 2
            draw.text((x, y), char, font=font, embedded_color=True)

    return np.array(img)


# ================= 核心生成逻辑 =================

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(filename)
    return filename


async def create_illusion_video(day_key):
    print(f"🎬 正在制作 {day_key} ...")

    assets_dir = f"assets/illusion/{day_key}"
    img_path = os.path.join(assets_dir, "illusion.jpg")

    if not os.path.exists(img_path):
        print(f"❌ 图片缺失: {img_path}")
        return

    # === Part 1: 视觉错觉 Hook (0s - 8s) ===

    # 1. 原始图片处理
    base_img = ImageClip(img_path).with_effects([
        vfx.Resize(height=1920),
        vfx.Crop(width=W, height=H, x_center=W / 2, y_center=H / 2)
    ])

    # 2. 负片层 (Inverted) - 前 5 秒
    clip_inverted = base_img.with_effects([
        vfx.InvertColors()
    ]).with_duration(5.0)

    # 3. 黑白层 (Grayscale) - 后 3 秒
    clip_bw = base_img.with_effects([
        vfx.BlackAndWhite()
    ]).with_duration(3.0)

    # 4. 视觉锚点 (红点)
    red_dot = (ColorClip(size=(20, 20), color=(255, 0, 0))
               .with_position('center').with_duration(8.0))

    # 5. 指令文字
    txt_instr = (ImageClip(create_text_img_pil("STARE AT THE DOT", (W, 200), color=(255, 255, 0)))
                 .with_position(('center', 300)).with_duration(5.0))

    txt_blink = (ImageClip(create_text_img_pil("DO NOT BLINK!", (W, 200), color=(255, 0, 0)))
                 .with_position(('center', 1500)).with_duration(5.0))

    # 6. Hook 合成
    visual_track = concatenate_videoclips([clip_inverted, clip_bw])
    part1_hook = CompositeVideoClip([visual_track, red_dot, txt_instr, txt_blink]).with_duration(8.0)

    # === Part 2: Emoji 游戏 (8s - 15s) ===

    emoji_data = DAY_CONFIG.get(day_key, {"main": "❓", "odd": "❔"})
    emoji_img = create_emoji_grid(emoji_data['main'], emoji_data['odd'])

    # 游戏背景
    bg_white = ColorClip(size=(W, H), color=(255, 255, 255)).with_duration(7.0)  # 修复颜色 'white'

    # Emoji 矩阵
    emoji_clip = ImageClip(emoji_img).with_position('center').with_duration(7.0)
    emoji_clip = emoji_clip.with_effects([vfx.Resize(lambda t: 1 + 0.05 * t)])

    # 文字
    txt_game = (ImageClip(create_text_img_pil("FIND THE ODD ONE", (W, 200), color=(0, 0, 0), stroke_color=(255, 255, 255)))
                .with_position(('center', 150)).with_duration(7.0))

    txt_cta = (ImageClip(create_text_img_pil("SUBSCRIBE IF YOU FOUND IT", (W, 200), color=(255, 0, 0), stroke_color=(255, 255, 255)))
               .with_position(('center', 1600)).with_duration(7.0))

    part2_game = CompositeVideoClip([bg_white, emoji_clip, txt_game, txt_cta]).with_duration(7.0)

    # === Part 3: 音频处理 ===

    audio_tracks = []

    # TTS 1: Hook
    tts_1_file = f"temp_tts_hook_{day_key}.mp3"
    await generate_tts("Stare at the red dot. Focus. Do not blink.", tts_1_file)
    if os.path.exists(tts_1_file):
        audio_tracks.append(AudioFileClip(tts_1_file).with_start(0))

    # TTS 2: Reveal
    tts_2_file = f"temp_tts_reveal_{day_key}.mp3"
    await generate_tts("Now look! Did you see the color?", tts_2_file)
    if os.path.exists(tts_2_file):
        audio_tracks.append(AudioFileClip(tts_2_file).with_start(5.0))

    # TTS 3: Game
    tts_3_file = f"temp_tts_game_{day_key}.mp3"
    await generate_tts(f"Now level 2. Find the odd {emoji_data['name']} emoji!", tts_3_file)
    if os.path.exists(tts_3_file):
        audio_tracks.append(AudioFileClip(tts_3_file).with_start(8.0))

    # SFX: 魔法音效
    if os.path.exists(SFX_MAGIC):
        audio_tracks.append(AudioFileClip(SFX_MAGIC).with_start(5.0))

    # === SFX Tick (自动循环) ===
    if os.path.exists(SFX_TICK):
        try:
            tick_source = AudioFileClip(SFX_TICK)
            target_dur = 7.0  # 我们需要 7 秒的滴答声

            # 核心修复：如果素材太短，就循环拼接
            if tick_source.duration < target_dur:
                n_loops = int(target_dur / tick_source.duration) + 1
                tick_looped = concatenate_audioclips([tick_source] * n_loops)
            else:
                tick_looped = tick_source

            # 截取需要的长度并设置开始时间
            tick = tick_looped.subclipped(0, target_dur) \
                .with_start(8.0) \
                .with_volume_scaled(0.5)

            audio_tracks.append(tick)
        except Exception as e:
            print(f"⚠️ 音频 Tick 处理警告: {e}")

    # === 最终合成 ===
    final_video = concatenate_videoclips([part1_hook, part2_game])
    if audio_tracks:
        final_video = final_video.with_audio(CompositeAudioClip(audio_tracks))

    out_file = f"Illusion_Day_{day_key}.mp4"
    final_video.write_videofile(out_file, fps=30, codec='libx264', audio_codec='aac', threads=4, preset='ultrafast')

    # 清理
    for f in [tts_1_file, tts_2_file, tts_3_file]:
        if os.path.exists(f): os.remove(f)

    print(f"✅ 完成: {out_file}")



async def main():
    # 批量生成
    days = [f"day{i}" for i in range(1, 15)]  # 生成 day1 到 day14

    # 为了测试，这里只生成 day1。如果想全部生成，取消注释下面的循环
    # for day in days:
    #     await create_illusion_video(day)

    await create_illusion_video("day1")


if __name__ == "__main__":
    asyncio.run(main())