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
    【矩阵深度去重版】
    - 视频：608x1080 左右分割 + 丝滑羽化
    - 深度去重：元数据全抹除 + 像素级不可见噪点 + 0.5% 随机变速
    - 音频：1% 低通白噪音 + 音频时间轴位移
    """

    # 1. 更加随机的去重参数 (让每一个视频的指纹都独一无二)
    rand_br = round(random.uniform(-0.03, 0.03), 3)  # 亮度波动
    rand_sat = round(random.uniform(1.0, 1.08), 3)  # 饱和度波动
    rand_cont = round(random.uniform(0.97, 1.03), 3)  # 对比度波动

    # 0.5% 的随机变速 (例如 0.995x 到 1.005x)，肉眼和人耳无法察觉，但哈希全变
    rand_speed = round(random.uniform(0.995, 1.005), 4)
    atempo_val = 1 / rand_speed  # 音频速度需同步

    # 随机噪点种子和音量
    noise_seed = random.randint(1, 999999)
    bgm_volume = round(random.uniform(0.007, 0.015), 4)

    # 2. 构造滤镜链
    filter_complex = (
        # --- 主视频层：变速 + 色彩增强 + 随机噪点注入 ---
        f"[0:v]fps=30,scale=608:1080,setsar=1,"
        f"setpts={rand_speed}*PTS,"
        f"eq=brightness={rand_br}:saturation={rand_sat}:contrast={rand_cont},"
        f"noise=alls={random.randint(1, 2)}:allf=t+u:all_seed={noise_seed},"  # 极细微随机像素干扰
        f"pad=1080:1080:0:0[main];"

        # --- 副视频层：保持常规处理 ---
        f"[1:v]fps=30,scale=608:1080,setsar=1,setpts=PTS-STARTPTS,"
        f"crop=540:1080:68:0,geq=lum='p(X,Y)':a='if(lt(X,68),X/68*255,255)'[sub];"

        # --- 叠加融合 ---
        f"[main][sub]overlay=540:0:shortest=1[outv];"

        # --- 音频层：变速同步 + 噪音混合 ---
        f"[2:a]lowpass=f=800,volume={bgm_volume}[bgm_soft];"
        f"[0:a]atempo={atempo_val}[main_a];"
        f"[main_a][bgm_soft]amix=inputs=2:duration=first:dropout_transition=2[outa]"
    )

    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'videotoolbox',
        '-t', '59',
        '-i', main_path,
        # 随机从原视频开头切掉 0 到 0.5 秒，进一步改变视频指纹
        '-ss', str(round(random.uniform(0, 0.5), 2)),
        '-stream_loop', '-1', '-i', sub_path,
        '-stream_loop', '-1', '-i', bgm_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '[outa]',
        '-map_metadata', '-1',  # 【核心】抹除原始设备、GPS、时间等所有元数据
        '-c:v', 'h264_videotoolbox',
        '-b:v', '4800k',
        '-c:a', 'aac', '-b:a', '128k',
        '-pix_fmt', 'yuv420p',
        output_path
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        print(f"✅ 处理成功: {os.path.basename(output_path)}")
    except subprocess.CalledProcessError as e:
        print(f"❌ 失败: {os.path.basename(main_path)}\n原因: {e.stderr.decode('utf-8', 'ignore')}")


def batch_process(main_dir, sub_dir, bgm_dir, output_dir=None):
    # 增加路径存在性检查，防止崩溃
    for d in [main_dir, sub_dir, bgm_dir]:
        if not os.path.exists(d):
            print(f"❌ 错误：路径不存在 -> {d}")
            return # 发现路径错误直接退出，不跑后面的逻辑

    if output_dir is None:
        output_dir = os.path.join(main_dir, "target")
    if not os.path.exists(output_dir): os.makedirs(output_dir)

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
        # 矩阵号建议：随机选择副视频和BGM
        sub_path = os.path.abspath(os.path.join(sub_dir, random.choice(sub_files)))
        bgm_path = os.path.abspath(os.path.join(bgm_dir, random.choice(bgm_files)))
        output_path = os.path.abspath(os.path.join(output_dir, f"Final_{m_file}"))
        tasks.append((main_path, sub_path, bgm_path, output_path))

    print(f"🚀 深度去重生产线启动 | 总任务: {len(tasks)}")
    # Mac M1/M2/M3 并发 3 性能最佳
    with ThreadPoolExecutor(max_workers=3) as executor:
        for t in tasks:
            executor.submit(process_with_ffmpeg, *t)


if __name__ == "__main__":
    # 配置你的路径
    MAIN_FOLDER = "/Users/huangyun/Desktop/搬运/A12"
    SUB_FOLDER = "/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"
    BGM_FOLDER = "/Users/huangyun/Desktop/搬运/BGM"

    batch_process(MAIN_FOLDER, SUB_FOLDER, BGM_FOLDER)