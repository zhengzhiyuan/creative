import os
import random
import asyncio
import edge_tts
import numpy as np  # 新增此行
from PIL import Image, ImageDraw, ImageFont

# === MoviePy 2.x 导入 ===
from moviepy import (
    VideoFileClip, ImageClip, ColorClip, TextClip,
    CompositeVideoClip, clips_array, AudioFileClip,
    CompositeAudioClip, concatenate_audioclips,
    concatenate_videoclips  # <--- 核心修复：必须用这个
)
import moviepy.video.fx as vfx

# ================= 配置区域 =================
W, H = 1080, 1920
COLOR_TOP = (200, 0, 0)
COLOR_BOTTOM = (0, 0, 200)
FONT_PATH = "Impact.ttf"

SFX_TICK = "assets/sfx/tick.mp3"
SFX_BOOM = "assets/sfx/boom.mp3"

# === TTS 配置 (关键迭代) ===
# 推荐声音:
# "en-US-ChristopherNeural" (男声，类似电影解说)
# "en-US-AnaNeural" (女声，清晰)
TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+35%"  # 语速加速 35%，制造紧迫感


# ================= 工具函数 =================

# ... (create_text_img_pil 和 create_half_clip_v2 保持不变，直接复用 v2 的代码) ...
# 为了节省篇幅，这里省略这两个视觉函数的代码，请确保它们在你的文件中
def create_text_img_pil(text, size, color='white', stroke_color='black'):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, 100)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (size[0] - text_w) / 2, (size[1] - text_h) / 2
    draw.text((x, y), text, font=font, fill=color, stroke_width=8, stroke_fill=stroke_color)
    return np.array(img)


def create_half_clip_v2(img_path, text, color_rgb, is_top=True):
    h_half = H // 2
    if os.path.exists(img_path):
        img = ImageClip(img_path)

        ratio_img = img.w / img.h
        ratio_target = W / h_half
        if ratio_img < ratio_target:
            img = img.with_effects([vfx.Resize(width=W)])
        else:
            img = img.with_effects([vfx.Resize(height=h_half)])
        img = img.with_effects([vfx.Crop(width=W, height=h_half, x_center=img.w / 2, y_center=img.h / 2)])
        # 色彩增强 (V1.5 迭代)
        img = img.with_effects([vfx.LumContrast(contrast=1.2)]) # 需确认MoviePy版本是否支持此写法
    else:
        img = ColorClip(size=(W, h_half), color=(50, 50, 50))

    tint = ColorClip(size=(W, h_half), color=color_rgb).with_opacity(0.2)
    txt_arr = create_text_img_pil(text, (W, 200))
    y_pos = h_half - 250 if is_top else 50
    txt_clip = ImageClip(txt_arr).with_position(('center', y_pos))
    return CompositeVideoClip([img, tint, txt_clip], size=(W, h_half))


# ================= 核心异步逻辑 =================

async def generate_tts_audio(text, filename):
    """使用 Edge-TTS 生成加速语音"""
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(filename)
    return filename


