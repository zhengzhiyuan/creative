import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys

# 确保终端能正确处理 utf-8
if sys.platform == "darwin":  # Mac
    os.environ["PYTHONIOENCODING"] = "utf-8"


def process_with_ffmpeg(main_path, sub_path, output_path):
    """
    基于回滚版本的稳健版：
    1. 强制 1:1，处理黑边，时间轴对齐，边缘羽化
    2. 强制限时 59 秒
    3. 修正 QuickTime 兼容性 (pix_fmt)
    """
    # 保持你原来的滤镜逻辑不变
    filter_complex = (
        "[0:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,pad=1080:1080:0:0[main];"
        "[1:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,crop=540:1080:68:0,"
        "geq=lum='p(X,Y)':a='if(lt(X,68),X/68*255,255)'[sub];"
        "[main][sub]overlay=540:0:shortest=1[outv]"
    )

    cmd = [
        'ffmpeg', '-y',
        '-t', '59',
        '-i', main_path,
        '-stream_loop', '-1',
        '-i', sub_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '0:a',
        '-c:v', 'h264_videotoolbox',
        '-b:v', '4000k',  # ROI 优化：从 6000k 降到 4000k，体积减小且不伤画质
        '-pix_fmt', 'yuv420p',  # 确保 QuickTime 完美兼容
        output_path
    ]

    try:
        # shell=False 配合列表形式的 cmd 是解决特殊字符文件名的终极方案
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        print(f"✅ 成功出片: {os.path.basename(output_path)[:30]}...")
    except subprocess.CalledProcessError as e:
        print(f"❌ 失败: {os.path.basename(main_path)}\n原因: {e.stderr.decode('utf-8', 'ignore')}")


def batch_process(main_dir, sub_dir, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(main_dir, "target")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    valid_exts = ('.mp4', '.mov', '.avi', '.mkv')
    # 直接获取原文件名，不做 isalnum 清洗
    main_files = [f for f in os.listdir(main_dir) if f.lower().endswith(valid_exts) and not f.startswith('.')]
    sub_files = [f for f in os.listdir(sub_dir) if f.lower().endswith(valid_exts) and not f.startswith('.')]

    if not main_files or not sub_files:
        print("未找到素材。")
        return

    tasks = []
    for m_file in main_files:
        main_path = os.path.abspath(os.path.join(main_dir, m_file))
        sub_path = os.path.abspath(os.path.join(sub_dir, random.choice(sub_files)))

        # --- 关键修改点 ---
        # 不再通过正则清洗文件名，直接使用原文件名 m_file
        # 加上前缀以示区别，并确保 output_path 是合法的绝对路径
        output_path = os.path.abspath(os.path.join(output_dir, f"Shorts_{m_file}"))

        tasks.append((main_path, sub_path, output_path))

    print(f"🚀 并发合成启动 | 并发数: 2")

    # Mac 建议并发设为 2，实测比 3 更稳
    with ThreadPoolExecutor(max_workers=2) as executor:
        for t in tasks:
            executor.submit(process_with_ffmpeg, *t)


if __name__ == "__main__":
    # 配置路径
    MAIN_FOLDER = "/Users/huangyun/Desktop/test"
    SUB_FOLDER = "/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"

    batch_process(MAIN_FOLDER, SUB_FOLDER)