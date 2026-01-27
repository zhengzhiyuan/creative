import os
import shutil
from icrawler.builtin import BingImageCrawler

# === 14天 视觉错觉素材清单 ===
# 选取色彩鲜艳、大众熟知的角色，反色效果最好
ASSET_PLAN = [
    ("day1", "Iron Man face close up"),
    ("day2", "Hulk face close up"),
    ("day3", "Spider-Man face close up"),
    ("day4", "Pikachu face close up"),
    ("day5", "Joker Joaquin Phoenix face"),
    ("day6", "Captain America face"),
    ("day7", "Venom face close up"),
    ("day8", "Mario face close up"),
    ("day9", "SpongeBob face"),
    ("day10", "Minion face close up"),
    ("day11", "Batman face close up"),
    ("day12", "Deadpool face"),
    ("day13", "Elsa Frozen face"),
    ("day14", "Buzz Lightyear face")
]

BASE_DIR = "assets/illusion"


def download_assets():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)

    print("🚀 开始下载 14 天错觉素材...")

    for day, keyword in ASSET_PLAN:
        day_dir = os.path.join(BASE_DIR, day)
        if not os.path.exists(day_dir):
            os.makedirs(day_dir)

        # 检查是否已存在
        if os.path.exists(os.path.join(day_dir, "illusion.jpg")):
            print(f"✅ {day} 已存在，跳过。")
            continue

        print(f"⬇️ 下载 {day}: {keyword} ...")

        # 使用临时目录下载
        temp_dir = os.path.join(day_dir, "temp")
        crawler = BingImageCrawler(storage={'root_dir': temp_dir})
        # 加上关键词确保高清竖屏或大图
        crawler.crawl(keyword=f"{keyword} high quality portrait wallpaper", max_num=1)

        # 重命名并移动
        try:
            downloaded = os.listdir(temp_dir)
            if downloaded:
                src = os.path.join(temp_dir, downloaded[0])
                dst = os.path.join(day_dir, "illusion.jpg")
                shutil.move(src, dst)
        except Exception as e:
            print(f"❌ Error {day}: {e}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


if __name__ == "__main__":
    download_assets()