import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys

if sys.platform == "darwin":
    os.environ["PYTHONIOENCODING"] = "utf-8"

def process_with_ffmpeg(main_path, sub_path, output_path):
    # --- 随机去重参数 ---
    rand_br = round(random.uniform(-0.02, 0.02), 3)
    rand_sat = round(random.uniform(1.0, 1.03), 3)

    # 滤镜逻辑修复：
    # 1. 核心改动：在 [1:v] 后面加上 trim=start=0 确保不从黑帧开始
    # 2. 统一 setpts 逻辑
    filter_complex = (
        f"[0:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,"
        f"eq=brightness={rand_br}:saturation={rand_sat},pad=1080:1080:0:0[main];"
        f"[1:v]fps=30,trim=start=0,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,"
        f"crop=540:1080:68:0,geq=lum='p(X,Y)':a='if(lt(X,68),X/68*255,255)'[sub];"
        f"[main][sub]overlay=540:0:shortest=1[outv]"
    )

    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'videotoolbox',
        '-t', '59',
        '-i', main_path,
        '-ss', '0',               # 【关键】强制副视频从 0 秒解码
        '-stream_loop', '-1',
        '-i', sub_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '0:a',
        '-c:v', 'h264_videotoolbox',
        '-b:v', '4500k',
        '-pix_fmt', 'yuv420p',
        output_path
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        print(f"✅ 修复完成: {os.path.basename(output_path)[:30]}...")
    except subprocess.CalledProcessError as e:
        print(f"❌ 失败: {os.path.basename(main_path)}\n原因: {e.stderr.decode('utf-8', 'ignore')}")

def batch_process(main_dir, sub_dir, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(main_dir, "target")
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    valid_exts = ('.mp4', '.mov', '.avi', '.mkv')
    main_files = [f for f in os.listdir(main_dir) if f.lower().endswith(valid_exts) and not f.startswith('.')]
    sub_files = [f for f in os.listdir(sub_dir) if f.lower().endswith(valid_exts) and not f.startswith('.')]

    if not main_files: return

    tasks = []
    for m_file in main_files:
        main_path = os.path.abspath(os.path.join(main_dir, m_file))
        sub_path = os.path.abspath(os.path.join(sub_dir, random.choice(sub_files)))
        output_path = os.path.abspath(os.path.join(output_dir, f"Fixed_{m_file}"))
        tasks.append((main_path, sub_path, output_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        for t in tasks:
            executor.submit(process_with_ffmpeg, *t)

if __name__ == "__main__":
    MAIN_FOLDER = "/Users/huangyun/Desktop/搬运/A8"
    SUB_FOLDER = "/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"
    batch_process(MAIN_FOLDER, SUB_FOLDER)