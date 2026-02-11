import moviepy as mp
from moviepy.video.VideoClip import ColorClip, TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
import cv2
import numpy as np


def create_ultra_short_hook(input_path, output_path):
    video = mp.VideoFileClip(input_path)
    w, h = video.size

    # --- 1. 缩短 Hook 时长到 0.5 秒 ---
    hook_duration = 1  # 极速闪击

    # --- 2. 极速进度条 ---
    bar_h, bar_w = 8, int(w * 0.7)

    def make_fast_bar(get_frame, t):
        # 0.3秒内从0冲到100%
        progress = min(t / 0.3, 1.0)
        current_w = int(bar_w * progress)
        img = np.zeros((bar_h, bar_w, 3), dtype=np.uint8) + 40
        img[:, :current_w] = [255, 0, 0]  # 纯红
        return img

    fake_bar = ColorClip(size=(bar_w, bar_h), color=(40, 40, 40))
    fake_bar = (fake_bar.with_duration(hook_duration)
                .with_position(("center", int(h * 0.85)))
                .transform(make_fast_bar))

    # --- 3. 瞬间模糊 (仅 0.2s-0.5s 之间闪烁一下) ---
    def flash_blur(frame, t):
        if 0.3 < t < 0.5:
            return cv2.GaussianBlur(frame, (21, 21), 0)
        return frame

    # --- 4. 组合 ---
    # 修复：使用正确的transform语法
    def apply_flash_blur(get_frame, t):
        frame = get_frame(t)
        return flash_blur(frame, t)

    hook_overlay = (video.subclipped(0, hook_duration)
                    .transform(apply_flash_blur))

    # 叠加进度条
    hook_segment = CompositeVideoClip([hook_overlay, fake_bar])

    # 拼接：前 0.5s 特效 + 后面全部
    final_video = mp.concatenate_videoclips([hook_segment, video.subclipped(hook_duration)])

    final_video.write_videofile(output_path, fps=video.fps, codec="libx264")

def main():
    create_ultra_short_hook("/Users/huangyun/Desktop/ytb视频/movie_v2/movie/Mac_Viral_11.mp4", "/Users/huangyun/Desktop/ytb视频/movie_v2/movie/output_hooked.mp4")

if __name__ == "__main__":
    main()
