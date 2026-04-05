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
    keep_duration = max(0.1, info['duration'] - 2.5)

    # --- 随机参数逻辑 ---
    r_bright = random.uniform(-0.005, 0.005)
    r_cont = random.uniform(0.995, 1.005)
    blur_value = random.randint(40, 60)
    crop_offset = random.uniform(0.09, 0.11)

    # --- Intel Mac 专项优化滤镜链 ---
    complex_filter = (
        f"trim=0:{keep_duration},setpts=PTS-STARTPTS,"
        f"crop=iw:ih*0.9:0:ih*{crop_offset},"
        f"split=2[bg][fg];"
        f"[bg]scale=1920:1080:flags=bilinear,boxblur={blur_value}:3[bg_blur];"
        f"[fg]scale=-1:1080:flags=bilinear[fg_scale];"
        f"[bg_blur][fg_scale]overlay=(W-w)/2:(H-h)/2,"
        f"eq=brightness={r_bright}:contrast={r_cont},"
        f"unsharp=3:3:0.5:3:3:0.0"
    )

    cmd = [
        'ffmpeg', '-y', '-i', file_path,
        '-vf', complex_filter,
        '-af', f"atrim=0:{keep_duration},asetpts=PTS-STARTPTS,volume={random.uniform(0.98, 1.02)}",
        '-c:v', 'h264_videotoolbox',
        '-b:v', '4500k',  # 优化：4500k 在 1080P 下体积与画质最平衡，减少上传压力
        '-profile:v', 'main',
        '-realtime', '1',
        '-threads', '2',  # 优化：限制单任务线程，防止 Intel CPU 瞬间满载死机
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

    print(f"🚀 [1080P 高清优化模式] 正在处理 {len(files)} 个视频...")
    tasks = []
    for i, f in enumerate(files):
        info = get_video_info(os.path.join(input_dir, f))
        if info:
            tasks.append((os.path.join(input_dir, f), os.path.join(temp_dir, f"{i:04d}.ts"), info))

    # 优化：Intel 芯片并行数建议设为 2，设为 4 极易导致 I/O 阻塞引发死机
    with ProcessPoolExecutor(max_workers=2) as executor:
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

    # 最终合并优化：加入 faststart 标记，方便 YouTube 快速转码和播放
    subprocess.run([
        'ffmpeg', '-y', '-i', combined_ts,
        '-c', 'copy',
        '-map_metadata', '-1',
        '-movflags', '+faststart',
        output_file
    ], capture_output=True)

    if os.path.exists(combined_ts): os.remove(combined_ts)
    print(f"✅ 完成！总耗时: {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    MY_INPUT = "/Users/huangyun/git/creative/ent/my_creative_material/xxx_folder"
    MY_TEMP = "/Users/huangyun/Desktop/搬运/ENT/temp_processed"
    MY_OUTPUT = "/Users/huangyun/Desktop/搬运/ENT/target/final_1080p_work.mp4"
    run_video_pipeline(MY_INPUT, MY_TEMP, MY_OUTPUT)