import os
import random
import subprocess
import time
import json

# ================= 配置区域 =================
INPUT_DIR = "tiktok_raw"
OUTPUT_DIR = "yt_shorts_ready"
REACTION_FILE = "reaction_green.mp4"
# 预设一个经典的绿幕猫咪
REACTION_URL = "https://www.youtube.com/watch?v=J---aiyznGQ"

FFMPEG_EXE = "ffmpeg"
MAX_DURATION = 59


# ============================================

def setup_environment():
    if not os.path.exists(INPUT_DIR): os.makedirs(INPUT_DIR)
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)

    if not os.path.exists(REACTION_FILE):
        print("🌐 正在抓取绿幕反应素材...")
        try:
            subprocess.run(['yt-dlp', '-f', 'mp4', '--output', REACTION_FILE, REACTION_URL], check=True)
            print("✅ 绿幕素材准备就绪")
        except Exception as e:
            print(f"⚠️ 下载失败，请手动放置 {REACTION_FILE}")


def get_video_duration(input_file):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', input_file]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(json.loads(result.stdout)['format']['duration'])


def process_segment(input_file, output_file, start_time):
    speed = round(random.uniform(1.01, 1.04), 3)
    br = round(random.uniform(-0.02, 0.02), 3)
    cont = round(random.uniform(1.0, 1.05), 3)
    sat = round(random.uniform(1.0, 1.1), 3)

    # --- 核心改进：chromakey 相似度调高到 0.3，增加 despill 去绿边 ---
    video_filter = (
        f"[0:v]split[v1][v2];"
        f"[v1]scale=1080:1920,boxblur=20:10[bg];"
        f"[v2]scale=980:-1,setpts={1 / speed}*PTS,"
        f"eq=brightness={br}:contrast={cont}:saturation={sat},"
        f"vibrance=intensity=0.3,unsharp=5:5:1.0:5:5:0.0[fg];"
        f"[1:v]chromakey=0x00FF00:0.3:0.1,despill,scale=350:-1,setpts=PTS-STARTPTS[react];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[temp];"
        f"[temp][react]overlay=W-w-30:H-h-200:shortest=1,"
        f"drawbox=y=ih-15:w=iw*t/{MAX_DURATION}:h=15:color=orange@0.9:t=fill,format=yuv420p[v_final]"
    )

    audio_filter = f"atempo={speed},asetrate=44100*1.01,aresample=44100"

    cmd = [
        FFMPEG_EXE, '-y',
        '-ss', str(start_time),
        '-t', str(MAX_DURATION),
        '-i', input_file,  # 0: ASMR
        '-stream_loop', '-1',
        '-i', REACTION_FILE,  # 1: 绿幕
        '-filter_complex', video_filter,
        '-af', audio_filter,
        '-map', '[v_final]',  # 映射合成后的视频
        '-map', '0:a',  # 只要 ASMR 的声音
        '-c:v', 'h264_videotoolbox',
        '-b:v', '6000k',
        '-c:a', 'aac',
        '-map_metadata', '-1',
        output_file
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ 报错: {result.stderr}")


def main():
    setup_environment()
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]

    if not files:
        print(f"👉 文件夹 {INPUT_DIR} 是空的")
        return

    print(f"🍏 M-Series 加速模式 | 正在清除绿幕并合成视频...")

    for filename in files:
        in_p = os.path.join(INPUT_DIR, filename)
        try:
            total_dur = get_video_duration(in_p)
            print(f"\n🎬 正在处理: {filename}")

            start = 0
            part = 1
            while start < total_dur:
                if total_dur - start < 5: break
                out_name = f"final_P{part}_{filename}"
                out_p = os.path.join(OUTPUT_DIR, out_name)
                process_segment(in_p, out_p, start)
                start += MAX_DURATION
                part += 1
            print(f"  ✅ 完成")
        except Exception as e:
            print(f"  ❌ 错误: {filename} | {e}")


if __name__ == "__main__":
    main()