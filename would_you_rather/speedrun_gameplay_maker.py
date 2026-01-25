import os
import random
import asyncio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# MoviePy 2.x 导入
from moviepy import (
    VideoFileClip, ImageClip, ColorClip, TextClip,
    CompositeVideoClip, clips_array, AudioFileClip,
    CompositeAudioClip, concatenate_audioclips,
    concatenate_videoclips
)
import moviepy.video.fx as vfx
import edge_tts

# ================= 配置区域 =================
# 总屏幕尺寸
FULL_W, FULL_H = 1080, 1920
# 上半部分尺寸 (WYR 内容区)
TOP_H = 960

COLOR_TOP = (200, 0, 0)
COLOR_BOTTOM = (0, 0, 200)
FONT_PATH = "Impact.ttf"

SFX_TICK = "assets/sfx/tick.mp3"
SFX_BOOM = "assets/sfx/boom.mp3"
TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+40%"  # 语速再快一点，配合跑酷


# ================= 辅助函数 =================

# 1. 随机获取一个游戏片段
def get_random_gameplay_clip(duration):
    game_dir = "assets/gameplay"
    files = [f for f in os.listdir(game_dir) if f.endswith(".mp4")]

    if not files:
        # 如果没素材，返回黑屏兜底
        return ColorClip(size=(FULL_W, FULL_H - TOP_H), color=(0, 0, 0)).with_duration(duration)  # 修复颜色

    video_path = os.path.join(game_dir, random.choice(files))
    clip = VideoFileClip(video_path)

    # 随机截取一段
    if clip.duration > duration:
        start = random.uniform(0, clip.duration - duration - 1)
        clip = clip.subclipped(start, start + duration)
    else:
        clip = clip.with_effects([vfx.Loop(duration=duration)])

    # 强制调整大小并裁剪填充下半屏
    target_h = FULL_H - TOP_H
    clip = clip.with_effects([
        vfx.Resize(height=target_h),
        vfx.Crop(width=FULL_W, height=target_h, x_center=clip.w / 2, y_center=clip.h / 2)
    ])

    return clip.without_audio()  # 游戏静音



# 2. 文字图片生成 (同前)
def create_text_img_pil(text, size, color='white', stroke_color='black'):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 处理颜色值
    if color == 'white':
        color = (255, 255, 255)
    elif color == 'red':
        color = (255, 0, 0)
    elif color == '#FFFF00':
        color = (255, 255, 0)
    elif isinstance(color, str) and color.startswith('#'):
        # 处理十六进制颜色
        hex_color = color.lstrip('#')
        color = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    if stroke_color == 'black':
        stroke_color = (0, 0, 0)

    try:
        font = ImageFont.truetype(FONT_PATH, 90)  # 字号稍微调小适配半屏
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (size[0] - text_w) / 2, (size[1] - text_h) / 2
    draw.text((x, y), text, font=font, fill=color, stroke_width=6, stroke_fill=stroke_color)
    return np.array(img)


# 3. 生成 1/4 屏的小方块 (因为现在红蓝各占 1/4 了)
def create_quarter_clip(img_path, text, color_rgb, is_top_quarter=True):
    """
    生成高度为 TOP_H / 2 (即 480px) 的片段
    """
    h_quarter = TOP_H // 2

    if os.path.exists(img_path):
        img = ImageClip(img_path)
        img = img.with_effects([
            vfx.Resize(height=h_quarter),
            vfx.Crop(width=FULL_W, height=h_quarter, x_center=img.w / 2, y_center=img.h / 2)
        ])
    else:
        img = ColorClip(size=(FULL_W, h_quarter), color=(50, 50, 50))

    tint = ColorClip(size=(FULL_W, h_quarter), color=color_rgb).with_opacity(0.2)

    # 文字位置微调
    txt_arr = create_text_img_pil(text, (FULL_W, 150))
    # 上半区文字靠下，下半区文字靠上
    y_pos = h_quarter - 180 if is_top_quarter else 30
    txt_clip = ImageClip(txt_arr).with_position(('center', y_pos))

    return CompositeVideoClip([img, tint, txt_clip], size=(FULL_W, h_quarter))


# 4. 特效：震动 (只震动上半部分)
def apply_shake(clip, start, duration=0.3):
    # 简单震动实现
    return clip  # 暂时省略复杂震动，保证合成稳定，如需震动参考上一版代码


# ================= 核心逻辑 =================

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(filename)
    return filename


