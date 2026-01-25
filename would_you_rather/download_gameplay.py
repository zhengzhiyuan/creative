import os
import requests
import time

# === 100% 可用的全球直链 ===
VIDEO_SOURCES = {
    # 1. Minecraft Parkour (我的世界跑酷)
    # 来源: GitHub 开源项目托管 (速度快，极其稳定)
    "gameplay_minecraft.mp4": "https://github.com/AnasImloul/Youtube-Shorts-Generator/raw/main/assets/backgrounds/gameplay.mp4",

    # 2. Neon Tunnel (霓虹隧道 - 视觉吸铁石)
    # 来源: Pexels 官方直链 (高清 1080x1920)
    # 这种视频会让用户产生“眩晕/沉浸感”，完播率极高
    "gameplay_neon.mp4": "https://videos.pexels.com/video-files/3052066/3052066-hd_1080_1920_30fps.mp4",

    # 3. Satisfying Fluid (解压流体)
    # 来源: Pexels 官方直链
    # 替代切沙子，视觉效果更高级
    "gameplay_fluid.mp4": "https://videos.pexels.com/video-files/5049386/5049386-hd_1080_1920_30fps.mp4"
}

OUTPUT_DIR = "assets/gameplay"


def download_file(filename, url, retries=3):
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        # 检查文件大小，防止下载了空文件
        if os.path.getsize(filepath) > 1024 * 1024:  # 大于 1MB
            print(f"✅ 文件有效，跳过: {filename}")
            return
        else:
            print(f"⚠️ 文件损坏，重新下载: {filename}")
            os.remove(filepath)

    print(f"⬇️ 正在下载: {filename} ...")

    # 伪装 Header，防止被 Pexels 拒绝
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                        if chunk:
                            f.write(chunk)
                print(f"✅ 下载完成: {filename}")
                return
            else:
                print(f"❌ 服务器返回错误 {response.status_code}，重试中 ({i + 1}/{retries})...")
        except Exception as e:
            print(f"❌ 连接错误: {e}，重试中 ({i + 1}/{retries})...")
            time.sleep(2)

    print(f"🚫 最终失败: {filename}，请检查网络或手动下载。")


def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📂 创建目录: {OUTPUT_DIR}")

    print("🚀 开始下载高留存背景素材 (Final Version)...")

    for name, url in VIDEO_SOURCES.items():
        download_file(name, url)

    print("\n🎉 素材库准备就绪！")
    print("💡 提示：这三个视频都是原生竖屏 (9:16)，无需裁剪，直接生成即可。")


if __name__ == "__main__":
    main()