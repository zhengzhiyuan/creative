import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys

# 确保 Mac 环境编码
if sys.platform == "darwin":
    os.environ["PYTHONIOENCODING"] = "utf-8"


def process_with_ffmpeg(main_path, sub_path, bgm_path, output_path):
    """
    【终极去重生产线】
    - 视频：608x1080 左右分割 + 丝滑羽化 + 随机色彩/亮度微调
    - 音频：1% 音量低通滤波噪音注入（机器能识别，人耳听不见）
    - 性能：Videotoolbox 硬件加速，单片处理约 10-20s
    """

    # 1. 随机去重参数（让每一条视频的哈希值都不同）
    rand_br = round(random.uniform(-0.02, 0.02), 3)
    rand_sat = round(random.uniform(1.0, 1.03), 3)
    # 极低音量：0.008 - 0.012，配合低通滤波，确保噪音不刺耳
    bgm_volume = round(random.uniform(0.008, 0.012), 4)

    # 2. 构造滤镜链
    # [0:v] 主视频，[1:v] 副视频，[2:a] 噪音BGM
    filter_complex = (
        # --- 视频层 ---
        f"[0:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,"
        f"eq=brightness={rand_br}:saturation={rand_sat},pad=1080:1080:0:0[main];"
        f"[1:v]fps=30,trim=start=0,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,"
        f"crop=540:1080:68:0,geq=lum='p(X,Y)':a='if(lt(X,68),X/68*255,255)'[sub];"
        f"[main][sub]overlay=540:0:shortest=1[outv];"
        # --- 音频层 ---
        # lowpass=f=800: 只保留 800Hz 以下的声音（沉闷的背景感），滤掉刺耳高频
        f"[2:a]lowpass=f=800,volume={bgm_volume}[bgm_soft];"
        f"[0:a][bgm_soft]amix=inputs=2:duration=first:dropout_transition=2[outa]"
    )

    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'videotoolbox',  # 硬件解码
        '-t', '59',  # 强制限时防止超长
        '-i', main_path,
        '-ss', '0', '-stream_loop', '-1', '-i', sub_path,
        '-stream_loop', '-1', '-i', bgm_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'h264_videotoolbox',  # 硬件编码
        '-b:v', '4500k',  # 码率适中，兼顾画质与体积
        '-c:a', 'aac', '-b:a', '128k',
        '-pix_fmt', 'yuv420p',  # 兼容所有播放器
        output_path
    ]

    try:
        # 使用 shell=False 是处理包含特殊符号路径的最佳实践
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        print(f"✅ 完成: {os.path.basename(output_path)[:30]}...")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', 'ignore')
        print(f"❌ 失败: {os.path.basename(main_path)}\n原因: {error_msg}")


def batch_process(main_dir, sub_dir, bgm_dir, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(main_dir, "target")
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    # 匹配常见格式
    valid_vids = ('.mp4', '.mov', '.avi', '.mkv')
    valid_auds = ('.mp3', '.m4a', '.wav', '.aac')

    main_files = [f for f in os.listdir(main_dir) if f.lower().endswith(valid_vids) and not f.startswith('.')]
    sub_files = [f for f in os.listdir(sub_dir) if f.lower().endswith(valid_vids) and not f.startswith('.')]
    bgm_files = [f for f in os.listdir(bgm_dir) if f.lower().endswith(valid_auds) and not f.startswith('.')]

    if not main_files or not bgm_files:
        print("❌ 错误：主视频或 BGM 文件夹为空，请检查路径。")
        return

    tasks = []
    for m_file in main_files:
        main_path = os.path.abspath(os.path.join(main_dir, m_file))
        sub_path = os.path.abspath(os.path.join(sub_dir, random.choice(sub_files)))
        bgm_path = os.path.abspath(os.path.join(bgm_dir, random.choice(bgm_files)))
        # 输出文件名
        output_path = os.path.abspath(os.path.join(output_dir, f"Safe_{m_file}"))
        tasks.append((main_path, sub_path, bgm_path, output_path))

    print(f"🚀 生产线启动 | 总任务数: {len(tasks)} | 并发数: 3")

    # Mac 建议并发设为 3，实测能最有效地利用 videotoolbox 硬件单元
    with ThreadPoolExecutor(max_workers=3) as executor:
        for t in tasks:
            executor.submit(process_with_ffmpeg, *t)


if __name__ == "__main__":
    # --- 请在这里配置你的文件夹路径 ---
    MAIN_FOLDER = "/Users/huangyun/Desktop/搬运/A2"
    SUB_FOLDER = "/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"
    BGM_FOLDER = "/Users/huangyun/Desktop/搬运/BGM"

    batch_process(MAIN_FOLDER, SUB_FOLDER, BGM_FOLDER)