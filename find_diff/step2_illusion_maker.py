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
# Mac用户专用 Emoji 路径
EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"

SFX_TICK = "assets/sfx/tick.mp3"
SFX_BOOM = "assets/sfx/boom.mp3"
SFX_MAGIC = "assets/sfx/boom.mp3"

TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+25%"

# ================= 14天 Emoji 数据配置 =================
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
    # 生成透明背景
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 颜色转换逻辑
    if color == 'white':
        color = (255, 255, 255)
    elif color == 'red':
        color = (255, 0, 0)
    elif color == 'yellow':
        color = (255, 255, 0)
    elif color == 'black':
        color = (0, 0, 0)

    if stroke_color == 'white':
        stroke_color = (255, 255, 255)
    elif stroke_color == 'black':
        stroke_color = (0, 0, 0)

    # === 修复点：强制转换为整数，且至少为 1 ===
    valid_font_size = max(10, int(font_size))

    try:
        font = ImageFont.truetype(FONT_PATH, valid_font_size)
    except Exception as e:
        print(f"⚠️ 自定义字体加载失败 ({e})，使用默认字体")
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (size[0] - text_w) / 2, (size[1] - text_h) / 2

    draw.text((x, y), text, font=font, fill=color, stroke_width=6, stroke_fill=stroke_color)
    return np.array(img)


def create_emoji_grid(main, odd, rows=7, cols=6):
    """
    生成 Emoji 矩阵 (修复 invalid pixel size 问题)
    """
    # 背景透明
    img = Image.new("RGBA", (W, 1000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    target_r = random.randint(0, rows - 1)
    target_c = random.randint(0, cols - 1)

    cell_w = W // cols
    cell_h = 1000 // rows

    # === 修复点：强制转为整数 ===
    raw_size = min(cell_w, cell_h) * 0.75
    font_size = max(10, int(raw_size))  # 确保是整数且不小于10

    try:
        # Mac 需要 index=0
        font = ImageFont.truetype(EMOJI_FONT_PATH, font_size, index=0)
    except Exception as e:
        print(f"⚠️ Emoji 字体加载失败: {e} (Size: {font_size})")
        # 尝试备用方案 (不带 index)
        try:
            font = ImageFont.truetype(EMOJI_FONT_PATH, font_size)
        except:
            print("⚠️ 彻底失败，使用默认字体 (可能不显示Emoji)")
            font = ImageFont.load_default()

    for r in range(rows):
        for c in range(cols):
            char = odd if (r == target_r and c == target_c) else main

            # 计算居中坐标
            x = c * cell_w + (cell_w - font_size) / 2
            y = r * cell_h + (cell_h - font_size) / 2

            # 必须 int() 坐标，防止部分系统报错
            draw.text((int(x), int(y)), char, font=font, embedded_color=True, fill='black')

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

    base_img = ImageClip(img_path).with_effects([
        vfx.Resize(height=1920),
        vfx.Crop(width=W, height=H, x_center=W / 2, y_center=H / 2)
    ])

    clip_inverted = base_img.with_effects([vfx.InvertColors()]).with_duration(5.0)
    clip_bw = base_img.with_effects([vfx.BlackAndWhite()]).with_duration(3.0)

    # 红点 (视觉锚点)
    red_dot = (ColorClip(size=(20, 20), color=(255, 0, 0))
               .with_position('center').with_duration(8.0))

    # 指令文字
    txt_instr = (ImageClip(create_text_img_pil("STARE AT THE DOT", (W, 200), color=(255, 255, 0)))
                 .with_position(('center', 300)).with_duration(5.0))

    txt_blink = (ImageClip(create_text_img_pil("DO NOT BLINK!", (W, 200), color=(255, 0, 0)))
                 .with_position(('center', 1500)).with_duration(5.0))

    visual_track = concatenate_videoclips([clip_inverted, clip_bw])
    part1_hook = CompositeVideoClip([visual_track, red_dot, txt_instr, txt_blink]).with_duration(8.0)

    # === Part 2: Emoji 游戏 (8s - 15s) ===

    emoji_data = DAY_CONFIG.get(day_key, {"main": "❓", "odd": "❔", "name": "Unknown"})
    emoji_img = create_emoji_grid(emoji_data['main'], emoji_data['odd'])

    # 游戏背景 (亮白色)
    bg_white = ColorClip(size=(W, H), color=(255, 255, 255)).with_duration(7.0)

    # Emoji 矩阵 (透明背景叠加在白底上)
    emoji_clip = ImageClip(emoji_img).with_position('center').with_duration(7.0)
    # 简单的呼吸动画
    emoji_clip = emoji_clip.with_effects([vfx.Resize(lambda t: 1 + 0.02 * t)])

    # 文字
    txt_game = (
        ImageClip(create_text_img_pil("FIND THE ODD ONE", (W, 200), color=(0, 0, 0), stroke_color=(255, 255, 255)))
        .with_position(('center', 150)).with_duration(7.0))

    txt_cta = (ImageClip(
        create_text_img_pil("SUBSCRIBE IF YOU FOUND IT", (W, 200), color=(255, 0, 0), stroke_color=(255, 255, 255)))
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

    # SFX: Tick (倒计时) - 已加入防止崩溃的循环逻辑
    if os.path.exists(SFX_TICK):
        try:
            tick_source = AudioFileClip(SFX_TICK)
            target_dur = 7.0
            if tick_source.duration < target_dur:
                n_loops = int(target_dur / tick_source.duration) + 1
                tick_looped = concatenate_audioclips([tick_source] * n_loops)
            else:
                tick_looped = tick_source

            tick = tick_looped.subclipped(0, target_dur) \
                .with_start(8.0) \
                .with_volume_scaled(0.5)
            audio_tracks.append(tick)
        except Exception as e:
            print(f"⚠️ Tick 音效处理错误: {e}")

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
    # 为了测试，这里只生成 day1
    # 如果要生成全部，改为: for i in range(1, 15): await create_illusion_video(f"day{i}")
    await create_illusion_video("day1")


if __name__ == "__main__":
    asyncio.run(main())