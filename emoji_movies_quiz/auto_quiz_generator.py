import json
import os
import random
import numpy as np

# ================= 修复补丁开始 (Fix for Pillow 10+) =================
import PIL.Image

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
# ================= 修复补丁结束 =================


from moviepy import *


from PIL import Image, ImageDraw, ImageFont

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.audio.AudioClip import CompositeAudioClip

# ================= 音效配置 =================
SFX_TICK = "tick.mp3"
SFX_DING = "success.mp3"

# ================= 配置区域 (Mac Optimized) =================
# JSON_FILE = 'marvel_viral.json'  # 确保你的目录下有这个json文件
JSON_FILE = 'movies_viral.json'  # 确保你的目录下有这个json文件

OUTPUT_PREFIX = 'Mac_Viral_'

# TARGET_FOLDER = 'target/marvel'
TARGET_FOLDER = 'target/movie'

# 视频文字
# 标题，电影
TITLE_FLEXI = "GUESS THE MOVIE"
# TITLE_FLEXI = "Guess the Marvel Hero"

# 背景视频
# 漫威
BG_FOLDER = 'assets/marvel/bg'
# 电影
BG_FOLDER = 'assets/movie/bg'

# 视频参数 (9:16 Shorts)
SCREEN_SIZE = (1080, 1920)
BG_COLOR = (25, 25, 35)  # 深蓝灰背景
TEXT_COLOR = 'white'




# 3. 颜色配置：高对比度
ACCENT_COLOR = '#FFFF00'      # 纯亮黄 (比之前的金色更刺眼)
URGENCY_COLOR = '#FF0000'     # 纯红

# 节奏控制 (黄金3秒法则：极快)
TIME_THINKING = 2.5  # 思考时间
TIME_REVEAL = 1  # 答案展示时间


# === macOS 字体路径配置 ===
# Apple Color Emoji 是 macOS 自带的彩色 Emoji 字体
FONT_PATH_EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
# 备用文字字体
FONT_PATH_TEXT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

if not os.path.exists(FONT_PATH_TEXT):
    FONT_PATH_TEXT = "/System/Library/Fonts/Supplemental/Arial.ttf"


# ==========================================================

def load_data():
    if not os.path.exists(JSON_FILE):
        print(f"❌ 错误：找不到 {JSON_FILE}，请先创建数据文件。")
        return []
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_image_with_pil(text, is_emoji=False, font_size=100, max_width=None):
    """
    使用 PIL 生成图片，专门解决 Mac 上 Emoji 显示和文字渲染问题
    """
    w, h = 1080, 400
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = FONT_PATH_EMOJI if is_emoji else FONT_PATH_TEXT

    try:
        if is_emoji:
            # Mac Emoji 字体通常 index=0
            font = ImageFont.truetype(font_path, font_size, index=0)
        else:
            font = ImageFont.truetype(font_path, font_size)
    except OSError:
        # 如果字体加载失败，使用默认
        font = ImageFont.load_default()

    # 计算文字尺寸 (兼容新旧版 Pillow)
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        # 旧版 Pillow 兼容
        text_w, text_h = draw.textsize(text, font=font)

    # 如果指定了最大宽度且文字超宽，则自动调整字体大小
    if max_width and text_w > max_width:
        scale_factor = max_width / text_w
        adjusted_font_size = int(font_size * scale_factor * 0.8)  # 保留一些边距
        try:
            if is_emoji:
                font = ImageFont.truetype(font_path, adjusted_font_size, index=0)
            else:
                font = ImageFont.truetype(font_path, adjusted_font_size)

            # 重新计算调整后的文字尺寸
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            else:
                text_w, text_h = draw.textsize(text, font=font)
        except OSError:
            # 如果调整失败，继续使用原字体
            pass


    # 修改点
    x = (w - text_w) / 2
    y = (h - text_h) / 2

    # 绘制
    draw.text(((w - text_w) / 2, (h - text_h) / 2), text, font=font, fill=TEXT_COLOR, embedded_color=is_emoji)

    if is_emoji:
        # Emoji 不需要描边，直接画
        draw.text((x, y), text, font=font, fill=TEXT_COLOR, embedded_color=True)
    else:
        # 普通文字：必须加粗黑描边 (Stroke)
        # stroke_width=6 : 描边宽度
        # stroke_fill='black' : 描边颜色
        draw.text((x, y), text, font=font, fill=TEXT_COLOR,
                  stroke_width=8, stroke_fill='black')

    return np.array(img)


