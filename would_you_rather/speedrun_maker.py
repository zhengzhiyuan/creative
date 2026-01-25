import os
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.video.fx import LumContrast

# === MoviePy 2.x 专用导入方式 ===
from moviepy import (
    VideoFileClip,
    ImageClip,
    ColorClip,
    TextClip,
    CompositeVideoClip,
    clips_array,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_audioclips
)
import moviepy.video.fx as vfx

# ================= 配置区域 =================
# 屏幕尺寸
W, H = 1080, 1920

# 颜色配置 (红蓝对决)
COLOR_TOP = (200, 0, 0)  # 深红
COLOR_BOTTOM = (0, 0, 200)  # 深蓝
FONT_PATH = "Impact.ttf"  # 请确保目录下有这个字体文件

# 音效路径
SFX_TICK = "assets/sfx/tick.mp3"
SFX_BOOM = "assets/sfx/boom.mp3"


# ================= 工具函数 =================

def create_text_img_pil(text, size, color='white', stroke_color='black'):
    """
    使用 PIL 生成带描边的文字图片 (比 MoviePy TextClip 更稳定)
    """
    # 创建透明背景
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        # 尝试加载字体，如果失败则使用默认
        font = ImageFont.truetype(FONT_PATH, 100)
    except OSError:
        print(f"⚠️ 警告: 找不到字体 {FONT_PATH}，使用系统默认字体")
        font = ImageFont.load_default()

    # 计算文字居中
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size[0] - text_w) / 2
    y = (size[1] - text_h) / 2

    # 将颜色转换为RGB值
    if color == '#FFFF00':
        color = (255, 255, 0)  # 黄色
    elif color == 'red':
        color = (255, 0, 0)  # 红色
    elif color == 'white':
        color = (255, 255, 255)  # 白色
    elif color == 'black':
        color = (0, 0, 0)  # 黑色
    
    if stroke_color == 'black':
        stroke_color = (0, 0, 0)  # 黑色描边
    elif stroke_color == 'white':
        stroke_color = (255, 255, 255)  # 白色描边

    # 绘制描边
    stroke_width = 8
    draw.text((x, y), text, font=font, fill=color, stroke_width=stroke_width, stroke_fill=stroke_color)

    return np.array(img)


def create_half_clip_v2(img_path, text, color_rgb, is_top=True, duration=3.0):
    """
    生成半屏视频片段 (适配 MoviePy v2)
    """
    h_half = H // 2

    # 1. 加载图片 & 填充半屏
    if os.path.exists(img_path):
        img = ImageClip(img_path)
        # 增加对比度 (1.2) 和 饱和度 (如果不方便调饱和度，至少调对比度)
        img = img.with_effects([vfx.LumContrast(contrast=1.2)])

        # 计算缩放比例以填满区域 (Cover 模式)
        ratio_img = img.w / img.h
        ratio_target = W / h_half

        if ratio_img < ratio_target:
            # 图片太窄，按宽度缩放
            img = img.with_effects([vfx.Resize(width=W)])
        else:
            # 图片太矮，按高度缩放
            img = img.with_effects([vfx.Resize(height=h_half)])

        # 居中裁剪 (MoviePy 2.x 写法)
        img = img.with_effects([vfx.Crop(width=W, height=h_half, x_center=img.w / 2, y_center=img.h / 2)])

    else:
        # 兜底纯色
        img = ColorClip(size=(W, h_half), color=(50, 50, 50))

    # 注意：MoviePy 2.x 的 Resize 特效不支持 lambda 动态缩放 (Zoom)
    # 为了保证代码稳定性，这里去掉了动态 Zoom，改用清晰的静态展示
    # 极速流本身切换很快，不需要 Zoom 也能有冲击力

    # 2. 染色滤镜 (Tint Overlay)
    # 使用半透 ColorClip 覆盖
    tint = ColorClip(size=(W, h_half), color=color_rgb).with_duration(duration).with_opacity(0.2)

    # 3. 文字 (选项名称)
    # 使用 PIL 生成图片再转 ImageClip，避免 v2 TextClip 的各种报错
    txt_arr = create_text_img_pil(text, (W, 200))
    # 调整文字位置：上半部分文字靠下，下半部分文字靠上
    y_pos = h_half - 250 if is_top else 50
    txt_clip = ImageClip(txt_arr).with_position(('center', y_pos))

    # 4. 合成半屏
    return CompositeVideoClip([img, tint, txt_clip], size=(W, h_half))


