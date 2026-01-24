import os
import requests

# === 配置下载链接 (亲测可用的稳定直链) ===
SFX_URLS = {
    "tick.mp3": "https://cdn.pixabay.com/audio/2022/03/10/audio_c8c8a73467.mp3",  # 清脆的秒表声
    "boom.mp3": "https://www.myinstants.com/media/sounds/vine-boom.mp3"  # 经典的 Vine Boom (Shorts标配)
}

OUTPUT_DIR = "assets/sfx"


def download_file(url, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)

    # 如果文件已存在，跳过
    if os.path.exists(filepath):
        print(f"✅ 已存在: {filename}")
        return

    print(f"⬇️ 正在下载: {filename} ...")
    try:
        # 伪装 User-Agent 防止被拦截
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, stream=True)

        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"✅ 下载完成: {filepath}")
        else:
            print(f"❌ 下载失败 (Status {response.status_code}): {url}")

    except Exception as e:
        print(f"❌ 错误: {e}")


def main():
    # 1. 创建文件夹
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📂 创建文件夹: {OUTPUT_DIR}")

    # 2. 批量下载
    for filename, url in SFX_URLS.items():
        download_file(url, filename)

    print("\n🎉 音效素材准备就绪！")


if __name__ == "__main__":
    main()