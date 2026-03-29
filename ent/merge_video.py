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

    # --- 随机参数逻辑 (去重微调) ---
    r_bright = random.uniform(-0.01, 0.01)
    r_cont = random.uniform(0.99, 1.01)
    blur_value = random.randint(30, 50)

    # 水印裁剪偏移 (保持 10% 左右)
    crop_offset = random.uniform(0.095, 0.105)

    # --- 核心优化：先裁剪水印，再模糊填充 ---
    # 1. crop=iw:ih*0.9:0:ih*crop_offset -> 这一步先把顶部 10% 切掉
    # 2. split=2[bg][fg] -> 分出背景和前景
    # 3. [bg] 做 16:9 模糊填充
    # 4. [fg] 做居中叠加
    complex_filter = (
        f"trim=0:{keep_duration},setpts=PTS-STARTPTS,"
        f"crop=iw:ih*0.9:0:ih*{crop_offset},"  # ✨ 恢复裁剪水印逻辑
        f"split=2[bg][fg];"
        f"[bg]scale=854:480,boxblur={blur_value}:5[bg_blur];"
        f"[fg]scale=-1:480[fg_scale];"
        f"[bg_blur][fg_scale]overlay=(W-w)/2:(H-h)/2,"
        f"noise=alls=1:allf=t+u,"
        f"eq=brightness={r_bright}:contrast={r_cont},"
        f"setsar=1"
    )

    cmd = [
        'ffmpeg', '-y', '-i', file_path,
        '-vf', complex_filter,
        '-af', f"atrim=0:{keep_duration},asetpts=PTS-STARTPTS,volume={random.uniform(0.99, 1.01)}",
        '-c:v', 'h264_videotoolbox',
        '-b:v', '2500k',
        '-c:a', 'aac', '-b:a', '128k',
        '-map_metadata', '-1',
        '-f', 'mpegts', output_ts
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ 文件 {os.path.basename(file_path)} 处理失败。")
        return None
    return output_ts


def run_video_pipeline(input_dir, temp_dir, output_file):
    start_time = time.time()
    input_dir, temp_dir, output_file = map(os.path.abspath, [input_dir, temp_dir, output_file])
    clean_up(temp_dir, output_file)

    files = sorted(
        [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.mov', '.mkv')) and not f.startswith('.')])
    if not files: return print("未发现视频。")

    print(f"🚀 [全能去重模式] 正在处理 {len(files)} 个视频...")
    tasks = []
    for i, f in enumerate(files):
        info = get_video_info(os.path.join(input_dir, f))
        if info:
            tasks.append((os.path.join(input_dir, f), os.path.join(temp_dir, f"{i:04d}.ts"), info))

    with ProcessPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process_single_video, tasks))

    valid_ts = [r for r in results if r is not None and os.path.exists(r)]
    if not valid_ts:
        print("❌ 转码失败。")
        return

    combined_ts = os.path.join(temp_dir, "combined.ts")
    with open(combined_ts, 'wb') as outfile:
        for ts_file in valid_ts:
            with open(ts_file, 'rb') as infile:
                shutil.copyfileobj(infile, outfile)

    subprocess.run(['ffmpeg', '-y', '-i', combined_ts, '-c', 'copy', '-map_metadata', '-1', output_file],
                   capture_output=True)
    if os.path.exists(combined_ts): os.remove(combined_ts)
    print(f"✅ 完成！总耗时: {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    MY_INPUT = "/Users/huangyun/git/creative/ent/my_creative_material/迪麗熱巴 臉崩_0329_2212"
    MY_TEMP = "/Users/huangyun/Desktop/搬运/ENT/temp_processed"
    MY_OUTPUT = "/Users/huangyun/Desktop/搬运/ENT/target/final_work_fixed.mp4"
    run_video_pipeline(MY_INPUT, MY_TEMP, MY_OUTPUT)