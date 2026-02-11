import moviepy as mp
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# --- 核心辅助函数：用 PIL 画出比 OpenCV 更平滑、更高级的文字 ---
def draw_text_advanced(frame, text, font_path, font_size, color, stroke_width=2):
    img_pil = Image.fromarray(frame)
    draw = ImageDraw.Draw(img_pil)
    # 加载字体（请确保路径下有该字体，或使用系统自带路径）
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    # 获取文字尺寸以居中
    w, h = img_pil.size
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = right - left, bottom - top
    position = ((w - text_w) // 2, (h - text_h) // 2)

    # 画描边（增加可读性，突破 60% 的关键）
    for adj in range(-stroke_width, stroke_width + 1):
        for adj2 in range(-stroke_width, stroke_width + 1):
            draw.text((position[0] + adj, position[1] + adj2), text, font=font, fill="black")

    draw.text(position, text, font=font, fill=color)
    return np.array(img_pil)


def create_viral_hook(input_path, output_path, challenge_text, emoji_text):
    video = mp.VideoFileClip(input_path)
    w, h = video.size

    # 定义 Hook 时长（10s 视频建议只给 0.6s - 0.8s）
    hook_dur = 0.7

    def frame_processor(get_frame, t):
        frame = get_frame(t)

        # 1. 视觉唤醒：0.7秒内从模糊到清晰
        if t < hook_dur:
            blur_sigma = int(31 * (1 - t / hook_dur))
            if blur_sigma % 2 == 0: blur_sigma += 1
            frame = cv2.GaussianBlur(frame, (max(1, blur_sigma), max(1, blur_sigma)), 0)

            # 2. 叠加挑衅文案 (99% FAIL...)
            frame = draw_text_advanced(frame, challenge_text, "Arial.ttf", 70, (255, 255, 0))  # 黄色

        # 3. 核心 Emoji/选项：0.2s 开始弹出，带弹性缩放
        if 0.2 < t < 1.5:
            # 弹性缩放逻辑
            rel_t = t - 0.2
            scale = 1.0 + 0.5 * np.exp(-5 * rel_t) * np.cos(10 * rel_t)

            # 这里为了性能，我们在中心区域画 Emoji
            # 在 2.2.1 中，直接在这一帧上覆盖处理后的 Emoji 效果最稳
            frame = draw_text_advanced(frame, emoji_text, "Arial.ttf", int(150 * scale), (255, 255, 255))

        return frame

    # 应用处理 (MoviePy 2.x 推荐用 transform)
    final_video = video.transform(frame_processor)

    # 强制加上高频音效（建议在同一目录下准备一个 pop.mp3）
    # audio = mp.AudioFileClip("pop.mp3").with_start(0.2)
    # final_video = final_video.with_audio(mp.CompositeAudioClip([video.audio, audio]))

    final_video.write_videofile(output_path, fps=video.fps, codec="libx264")


# 调用示例
# create_viral_hook("input.mp4", "output.mp4", "99% FAIL THIS LEVEL", "🦁🍿🎬")

def main():
    create_viral_hook(
        "/Users/huangyun/Desktop/ytb视频/movie_v2/movie/Mac_Viral_11.mp4", "/Users/huangyun/Desktop/ytb视频/movie_v2/movie/output_hooked.mp4",
        "99% FAIL THIS LEVEL!",
        "🍿🦁👑"
    )

if __name__ == "__main__":
    main()
