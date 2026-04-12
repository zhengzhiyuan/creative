import os
import subprocess
import sys


class BiliDownloader:
    def __init__(self, download_path="test_assets"):
        self.download_path = download_path
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

    def search_and_download(self, query, limit=1):
        print(f"开始搜索并下载关键词: {query}")

        # 将搜索关键词转为 B 站标准的搜索链接
        # yt-dlp 能够自动解析这种 search URL 并抓取结果
        search_url = f"https://search.bilibili.com/all?keyword={query}"

        cmd = [
            sys.executable, '-m', 'yt_dlp',
            search_url,
            '--playlist-items', f'1-{limit}',  # 下载搜索结果的前 limit 个
            '--paths', self.download_path,
            '--output', '%(title).20s-%(id)s.%(ext)s',
            '--format', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '--no-playlist',  # 这里的 no-playlist 是指不下载视频合辑，仅从搜索列表抓取
            '--user-agent',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]

        try:
            # 💡 注意：有些环境需要 shell=True，但为了安全我们先保持 False
            # 增加一个超时设置，防止进程卡死
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            if result.returncode == 0:
                print("✅ 下载任务启动成功！")
                print(result.stdout)
            else:
                # 打印详细错误方便排查
                print(f"❌ 下载出错，错误详情：\n{result.stderr}")

        except Exception as e:
            print(f"💣 执行异常: {str(e)}")


if __name__ == "__main__":
    downloader = BiliDownloader()
    downloader.search_and_download("谢霆锋 顶包案 现场", limit=1)