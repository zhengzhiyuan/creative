import os
import subprocess
import hashlib

# --- 核心配置 ---
# 修改点：目标分辨率改为 1080P (1920x1080)
TARGET_RES = "1920x1080"
FPS = 24

# 修改点：1080P 建议码率设为 5000k，保证画质的同时兼顾上传速度
BITRATE = "5000k"


def get_file_md5(file_path):
    """计算文件唯一标识，防止重复处理"""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        # 只取前 1MB 算哈希，提速
        chunk = f.read(1024 * 1024)
        hasher.update(chunk)
    return hasher.hexdigest()


def process_videos(input_folder):
    # 修改点 1：输出目录改为 output1080
    output_dir = os.path.join(input_folder, "output1080")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 2. 获取所有视频文件
    valid_extensions = ('.mp4', '.mov', '.mkv', '.avi', '.flv')
    vids = sorted([f for f in os.listdir(input_folder) if f.lower().endswith(valid_extensions) and not f.startswith('.')])

    if not vids:
        print(f"❌ 在目录 {input_folder} 中未找到视频文件。")
        return

    print(f"🚀 启动 1080P 预处理！目标目录: {output_dir}")
    print(f"配置: 裁剪顶部15%, 缩放至1080P, 帧率{FPS}, 使用Mac硬件加速")
    print("-" * 30)

    for i, filename in enumerate(vids):
        input_path = os.path.join(input_folder, filename)

        # 使用 MD5 命名
        file_hash = get_file_md5(input_path)
        output_filename = f"clean_{file_hash}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        # 检查是否已经处理过
        if os.path.exists(output_path):
            print(f"⏩ 跳过 [{i + 1}/{len(vids)}]: {filename} (已存在)")
            continue

        print(f"🔄 处理中 [{i + 1}/{len(vids)}]: {filename}")

        # FFmpeg 滤镜链：修改点：动态适配 1080P 尺寸
        res_pair = TARGET_RES.replace('x', ':')
        filter_str = (
            f"crop=iw:ih*0.85:0:ih*0.15,"
            f"scale={res_pair}:force_original_aspect_ratio=increase,"
            f"crop={res_pair},"
            f"fps={FPS}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-an",  # 移除音频
            "-vf", filter_str,
            "-c:v", "h264_videotoolbox",  # Mac 硬件加速
            "-b:v", BITRATE,
            "-threads", "4",              # 优化点：限制线程，防止 Intel Mac 在处理 1080P 时死机
            "-movflags", "+faststart",     # 优化点：方便 YouTube 预处理
            output_path
        ]

        try:
            # 运行命令
            result = subprocess.run(cmd, capture_output=True, text=True,check=True)
            if result.returncode != 0:
                print(f"❌ 处理失败 {filename}: {result.stderr}")
            else:
                print(f"✅ 完成: {output_filename}")
        except Exception as e:
            print(f"⚠️ 发生错误: {e}")

    print("-" * 30)
    print(f"✨ 处理结束！1080P 素材已存放至: {output_dir}")


if __name__ == "__main__":
    folder_to_process = "/Users/huangyun/Desktop/搬运/sex_creative/游戏波"

    if os.path.isdir(folder_to_process):
        process_videos(folder_to_process)
    else:
        print("❌ 路径无效，请检查是否输入正确。")