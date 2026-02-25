import os
import subprocess
import time
import random
import json
import shutil
from concurrent.futures import ProcessPoolExecutor


def clean_up(temp_dir, output_file):
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    if os.path.exists(output_file):
        os.remove(output_file)


def get_video_info(file_path):
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', file_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(res.stdout)
        video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
        duration = float(data.get('format', {}).get('duration', 0))
        if video_stream:
            return {'width': int(video_stream['width']), 'height': int(video_stream['height']), 'duration': duration}
    except:
        return None


def process_single_video(task_info):
    file_path, output_ts, info = task_info
    keep_duration = max(0.1, info['duration'] - 2)
    is_portrait = info['width'] < info['height']

    # --- 随机参数逻辑 (避开不稳定的 noise seed) ---
    crop_offset = random.uniform(0.095, 0.105)
    # 随机亮度微调 (-0.01 到 0.01)
    r_bright = random.uniform(-0.01, 0.01)
    # 随机对比度微调 (0.99 到 1.01)
    r_cont = random.uniform(0.99, 1.01)

    # 动态裁剪滤镜
    crop_filter = "" if is_portrait else f"crop=iw:ih*0.9:0:ih*{crop_offset},"

    # 重新设计的滤镜链：裁剪 -> 基础噪点(不带seed) -> 色彩扰动 -> 480P合成
    # 这里我们只使用 noise=alls=1，不加 seed 参数，避免 8.0 报错
    filter_str = (
        f"trim=0:{keep_duration},setpts=PTS-STARTPTS,"
        f"{crop_filter}"
        f"noise=alls=1:allf=t+u,"
        f"eq=brightness={r_bright}:contrast={r_cont},"
        f"split[main][bg];"
        f"[bg]scale=854:480:force_original_aspect_ratio=increase,crop=854:480,"
        f"boxblur=5:1,eq=brightness=-0.1[blurred_bg];"
        f"[main]scale=854:480:force_original_aspect_ratio=decrease[scaled_v];"
        f"[blurred_bg][scaled_v]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )

    cmd = [
        'ffmpeg', '-y', '-i', file_path,
        '-vf', filter_str,
        '-af', f"atrim=0:{keep_duration},asetpts=PTS-STARTPTS,volume={random.uniform(0.99, 1.01)}",
        '-c:v', 'h264_videotoolbox',
        '-b:v', '1200k',
        '-c:a', 'aac', '-b:a', '96k',
        '-map_metadata', '-1',
        '-f', 'mpegts', output_ts
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ 文件 {os.path.basename(file_path)} 处理失败。报错详情：\n{res.stderr}")
        return None
    return output_ts


def run_video_pipeline(input_dir, temp_dir, output_file):
    start_time = time.time()
    input_dir, temp_dir, output_file = map(os.path.abspath, [input_dir, temp_dir, output_file])

    clean_up(temp_dir, output_file)

    files = sorted(
        [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.mov', '.mkv')) and not f.startswith('.')])
    if not files: return print("未发现视频。")

    print(f"🚀 [版本适配模式] 正在处理 {len(files)} 个视频...")

    tasks = []
    for i, f in enumerate(files):
        info = get_video_info(os.path.join(input_dir, f))
        if info:
            tasks.append((os.path.join(input_dir, f), os.path.join(temp_dir, f"{i:04d}.ts"), info))

    # 使用 2 个并发以适配 i5 硬件加速
    with ProcessPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process_single_video, tasks))

    valid_ts = [r for r in results if r is not None and os.path.exists(r)]

    if not valid_ts:
        print("❌ 转码失败，请检查 FFmpeg 滤镜兼容性。")
        return

    # 直接拼接二进制流
    combined_ts = os.path.join(temp_dir, "combined.ts")
    print(f"🔗 成功转码 {len(valid_ts)} 段，开始二进制拼接...")
    with open(combined_ts, 'wb') as outfile:
        for ts_file in valid_ts:
            with open(ts_file, 'rb') as infile:
                shutil.copyfileobj(infile, outfile)

    # 封装
    print("🎬 封装最终 MP4 并抹除元数据...")
    subprocess.run(['ffmpeg', '-y', '-i', combined_ts, '-c', 'copy', '-map_metadata', '-1', output_file],
                   capture_output=True)

    if os.path.exists(combined_ts): os.remove(combined_ts)

    print(f"✅ 处理完成！总耗时: {time.time() - start_time:.2f}s")
    print(f"📁 结果: {output_file}")


if __name__ == "__main__":
    MY_INPUT = "/Users/huangyun/Desktop/搬运/ENT/my_videos"
    MY_TEMP = "/Users/huangyun/Desktop/搬运/ENT/temp_processed"
    MY_OUTPUT = "/Users/huangyun/Desktop/搬运/ENT/target/final_work.mp4"
    run_video_pipeline(MY_INPUT, MY_TEMP, MY_OUTPUT)