def create_question_clip(item, index, total_questions, is_last_one):
    emoji_seq = item['emoji_sequence']
    answer = item['answer']

    # 1. 背景
    # bg = ColorClip(size=SCREEN_SIZE, color=BG_COLOR)
    # 假设你下载了一个叫 comic_bg.mp4 的素材
    bg = get_safe_background(get_random_background(),brightness=0.3)

    # 2. Header
    header_img = create_image_with_pil(f"{TITLE_FLEXI} {index}/{total_questions}", font_size=60)
    header_clip = ImageClip(header_img).with_position(('center', 200))

    # 3. Emoji 核心区
    emoji_img = create_image_with_pil(emoji_seq, is_emoji=True, font_size=160)
    emoji_clip = ImageClip(emoji_img).with_position(('center', 500))

    # 简单的放大动画 (呼吸感)
    # emoji_clip_anim = emoji_clip.resized(lambda t: 1 + 0.05 * t)
    emoji_clip_anim = emoji_clip.resized(lambda t: 1 + 0.03 * np.sin(6 * t))

    # 4. 进度条 - 修复颜色值格式
    bar_width = 900
    bar_height = 20

    # 将十六进制颜色转换为RGB元组
    accent_rgb = tuple(int(ACCENT_COLOR.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))

    bar_clip = ColorClip(size=(bar_width, bar_height), color=accent_rgb).with_position(('center', 1400))

    # 动态缩短宽度 - 修复尺寸为0的问题
    def progress_resize(t):
        new_width = bar_width * (1 - t / TIME_THINKING)
        # 确保尺寸始终大于0，最小为1
        safe_width = max(1, int(new_width))
        return (safe_width, bar_height)

    progress_bar = bar_clip.resized(progress_resize)

    # 5. 答案区域 - 添加最大宽度限制
    if is_last_one:
        # === 互动陷阱 ===
        duration_total = TIME_THINKING + 1.5
        ans_text = "COMMENT YOUR ANSWER!"

        # 为问号设置最大宽度限制
        ans_img = create_image_with_pil("???", is_emoji=False, font_size=150, max_width=800)
        # 为CTA文本设置最大宽度限制
        cta_img = create_image_with_pil(ans_text, font_size=70, max_width=900)

        ans_clip = ImageClip(ans_img).with_position(('center', 1100)).with_start(TIME_THINKING)
        cta_clip = ImageClip(cta_img).with_position(('center', 1250)).with_start(TIME_THINKING)

        final_clips = [bg, header_clip, emoji_clip_anim, progress_bar, ans_clip, cta_clip]

    else:
        # === 普通题目 ===
        duration_total = TIME_THINKING + TIME_REVEAL
        # 为答案文本设置最大宽度限制（例如800像素），字体初始大小为90
        ans_img = create_image_with_pil(answer.upper(), font_size=90, max_width=800)
        ans_clip = ImageClip(ans_img).with_position(('center', 1150)).with_start(TIME_THINKING)

        final_clips = [bg, header_clip, emoji_clip_anim, progress_bar, ans_clip]

    # 修正时序
    progress_bar = progress_bar.with_duration(TIME_THINKING)
    header_clip = header_clip.with_duration(duration_total)
    emoji_clip_anim = emoji_clip_anim.with_duration(duration_total)
    bg = bg.with_duration(duration_total)

    clip = CompositeVideoClip(final_clips, size=SCREEN_SIZE).with_duration(duration_total)

    # === 音频处理层 (Audio Layer) ===
    audio_clips = []

    # 1. 添加倒计时滴答声 (Loop Ticking)
    if os.path.exists(SFX_TICK):
        try:
            tick_clip = AudioFileClip(SFX_TICK)
            tick_count = int(TIME_THINKING)
            for i in range(tick_count):
                audio_clips.append(tick_clip.with_start(i))
        except Exception as e:
            print(f"⚠️ 音频加载失败: {e}")

    # 2. 添加正确/悬念音效
    if os.path.exists(SFX_DING):
        try:
            ding_clip = AudioFileClip(SFX_DING)
            if not is_last_one:
                audio_clips.append(ding_clip.with_start(TIME_THINKING))
        except:
            pass

    # 创建视频复合片段
    video_comp = CompositeVideoClip(final_clips, size=SCREEN_SIZE).with_duration(duration_total)

    # === 将音频合入视频 ===
    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
        final_audio = final_audio.with_duration(duration_total)
        video_comp = video_comp.with_audio(final_audio)

    return video_comp


