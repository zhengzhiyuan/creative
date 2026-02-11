import yt_dlp


def download_tiktok_video(url, save_path='downloads'):
    ydl_opts = {
        # 1. 关键：只下载点赞 > 100k 且时长 > 15s 的视频
        'match_filter': yt_dlp.utils.match_filter_func("like_count > 100000 & duration > 15"),

        # 2. 格式设置：优先选择带 h264 编码的视频（方便后续 FFmpeg 处理）
        'format': 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]',

        # 3. 输出路径与文件名：使用视频标题，并过滤非法字符
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',

        # 4. 伪装浏览器，防止被 TikTok 屏蔽
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',

        # 5. 如果需要强制无水印（通常默认就是）
        'extract_flat': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # 提取信息并下载
            info = ydl.extract_info(url, download=True)
            if info:
                print(f"✅ 下载成功: {info.get('title')}")
                print(f"📊 数据：点赞 {info.get('like_count')}, 时长 {info.get('duration')}s")
                return info
        except Exception as e:
            # 如果不符合 match_filter 的条件，也会报错并跳过
            print(f"❌ 视频不符合要求或下载失败: {e}")
            return None

# 调用示例
if __name__ == '__main__':
    download_tiktok_video("https://www.tiktok.com/@smoorfy_julia")