async def create_content_segment(q_data, duration, is_last, temp_id):
    """生成上半部分的 WYR 内容 (尺寸 1080x960)"""

    # 1. 画面 (Red Top, Blue Bottom) -> 现在都在上半屏里
    top = create_quarter_clip(q_data['img_a'], q_data['opt_a'], COLOR_TOP, True)
    bot = create_quarter_clip(q_data['img_b'], q_data['opt_b'], COLOR_BOTTOM, False)
    screen = clips_array([[top], [bot]])  # 组合成 1080x960

    # 分割线
    vs_line = ColorClip(size=(FULL_W, 5), color=(255, 255, 255)).with_position(('center', 'center'))  # 修复颜色

    layers = [screen, vs_line]

    # 冲击时间点
    impact_time = duration * 0.6 if not is_last else 0.5

    # 2. 结果显示 (百分比)
    if not is_last:
        per_a = f"{q_data['per_a']}%"
        per_b = f"{100 - q_data['per_a']}%"
        img_a = create_text_img_pil(per_a, (300, 120), color=(255, 255, 0))  # 修复颜色 '#FFFF00'
        img_b = create_text_img_pil(per_b, (300, 120), color=(255, 255, 0))  # 修复颜色 '#FFFF00'
        # 坐标是相对于 960 高度的
        layers.append(ImageClip(img_a).with_position(('center', 250)).with_start(impact_time))
        layers.append(ImageClip(img_b).with_position(('center', 730)).with_start(impact_time))
    else:
        # 陷阱
        img_bait = create_text_img_pil("???", (300, 120), color=(255, 0, 0))  # 修复颜色 'red'
        img_cta = create_text_img_pil("CHOOSE NOW!", (600, 120), color=(255, 255, 255))  # 修复颜色 'white'
        layers.append(ImageClip(img_bait).with_position('center').with_start(impact_time))
        layers.append(ImageClip(img_cta).with_position(('center', 800)).with_start(impact_time))

    # 3. 白闪特效 (仅上半屏)
    flash = ColorClip(size=(FULL_W, TOP_H), color=(255, 255, 255)) \
        .with_opacity(0.5).with_start(impact_time).with_duration(0.15)
    layers.append(flash)

    return CompositeVideoClip(layers, size=(FULL_W, TOP_H)).with_duration(duration)


async def create_full_video_segment(q_data, duration, is_last, temp_id):
    """将 内容 + 游戏 + 音频 组合"""

    # 1. 生成上半部分内容
    content_clip = await create_content_segment(q_data, duration, is_last, temp_id)

    # 2. 生成下半部分游戏
    gameplay_clip = get_random_gameplay_clip(duration)

    # 3. 垂直拼接 (Top: Content, Bottom: Gameplay)
    full_visual = clips_array([[content_clip], [gameplay_clip]])

    # 4. 音频处理
    audio_tracks = []

    # TTS
    text = f"{q_data['opt_a']} or {q_data['opt_b']}?"
    if is_last: text += " Choose Now!"
    tts_file = f"temp_tts_{temp_id}.mp3"
    await generate_tts(text, tts_file)
    if os.path.exists(tts_file):
        audio_tracks.append(AudioFileClip(tts_file).with_start(0))

    # SFX
    if os.path.exists(SFX_TICK):
        tick = AudioFileClip(SFX_TICK).with_volume_scaled(0.6)
        if tick.duration < duration:
            loops = int(duration / tick.duration) + 1
            tick = concatenate_audioclips([tick] * loops)
        audio_tracks.append(tick.subclipped(0, duration))

    if os.path.exists(SFX_BOOM) and not is_last:
        reveal_time = duration * 0.6
        audio_tracks.append(AudioFileClip(SFX_BOOM).with_start(reveal_time).with_volume_scaled(0.8))

    return full_visual.with_audio(CompositeAudioClip(audio_tracks)), tts_file