def create_question_segment_v2(q_data, start_time, duration, is_last_one):
    """生成一道题的完整片段"""

    # 1. 制作上下两半
    top_part = create_half_clip_v2(q_data['img_a'], q_data['opt_a'], COLOR_TOP, True, duration)
    bot_part = create_half_clip_v2(q_data['img_b'], q_data['opt_b'], COLOR_BOTTOM, False, duration)

    # 2. 拼合 (垂直堆叠)
    # clips_array 在 v2 中依然可用
    screen = clips_array([[top_part], [bot_part]])

    # 3. 中间分割线
    vs_bg = ColorClip(size=(W, 10), color=(255, 255, 255)).with_position(('center', 'center'))

    layers = [screen, vs_bg]
    audio_layers = []

    # 4. 结果展示逻辑
    if not is_last_one:
        # === 普通题目：显示百分比 ===
        reveal_time = duration * 0.6  # 比如 3秒题，1.8秒出结果

        per_a = f"{q_data['per_a']}%"
        per_b = f"{100 - q_data['per_a']}%"

        # 生成百分比图片
        img_a = create_text_img_pil(per_a, (400, 150), color='#FFFF00')
        img_b = create_text_img_pil(per_b, (400, 150), color='#FFFF00')

        txt_a = ImageClip(img_a).with_position(('center', 400)).with_start(reveal_time)
        txt_b = ImageClip(img_b).with_position(('center', 1400)).with_start(reveal_time)

        layers.extend([txt_a, txt_b])

        # 音效：Boom
        if os.path.exists(SFX_BOOM):
            boom = AudioFileClip(SFX_BOOM).with_start(reveal_time)
            audio_layers.append(boom)

    else:
        # === 最后一题：互动陷阱 ===
        # 显示 ??? 和 引导语
        img_bait = create_text_img_pil("???", (400, 150), color='red')
        img_cta = create_text_img_pil("CHOOSE NOW!", (800, 150), color='white')

        bait = ImageClip(img_bait).with_position('center').with_start(0.5)
        cta = ImageClip(img_cta).with_position(('center', 1600)).with_start(0.5)

        layers.extend([bait, cta])

    # 5. 组合画面
    # 注意：v2 中 set_duration, set_start 依然可用，但推荐链式调用
    comp = CompositeVideoClip(layers, size=(W, H)).with_start(start_time).with_duration(duration)

    comp = add_flash_effect(comp)

    # 6. 添加倒计时音效 (Tick) - [修复版逻辑]
    if os.path.exists(SFX_TICK):
        try:
            tick = AudioFileClip(SFX_TICK).with_volume_scaled(0.8)

            # === 核心修复：自动循环短音频 ===
            # 如果音频比需要的时长短，就复制拼接，直到够长为止
            if tick.duration < duration:
                # 计算需要循环多少次 (例如 3.0 / 1.46 ≈ 2.05 -> 循环3次)
                n_loops = int(duration / tick.duration) + 1
                # 拼接音频
                tick = concatenate_audioclips([tick] * n_loops)

            # 现在音频足够长了，安全截取
            tick = tick.subclipped(0, duration)

            # 将 tick 加入音频列表
            audio_layers.insert(0, tick)
        except Exception as e:
            print(f"⚠️ 音频处理警告: {e}")

    # 7. 合成音频
    if audio_layers:
        comp_audio = CompositeAudioClip(audio_layers)
        comp = comp.with_audio(comp_audio)



    return comp


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

def add_flash_effect(clip):
    """给片段开头加一个极短的白闪"""
    # 创建一个 0.15秒 的白色片段 - 使用 RGB 值替代字符串
    flash = ColorClip(size=(W, H), color=(255, 255, 255)).with_duration(0.15).with_opacity(0.6)
    # 叠加在原片段开头
    return CompositeVideoClip([clip, flash.with_start(0)])

def main():
    # === 批量生成设置 ===
    # 你可以改为 range(1, 15) 一次生成所有，或者指定某一天
    # DAYS_TO_GENERATE = [1]
    DAYS_TO_GENERATE = range(2, 15)

    print(f"🚀 准备生成 {len(DAYS_TO_GENERATE)} 个极速流视频...")

    for day in DAYS_TO_GENERATE:
        day_data = get_day_data(day)

        # 检查图片是否存在，避免报错
        if not os.path.exists(day_data[0]['img_a']):
            print(f"❌ Day {day} 素材缺失，请检查路径: {day_data[0]['img_a']}")
            continue

        print(f"🎬 正在渲染 Day {day} ...")

        # 极速时间轴 (10秒)
        clip1 = create_question_segment_v2(day_data[0], 0, 3.0, False)
        clip2 = create_question_segment_v2(day_data[1], 3.0, 3.0, False)
        clip3 = create_question_segment_v2(day_data[2], 6.0, 4.0, True)

        final = CompositeVideoClip([clip1, clip2, clip3], size=(W, H)).with_duration(10.0)

        output_filename = f"target/Speedrun_Day{day}.mp4"
        final.write_videofile(
            output_filename,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            threads=4,
            preset='ultrafast'
        )
        print(f"✅ Day {day} 完成！")


if __name__ == "__main__":
    main()