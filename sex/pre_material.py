import os
import subprocess
import hashlib

# --- 核心配置 ---
TARGET_RES = "1280x720"
FPS = 24
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
    # 1. 路径准备
    output_dir = os.path.join(input_folder, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 2. 获取所有视频文件
    valid_extensions = ('.mp4', '.mov', '.mkv', '.avi', '.flv')
    vids = [f for f in os.listdir(input_folder) if f.lower().endswith(valid_extensions)]

    if not vids:
        print(f"❌ 在目录 {input_folder} 中未找到视频文件。")
        return

    print(f"🚀 启动预处理！目标目录: {output_dir}")
    print(f"配置: 裁剪顶部15%, 缩放至720P, 帧率{FPS}, 使用Mac硬件加速")
    print("-" * 30)

    for i, filename in enumerate(vids):
        input_path = os.path.join(input_folder, filename)

        # 使用 MD5 命名，确保唯一性且方便“追加”模式判断
        file_hash = get_file_md5(input_path)
        output_filename = f"clean_{file_hash}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        # 检查是否已经处理过
        if os.path.exists(output_path):
            print(f"⏩ 跳过 [{i + 1}/{len(vids)}]: {filename} (已存在)")
            continue

        print(f"🔄 处理中 [{i + 1}/{len(vids)}]: {filename}")

        # FFmpeg 滤镜链：
        # crop=iw:ih*0.85:0:ih*0.15 -> 裁掉顶部 15%
        # scale=1280:720:force_original_aspect_ratio=increase -> 保证填满 720P
        # crop=1280:720 -> 居中裁切多余部分，防止黑边
        # fps=24 -> 统一帧率
        filter_str = (
            f"crop=iw:ih*0.85:0:ih*0.15,"
            f"scale={TARGET_RES.replace('x', ':')}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_RES.replace('x', ':')},"
            f"fps={FPS}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-an",  # 移除音频节省空间
            "-vf", filter_str,
            "-c:v", "h264_videotoolbox",  # Mac 硬件加速驱动
            "-b:v", BITRATE,
            "-preset", "p4",  # 质量预设
            output_path
        ]

        try:
            # 运行命令
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"❌ 处理失败 {filename}: {result.stderr}")
            else:
                print(f"✅ 完成: {output_filename}")
        except Exception as e:
            print(f"⚠️ 发生错误: {e}")

    print("-" * 30)
    print(f"✨ 处理结束！所有可用素材已存放至: {output_dir}")


if __name__ == "__main__":
    # 在这里输入你的文件夹路径
    # folder_to_process = input("请输入素材文件夹的完整路径: ").strip()
    folder_to_process = "/Users/huangyun/Desktop/搬运/sex_creative/游戏波"

    if os.path.isdir(folder_to_process):
        process_videos(folder_to_process)
    else:
        print("❌ 路径无效，请检查是否输入正确。")