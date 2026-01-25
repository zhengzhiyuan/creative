import os
import random
import asyncio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# === MoviePy 2.x 专用导入 ===
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
COLOR_TOP = (200, 0, 0)  # 深红
COLOR_BOTTOM = (0, 0, 200)  # 深蓝
FONT_PATH = "Impact.ttf"  # 字体路径

# 音效路径
SFX_TICK = "assets/sfx/tick.mp3"
SFX_BOOM = "assets/sfx/boom.mp3"

# TTS 配置 (快语速)
TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+35%"


# ================= 视觉工具函数 =================

def create_text_img_pil(text, size, color='white', stroke_color='black'):
    """使用 PIL 生成高质量描边文字"""
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
        font = ImageFont.truetype(FONT_PATH, 100)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (size[0] - text_w) / 2, (size[1] - text_h) / 2
    draw.text((x, y), text, font=font, fill=color, stroke_width=8, stroke_fill=stroke_color)
    return np.array(img)


def create_half_clip(img_path, text, color_rgb, is_top=True):
    """生成半屏画面 (带颜色滤镜)"""
    h_half = H // 2

    # 1. 加载图片 & 填充
    if os.path.exists(img_path):
        img = ImageClip(img_path)
        # 模拟 Cover 模式缩放
        ratio_img = img.w / img.h
        ratio_target = W / h_half
        if ratio_img < ratio_target:
            img = img.with_effects([vfx.Resize(width=W)])
        else:
            img = img.with_effects([vfx.Resize(height=h_half)])
        # 居中裁剪
        img = img.with_effects([vfx.Crop(width=W, height=h_half, x_center=img.w / 2, y_center=img.h / 2)])
    else:
        # 兜底纯色
        print(f"⚠️ 图片缺失: {img_path}")
        img = ColorClip(size=(W, h_half), color=(50, 50, 50))

    # 2. 染色滤镜 (Tint)
    tint = ColorClip(size=(W, h_half), color=color_rgb).with_opacity(0.2)

    # 3. 文字
    txt_arr = create_text_img_pil(text, (W, 200))
    y_pos = h_half - 250 if is_top else 50
    txt_clip = ImageClip(txt_arr).with_position(('center', y_pos))

    return CompositeVideoClip([img, tint, txt_clip], size=(W, h_half))


# ================= 特效工具函数 (Juice) =================

def create_flash_overlay(start_time, duration=0.15):
    """白闪特效图层"""
    return ColorClip(size=(W, H), color=(255, 255, 255)) \
        .with_opacity(0.5) \
        .with_start(start_time) \
        .with_duration(duration)


def apply_shake_effect(clip, impact_time, duration=0.3, magnitude=20):
    """
    【无黑屏震动】使用 numpy.roll 进行像素平移
    """
    # 1. 先放大 5% 防止边缘黑边
    clip = clip.with_effects([vfx.Resize(1.05)])

    def shake_transform(get_frame, t):
        frame = get_frame(t)
        # 仅在冲击时间内震动
        if impact_time <= t <= impact_time + duration:
            dx = random.randint(-magnitude, magnitude)
            dy = random.randint(-magnitude, magnitude)
            # 循环位移 (效率高且不黑屏)
            frame = np.roll(frame, dy, axis=0)
            frame = np.roll(frame, dx, axis=1)
        return frame

    return clip.transform(shake_transform)


# ================= 核心生成逻辑 =================

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(filename)
    return filename


