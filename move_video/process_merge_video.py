import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
# 确保终端能正确处理 utf-8
if sys.platform == "darwin": # Mac
    os.environ["PYTHONIOENCODING"] = "utf-8"

def process_with_ffmpeg(main_path, sub_path, output_path):
    """
    强制 1:1，处理黑边，时间轴对齐，边缘羽化，且强制限时 59 秒
    """
    # 滤镜逻辑：
    # 1. 主视频 [0:v] 缩放并 pad 成 1080x1080
    # 2. 副视频 [1:v] 裁剪羽化
    filter_complex = (
        "[0:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,pad=1080:1080:0:0[main];"
        "[1:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,crop=540:1080:68:0,"
        "geq=lum='p(X,Y)':a='if(lt(X,68),X/68*255,255)'[sub];"
        "[main][sub]overlay=540:0:shortest=1[outv]"
    )

    cmd = [
        'ffmpeg', '-y',
        '-t', '59',            # 【新增】强制限制输出时长为 59 秒
        '-i', main_path,
        '-stream_loop', '-1',  # 副视频无限循环
        '-i', sub_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '0:a',        # 仅保留主视频音轨
        '-c:v', 'h264_videotoolbox',
        '-b:v', '6000k',
        output_path
    ]

    try:
        # 捕获 stderr 以便调试
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        print(f"✅ 成功: {os.path.basename(main_path)}")
    except subprocess.CalledProcessError as e:
        print(f"❌ 失败: {os.path.basename(main_path)}\n原因: {e.stderr.decode()}")


def batch_process(main_dir, sub_dir, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(main_dir, "target")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    valid_exts = ('.mp4', '.mov', '.avi', '.mkv')
    main_files = [f for f in os.listdir(main_dir) if f.lower().endswith(valid_exts) and not f.startswith('.')]
    sub_files = [f for f in os.listdir(sub_dir) if f.lower().endswith(valid_exts) and not f.startswith('.')]

    if not main_files or not sub_files:
        print("未找到素材。")
        return

    tasks = []
    for m_file in main_files:
        main_path = os.path.abspath(os.path.join(main_dir, m_file))
        sub_path = os.path.abspath(os.path.join(sub_dir, random.choice(sub_files)))
        # 清洗文件名，确保特殊字符不影响导出
        clean_name = "".join([c for c in m_file if c.isalnum() or c in ('.', '_')]).strip()
        output_path = os.path.abspath(os.path.join(output_dir, f"1to1_{clean_name}.mp4"))
        tasks.append((main_path, sub_path, output_path))

    print(f"🚀 Mac 并发合成 (1:1 画布模式)，最大并发: 3")

    with ThreadPoolExecutor(max_workers=3) as executor:
        for t in tasks:
            executor.submit(process_with_ffmpeg, *t)


if __name__ == "__main__":
    # 配置路径
    MAIN_FOLDER = "/Users/huangyun/Desktop/test"
    SUB_FOLDER = "/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"

    batch_process(MAIN_FOLDER, SUB_FOLDER)