def get_optimized_batches(data):
    # 将数据按难度分类
    easy = [x for x in data if x['difficulty'] == 'Easy']
    medium = [x for x in data if x['difficulty'] == 'Medium']
    hard = [x for x in data if x['difficulty'] == 'Hard']

    batches = []
    # 尽可能凑出 Easy -> Medium -> Hard 的组合
    # 如果某种难度不够了，就随机填充
    min_len = min(len(easy), len(medium), len(hard))

    for i in range(min_len):
        batch = [easy[i], medium[i], hard[i]]
        batches.append(batch)

    return batches

def create_frosted_card(width, height):
    """生成一个带圆角的半透明白色底板"""
    # 这里的 (255, 255, 255, 30) 表示白色，透明度约 12%
    # 如果想要深色玻璃，用 (0, 0, 0, 150)
    card = Image.new("RGBA", (width, height), (0, 0, 0, 150))
    # 这里可以加圆角逻辑，或者简单点直接用矩形
    return ImageClip(np.array(card))


def get_safe_background(video_path, brightness=0.3):
    """
    生成一个"安全"的动态背景：竖屏 + 压暗
    """
    # 1. 兜底方案：如果没素材，返回纯色
    if not os.path.exists(video_path):
        print(f"⚠️ 背景素材缺失: {video_path}，使用纯色代替")
        return ColorClip(size=(1080, 1920), color=(20, 20, 30))

    try:
        # 2. 加载视频
        clip = VideoFileClip(video_path, audio=False)

        # 3. 强制裁剪为竖屏 (Center Crop)
        # 逻辑：先高度适配，再切宽度
        target_ratio = 1080 / 1920
        current_ratio = clip.w / clip.h

        if current_ratio != target_ratio:
            # 如果高度不够，先拉伸高度到 1920
            if clip.h < 1920:
                clip = clip.resized(height=1920)

            # 使用 fx 调用 crop
            # 注意：这里直接传函数名 crop，不需要 vfx.crop
            clip = clip.with_effects([
                vfx.Resize(height=1920),
                vfx.Crop(x_center=clip.w / 2, y_center=clip.h / 2, width=1080, height=1920),
                vfx.MultiplyColor(brightness)  # 替代 colorx
            ])

        return clip

    except Exception as e:
        print(f"❌ 背景处理出错: {e}，降级为纯色背景")
        return ColorClip(size=(1080, 1920), color=(20, 20, 30))


def get_random_background():
    bg_folder = f"{BG_FOLDER}"
    files = [f for f in os.listdir(bg_folder) if f.endswith(".mp4")]
    if not files:
        return None  # 返回纯色兜底

    selected = random.choice(files)
    return os.path.join(bg_folder, selected)


def main():
    print("🚀 开始制作...")
    data = load_data()

    if not data:
        print("没有数据，请检查 json 文件路径")
        return

    random.shuffle(data)
    QUESTIONS_PER_VIDEO = 3

    batches = get_optimized_batches(data)
    for i, batch in enumerate(batches):
        if len(batch) < QUESTIONS_PER_VIDEO: continue

        print(f"🎬 正在渲染第 {i + 1} 个视频...")
        clips = []

        for idx, item in enumerate(batch):
            is_last = (idx == len(batch) - 1)
            clip = create_question_clip(item, idx + 1, QUESTIONS_PER_VIDEO, is_last)
            clips.append(clip)

        final_video = concatenate_videoclips(clips)

        output_filename = f"./{TARGET_FOLDER}/{OUTPUT_PREFIX}{i + 1}.mp4"
        final_video.write_videofile(
            output_filename,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            threads=4,
            preset='ultrafast'
        )
        print(f"✅ 生成完成: {output_filename}")


if __name__ == "__main__":
    main()