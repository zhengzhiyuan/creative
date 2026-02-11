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
    强制 1:1 输出，针对 Mac VideoToolbox 加速
    """
    # 逻辑重新计算：
    # 1. 主视频(0:v) 缩放至 608x1080，然后 pad 成 1080x1080 的画布，位置在(0,0)
    # 2. 副视频(1:v) 缩放至 608x1080，裁剪掉左边 68px，剩下 540px
    # 3. 副视频左侧做 68px 羽化
    # 4. 将副视频叠在画布的 x=472 (即 1080-608) 位置，确保重叠 68px

    # 精准坐标计算：
    # [main] 占 0-608 像素
    # [sub] 裁剪后剩下 540 像素，放在 540 像素位置，刚好填满 540-1080 空间
    # 重叠带出现在 540 到 608 像素之间，宽度正好是 68 像素

    filter_complex = (
        "[0:v]scale=608:1080,setsar=1,setpts=PTS-STARTPTS,pad=1080:1080:0:0[main];"
        "[1:v]scale=608:1080,setsar=1,setpts=PTS-STARTPTS,crop=540:1080:68:0,"
        "geq=lum='p(X,Y)':a='if(lt(X,68),X/68*255,255)'[sub];"
        "[main][sub]overlay=540:0:shortest=1[outv]"
    )

    cmd = [
        'ffmpeg',
        '-y',
        '-i', main_path,
        '-stream_loop', '-1',  # 放在 -i sub_path 之前，表示无限循环该输入
        '-i', sub_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '0:a',
        '-c:v', 'h264_videotoolbox',
        '-b:v', '6000k',
        '-shortest',  # 关键：以主视频时长为基准切断
        output_path
    ]

    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(f"❌ 失败: {os.path.basename(main_path)}\n原因: {result.stderr.decode()}")
        else:
            print(f"✅ 成功: {os.path.basename(main_path)}")
    except Exception as e:
        print(f"❌ 系统错误: {e}")


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