def get_day_data(day_idx):
    """获取数据结构，路径自动映射"""
    # 示例数据：Day 1
    # 实际使用时，你可以把 14 天的数据字典放这里
    all_data = {
        1: [  # Day 1: Classic (经典)
            ("RICH", "HANDSOME", 76),
            ("FLY", "INVISIBLE", 64),
            ("SAVE MOM", "SAVE DAD", 0)  # 0 表示不显示结果(陷阱)
        ],
        2: [  # Day 2: Marvel Powers (漫威能力)
            ("IRON SUIT", "CAP SHIELD", 68),
            ("THOR HAMMER", "HULK POWER", 55),
            ("KILL THANOS", "KILL LOKI", 0)
        ],
        3: [  # Day 3: Gaming (游戏)
            ("FREE WIFI", "FREE FOOD", 82),
            ("PLAYSTATION", "XBOX", 60),
            ("UNLIMITED GAMES", "UNLIMITED MONEY", 0)
        ],
        4: [  # Day 4: Horror (恐怖)
            ("ZOMBIES", "GHOSTS", 45),
            ("VAMPIRE", "WEREWOLF", 52),
            ("TRAPPED IN OCEAN", "TRAPPED IN SPACE", 0)
        ],
        5: [  # Day 5: Food (食物)
            ("PIZZA", "BURGER", 51),
            ("COKE", "PEPSI", 70),
            ("ONLY SWEET", "ONLY SALTY", 0)
        ],
        6: [  # Day 6: School (学校)
            ("NO HOMEWORK", "NO EXAMS", 55),
            ("SMARTEST", "POPULAR", 40),
            ("10Y SCHOOL", "10Y PRISON", 0)
        ],
        7: [  # Day 7: Love/Money (人性)
            ("TRUE LOVE", "10 MILLION", 35),
            ("CHEAT", "BE CHEATED", 10),
            ("DATE EX", "DATE BOSS", 0)
        ],
        8: [  # Day 8: Spider-Man Special (蜘蛛侠专场)
            ("MJ", "GWEN STACY", 48),
            ("TOBEY", "TOM HOLLAND", 58),
            ("SAVE SPIDEY", "SAVE IRON MAN", 0)
        ],
        9: [  # Day 9: Marvel vs DC (跨界)
            ("IRON MAN", "BATMAN", 52),
            ("THOR", "SUPERMAN", 45),
            ("JOKER", "THANOS", 0)
        ],
        10: [  # Day 10: Superpowers (超能力)
            ("READ MINDS", "SEE FUTURE", 65),
            ("TELEPORT", "TIME TRAVEL", 72),
            ("STOP TIME", "REWIND TIME", 0)
        ],
        11: [  # Day 11: Harry Potter (哈利波特)
            ("GRYFFINDOR", "SLYTHERIN", 60),
            ("HARRY", "DRACO", 55),
            ("SAVE DOBBY", "SAVE DUMBLEDORE", 0)
        ],
        12: [  # Day 12: Survival (生存)
            ("ZOMBIE APOCALYPSE", "ALIEN INVASION", 42),
            ("FREEZE TO DEATH", "BURN TO DEATH", 50),
            ("HUNT", "BE HUNTED", 0)
        ],
        13: [  # Day 13: Life Inconvenience (生活)
            ("NO PHONE", "NO TV", 20),
            ("NO MUSIC", "NO MOVIES", 30),
            ("TALK TO ANIMALS", "SPEAK ALL LANGS", 0)
        ],
        14: [  # Day 14: The End (终极)
            ("RED PILL", "BLUE PILL", 50),
            ("RESTART LIFE", "SKIP TO END", 80),
            ("WORLD PEACE", "1 BILLION $", 0)
        ]
    }

    if day_idx not in all_data: return None

    raw = all_data[day_idx]
    base = f"assets/speedrun/day{day_idx}"

    return [
        {"opt_a": raw[0][0], "img_a": f"{base}/q1_a.jpg", "opt_b": raw[0][1], "img_b": f"{base}/q1_b.jpg",
         "per_a": raw[0][2]},
        {"opt_a": raw[1][0], "img_a": f"{base}/q2_a.jpg", "opt_b": raw[1][1], "img_b": f"{base}/q2_b.jpg",
         "per_a": raw[1][2]},
        {"opt_a": raw[2][0], "img_a": f"{base}/q3_a.jpg", "opt_b": raw[2][1], "img_b": f"{base}/q3_b.jpg",
         "per_a": raw[2][2]},
    ]



async def main_async(day):
    # 示例数据
    day_data = get_day_data(day)

    print("🚀 正在生成 Subway Surfers 版极速流视频...")

    temp_files = []

    # 生成 3 个片段
    task1 = create_full_video_segment(day_data[0], 3.0, False, "q1")
    task2 = create_full_video_segment(day_data[1], 3.0, False, "q2")
    task3 = create_full_video_segment(day_data[2], 4.0, True, "q3")

    results = await asyncio.gather(task1, task2, task3)
    clips = [r[0] for r in results]
    temp_files = [r[1] for r in results]

    # 拼接
    final_video = concatenate_videoclips(clips, method="compose")

    out_file = f"target/Speedrun_Gameplay_Mix_Day{day}.mp4"
    final_video.write_videofile(out_file, fps=30, codec='libx264', audio_codec='aac', threads=4, preset='ultrafast')

    # 清理
    for f in temp_files:
        if os.path.exists(f): os.remove(f)
    print("✅ 完成！")


def main():
    DAYS_TO_GENERATE = range(1, 15)
    for day in DAYS_TO_GENERATE:
        asyncio.run(main_async(day))


if __name__ == "__main__":
    main()