async def create_question_segment_v3(q_data, start_time, duration, is_last_one, temp_id):
    """
    生成单题片段 (包含 TTS)
    temp_id: 用于区分临时文件
    """
    # 1. 画面生成 (同 v2)
    top_part = create_half_clip_v2(q_data['img_a'], q_data['opt_a'], COLOR_TOP, True)
    bot_part = create_half_clip_v2(q_data['img_b'], q_data['opt_b'], COLOR_BOTTOM, False)
    screen = clips_array([[top_part], [bot_part]])

    # 白闪特效 (Visual Flash)
    flash = ColorClip(size=(W, H), color=(255, 255, 255)).with_duration(0.15).with_opacity(0.5).with_start(0)

    vs_bg = ColorClip(size=(1920, 10), color=(255, 255, 255)).with_position(('center', 'center'))
    layers = [screen, vs_bg, flash]
    audio_layers = []

    # 2. TTS 生成 (新增!)
    # 文案逻辑: "Option A or Option B?"
    tts_text = f"{q_data['opt_a']} or {q_data['opt_b']}?"
    if is_last_one:
        tts_text += " Choose Now!"

    tts_filename = f"temp_tts_{temp_id}.mp3"
    await generate_tts_audio(tts_text, tts_filename)

    if os.path.exists(tts_filename):
        tts_clip = AudioFileClip(tts_filename).with_start(0)  # 一开始就读
        # 确保 TTS 不会超过视频片段时长 (虽然加速后一般很短)
        if tts_clip.duration > duration:
            tts_clip = tts_clip.subclipped(0, duration)
        audio_layers.append(tts_clip)

    # 3. 结果展示 (同 v2)
    if not is_last_one:
        reveal_time = duration * 0.6
        per_a = f"{q_data['per_a']}%"
        per_b = f"{100 - q_data['per_a']}%"

        img_a = create_text_img_pil(per_a, (400, 150), color='#FFFF00')
        img_b = create_text_img_pil(per_b, (400, 150), color='#FFFF00')

        txt_a = ImageClip(img_a).with_position(('center', 400)).with_start(reveal_time)
        txt_b = ImageClip(img_b).with_position(('center', 1400)).with_start(reveal_time)
        layers.extend([txt_a, txt_b])

        if os.path.exists(SFX_BOOM):
            boom = AudioFileClip(SFX_BOOM).with_start(reveal_time).with_volume_scaled(0.8)
            audio_layers.append(boom)
    else:
        # 最后一题陷阱
        # 建议使用之前说的 "assets/ui/question_marks.png" 替代代码画图
        img_bait = create_text_img_pil("???", (400, 150), color='red')
        img_cta = create_text_img_pil("CHOOSE NOW!", (800, 150), color='white')
        bait = ImageClip(img_bait).with_position('center').with_start(0.5)
        cta = ImageClip(img_cta).with_position(('center', 1600)).with_start(0.5)
        layers.extend([bait, cta])

    # 4. 合成片段
    comp = CompositeVideoClip(layers, size=(W, H)).with_start(start_time).with_duration(duration)

    # 5. 音效混合 (TTS + Tick)
    if os.path.exists(SFX_TICK):
        tick = AudioFileClip(SFX_TICK).with_volume_scaled(0.6)  # 稍微调小Tick，凸显人声
        if tick.duration < duration:
            n_loops = int(duration / tick.duration) + 1
            tick = concatenate_audioclips([tick] * n_loops)
        tick = tick.subclipped(0, duration)
        audio_layers.insert(0, tick)

    if audio_layers:
        comp = comp.with_audio(CompositeAudioClip(audio_layers))

    return comp, tts_filename

def get_day_data(day_index):
    """
    获取第 day_index (1-14) 天的题目数据
    自动生成图片路径
    """
    base_path = f"assets/speedrun/day{day_index}"

    # === 14天题库总表 ===
    all_questions = {
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

    questions = all_questions.get(day_index, [])
    formatted_data = []

    for i, q in enumerate(questions):
        q_idx = i + 1
        formatted_data.append({
            "opt_a": q[0],
            "img_a": os.path.join(base_path, f"q{q_idx}_a.jpg"),
            "opt_b": q[1],
            "img_b": os.path.join(base_path, f"q{q_idx}_b.jpg"),
            "per_a": q[2]
        })

    return formatted_data


async def main_async(day_data, day):
    # 示例数据 (请替换为你的 get_day_data 逻辑)
    print(f"🚀 正在生成带Day{day} TTS 的极速流视频...")

    temp_files = []

    # 并发生成三个片段
    # Q1: 3s | Q2: 3s | Q3: 4s
    task1 = create_question_segment_v3(day_data[0], 0, 3.0, False, "q1")
    task2 = create_question_segment_v3(day_data[1], 3.0, 3.0, False, "q2")
    task3 = create_question_segment_v3(day_data[2], 6.0, 4.0, True, "q3")

    results = await asyncio.gather(task1, task2, task3)

    clips = [res[0] for res in results]
    temp_files = [res[1] for res in results]

    final = concatenate_videoclips(clips, method="compose")

    output_filename = f"target/Day{day}_TTS_Speedrun_v3.mp4"
    final.write_videofile(
        output_filename,
        fps=30,
        codec='libx264',
        audio_codec='aac',
        threads=4,
        preset='ultrafast'
    )

    print("🧹 清理临时音频文件...")
    for f in temp_files:
        if os.path.exists(f):
            os.remove(f)

    print(f"✅ 完成！文件: {output_filename}")


def main():
    DAYS_TO_GENERATE = range(1, 15)
    # DAYS_TO_GENERATE = [1]

    print(f"🚀 准备生成 {len(DAYS_TO_GENERATE)} 个极速流视频...")

    for day in DAYS_TO_GENERATE:
        day_data = get_day_data(day)
        asyncio.run(main_async(day_data,day))


if __name__ == "__main__":
    main()