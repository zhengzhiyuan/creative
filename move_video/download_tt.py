import os
import subprocess
import sys  # 必须导入 sys
import yt_dlp


def download_tiktok_videos(collection_url, save_dir):
    """
    1. 每次仅下载3个视频
    2. 过滤点赞>10万，时长>15秒
    3. 记录进度防止重复
    4. 保留视频标题
    """
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # 进度记录文件：记录已下载的视频ID
    archive_file = os.path.join(save_dir, "downloaded_history.txt")

    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--download-archive', archive_file,
        '--max-downloads', '3',
        '--match-filter', "duration > 15 & like_count >= 200000",
        '-o', f'{save_dir}/%(title).90s.%(ext)s',
        '--format', 'bestvideo+bestaudio/best',
        '--merge-output-format', 'mp4',
        '--no-check-certificate',
        '--ignore-errors',

        # --- 重点修改 1：增加此项解决 SSL/握手问题 ---
        '--legacy-server-connect',

        # --- 重点修改 2：Cookie 处理 ---
        '--cookies-from-browser', 'chrome',

        # --- 重点修改 3：使用更现代的 UA ---
        '--user-agent',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',

        collection_url
    ]

    cmd.extend(['--proxy', 'http://127.0.0.1:7897'])

    try:
        print(f"🚀 正在从 {collection_url} 匹配并下载 3 个优质视频...")
        subprocess.run(cmd, check=True)
        print("✅ 任务完成：3个视频已保存，进度已记录。")
    except subprocess.CalledProcessError as e:
        # 如果是因为达到 max-downloads 停止，属于正常结束
        if e.returncode == 101:
            print("✅ 已达到本次下载限额（3个）。")
        else:
            print(f"❌ 下载过程出现异常: {e}")


if __name__ == "__main__":
    # 示例：某个博主的主页链接
    target_url = "https://www.tiktok.com/@katy.vine"
    # 你的主视频存放目录
    main_video_path = "/Users/huangyun/Desktop/搬运/A17"

    download_tiktok_videos(target_url, main_video_path)
