import moviepy as mp
from moviepy.video.VideoClip import ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.tools.drawing import color_gradient
import numpy as np
import cv2

def create_fakeout_hook_v2(input_path, output_path):
    # 1. 加载视频 (2.x 推荐直接使用 mp.VideoFileClip)
    video = mp.VideoFileClip(input_path)
    w, h = video.size

    # --- 2. 创建假的进度条 (Fake Progress Bar) ---
    bar_height = 10
    bar_width_max = int(w * 0.8)
    bar_y_position = int(h * 0.82)

    def make_bar_frame(get_frame, t):
        # 进度条逻辑：0.6秒冲到99%然后卡住
        if t < 0.6:
            progress = t / 0.6 * 0.99
        else:
            progress = 0.99

        current_width = int(bar_width_max * progress)
        # 创建底色
        bar_img = np.zeros((bar_height, bar_width_max, 3), dtype=np.uint8) + 60
        # 填充进度色 (YouTube红: 255, 0, 0)
        bar_img[:, :current_width] = [255, 0, 0]
        return bar_img

    # 2.x 中使用 with_duration 和 with_position
    fake_bar_bg = ColorClip(size=(bar_width_max, bar_height), color=(60, 60, 60))
    fake_bar_bg = (fake_bar_bg
                   .with_duration(1.5)
                   .with_position(("center", bar_y_position)))

    # 应用动态进度逻辑
    dynamic_bar = fake_bar_bg.transform(make_bar_frame)

    # --- 3. 创建报错文字 ---
    # 修复字体问题，使用系统可用字体
    try:
        error_msg = mp.TextClip(
            text="⚠️ Loading Failed. Reconnecting...",
            font_size=35,  # 修复：MoviePy 2.x 使用 font_size 而不是 fontsize
            color='white',
            font="Arial",  # 使用简单字体
            bg_color='black',
            method='caption',
            size=(int(w * 0.8), None)
        ).with_start(0.7).with_duration(0.8).with_position('center')
    except Exception as e:
        print(f"TextClip 报错，请检查 ImageMagick 是否安装: {e}")
        # 如果没有 ImageMagick，可以用一个简单的红色色块代替作为演示
        error_msg = ColorClip(size=(int(w * 0.8), 50), color=(255, 0, 0)).with_start(0.7).with_duration(0.8).with_position(
            'center')

    # --- 4. 模糊滤镜处理 ---
    def apply_blur(get_frame, t):  # 修复：transform 函数需要接受 get_frame 和 t 两个参数
        frame = get_frame(t)
        return cv2.GaussianBlur(frame, (25, 25), 0)

    # 分割视频：前1.5秒模糊，后面正常
    hook_part = video.subclipped(0, 1.5).transform(apply_blur)  # 修复：使用 transform 而不是 image_transform
    main_part = video.subclipped(1.5)  # 修复：使用 subclipped 而不是 subclip

    # 组合前1.5秒的特效层
    hook_overlay = CompositeVideoClip([hook_part, dynamic_bar, error_msg])

    # 最终拼接 (2.x 推荐使用 mp.concatenate_videoclips)
    final_video = mp.concatenate_videoclips([hook_overlay, main_part])

    # 写入文件
    final_video.write_videofile(output_path, fps=video.fps, codec="libx264")

def main():
    # 为了测试，这里只生成 day1
    # 如果要生成全部，改为: for i in range(1, 15): await create_illusion_video(f"day{i}")
    create_fakeout_hook_v2("/Users/huangyun/Desktop/ytb视频/movie_v2/movie/Mac_Viral_11.mp4", "/Users/huangyun/Desktop/ytb视频/movie_v2/movie/output_hooked.mp4")


if __name__ == "__main__":
    main()