async def create_segment(q_data, duration, is_last, temp_id):
    """生成单个问题片段 (含画面、TTS、音效、特效)"""

    # 1. 基础画面合成
    top = create_half_clip(q_data['img_a'], q_data['opt_a'], COLOR_TOP, True)
    bot = create_half_clip(q_data['img_b'], q_data['opt_b'], COLOR_BOTTOM, False)
    screen = clips_array([[top], [bot]])

    vs_line = ColorClip(size=(1920, 10), color=(255, 255, 255)).with_position(('center', 'center'))  # 修复颜色

    layers = [screen, vs_line]
    audio_tracks = []

    # 确定冲击时间点 (Impact Time)
    impact_time = duration * 0.6 if not is_last else 0.5

    # 2. TTS 生成
    # 文案: "Option A or Option B?" / "Option A or Option B? Choose Now!"
    text = f"{q_data['opt_a']} or {q_data['opt_b']}?"
    if is_last: text += " Choose Now!"

    tts_file = f"temp_tts_{temp_id}.mp3"
    await generate_tts(text, tts_file)

    if os.path.exists(tts_file):
        tts = AudioFileClip(tts_file).with_start(0)
        # 防止 TTS 超过视频长度
        if tts.duration > duration: tts = tts.subclipped(0, duration)
        audio_tracks.append(tts)

    # 3. 结果/陷阱展示
    if not is_last:
        # 显示百分比
        per_a = f"{q_data['per_a']}%"
        per_b = f"{100 - q_data['per_a']}%"
        img_a = create_text_img_pil(per_a, (400, 150), color='#FFFF00')
        img_b = create_text_img_pil(per_b, (400, 150), color='#FFFF00')

        layers.append(ImageClip(img_a).with_position(('center', 400)).with_start(impact_time))
        layers.append(ImageClip(img_b).with_position(('center', 1400)).with_start(impact_time))

        # Boom 音效
        if os.path.exists(SFX_BOOM):
            boom = AudioFileClip(SFX_BOOM).with_start(impact_time).with_volume_scaled(0.8)
            audio_tracks.append(boom)
    else:
        # 最后一题陷阱
        img_bait = create_text_img_pil("???", (400, 150), color='red')
        img_cta = create_text_img_pil("CHOOSE NOW!", (800, 150), color='white')

        layers.append(ImageClip(img_bait).with_position('center').with_start(impact_time))
        layers.append(ImageClip(img_cta).with_position(('center', 1600)).with_start(impact_time))

    # 4. 加入白闪 (Flash)
    layers.append(create_flash_overlay(impact_time))

    # 5. 初步合成
    comp = CompositeVideoClip(layers, size=(W, H)).with_duration(duration)

    # 6. 加入震动 (Shake) - 对整体应用
    comp = apply_shake_effect(comp, impact_time, duration=0.3)

    # 7. 加入 Tick 倒计时 (循环填补)
    if os.path.exists(SFX_TICK):
        tick = AudioFileClip(SFX_TICK).with_volume_scaled(0.6)
        if tick.duration < duration:
            loops = int(duration / tick.duration) + 1
            tick = concatenate_audioclips([tick] * loops)
        tick = tick.subclipped(0, duration)
        audio_tracks.insert(0, tick)

    # 8. 合成音频
    if audio_tracks:
        comp = comp.with_audio(CompositeAudioClip(audio_tracks))

    return comp, tts_file


# ================= 主程序 =================

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


async def main_async(DAY):
    print(f"🚀 开始生成 Day {DAY} 极速流视频...")

    data = get_day_data(DAY)
    if not data:
        print("❌ 没有找到数据")
        return

    # 并发生成 3 个片段
    # Q1: 3s | Q2: 3s | Q3: 4s (最后一题稍微长一点让用户反应)
    tasks = [
        create_segment(data[0], 3.0, False, "q1"),
        create_segment(data[1], 3.0, False, "q2"),
        create_segment(data[2], 4.0, True, "q3")
    ]

    results = await asyncio.gather(*tasks)

    clips = [r[0] for r in results]
    temp_files = [r[1] for r in results]

    # 线性拼接 (保证音画同步)
    final_video = concatenate_videoclips(clips, method="compose")

    out_file = f"target/Speedrun_Day{DAY}_v3.mp4"
    final_video.write_videofile(
        out_file,
        fps=30,
        codec='libx264',
        audio_codec='aac',
        threads=4,
        preset='ultrafast'
    )

    # 清理临时 TTS 文件
    for f in temp_files:
        if os.path.exists(f): os.remove(f)

    print(f"✅ 搞定！输出文件: {out_file}")


def main():
    DAYS_TO_GENERATE = range(1, 15)
    for day in DAYS_TO_GENERATE:
        asyncio.run(main_async(day))


if __name__ == "__main__":
    main()