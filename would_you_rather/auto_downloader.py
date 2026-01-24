import os
import shutil
from icrawler.builtin import BingImageCrawler

# === 配置 ===
# 为了规避 Google 的反爬虫，这里使用 Bing 引擎（效果一样好且稳定）
ROOT_DIR = "assets/sfx/speedrun"

# === 14天完整搜索关键词清单 ===
# 格式: Day: [(Q1A, Q1B), (Q2A, Q2B), (Q3A, Q3B)]
# 关键词已自动加上 "vertical wallpaper 4k" 以确保质量
DATA_PLAN = {
    1: [
        ("stack of money aesthetic", "gigachad meme real life"),
        ("superman flying comic movie", "hollow man invisible movie poster"),
        ("mom hugging child art aesthetic", "dad hugging child art aesthetic")
    ],
    2: [
        ("iron man mark 85 suit", "captain america shield broken"),
        ("thor mjolnir hammer lightning", "incredible hulk screaming"),
        ("thanos infinity gauntlet snap", "loki tva series poster")
    ],
    3: [
        ("neon wifi sign aesthetic", "pizza burger feast food porn"),
        ("playstation 5 logo neon", "xbox series x logo neon"),
        ("dream gaming room setup rgb", "cash money luxury aesthetic")
    ],
    4: [
        ("zombie horde apocalypse art", "scary ghost shadow art"),
        ("dracula vampire horror art", "werewolf monster full moon art"),
        ("deep ocean thalassophobia scary", "deep space void scary")
    ],
    5: [
        ("pepperoni pizza cheese pull", "juicy cheeseburger aesthetic"),
        ("coca cola glass ice cold", "pepsi can neon aesthetic"),
        ("candy shop colorful", "french fries potato chips")
    ],
    6: [
        ("stack of homework paper", "exam fail grade F red"),
        ("einstein math formula blackboard", "high school party friends"),
        ("boring classroom anime style", "prison bars dark mood")
    ],
    7: [
        ("couple holding hands sunset", "gold bars vault"),
        ("person whispering secret dark", "broken heart neon sign"),
        ("silhouette couple arguing", "angry boss office meme")
    ],
    8: [
        ("zendaya mj spider-man movie", "gwen stacy spider-verse art"),
        ("tobey maguire spider-man suit", "tom holland spider-man suit"),
        ("spider-man turning to dust infinity war", "iron man dying endgame")
    ],
    9: [
        ("iron man neon art", "batman rain art"),
        ("thor thunder eyes", "superman heat vision"),
        ("joker joaquin phoenix stairs", "thanos smiling")
    ],
    10: [
        ("glowing brain art mind reading", "crystal ball mystical"),
        ("nightcrawler teleport effect", "delorean back to the future"),
        ("frozen water droplets time stop", "clock spinning backwards art")
    ],
    11: [
        ("gryffindor crest wallpaper", "slytherin crest wallpaper"),
        ("harry potter wand spell", "draco malfoy suit green"),
        ("dobby elf cute art", "dumbledore falling half blood prince")
    ],
    12: [
        ("ruined city zombie art", "ufo beam abduction art"),
        ("frozen man ice movie", "fire flames hellscape"),
        ("sniper rifle scope view", "scared person hiding closet")
    ],
    13: [
        ("broken smartphone screen", "tv static noise screen"),
        ("headphones crossed out", "empty cinema theater"),
        ("dr dolittle movie poster", "tower of babel art")
    ],
    14: [
        ("matrix red pill blue pill", "matrix red pill blue pill"),  # Q1特殊：两张一样的图，代码会自动处理切分或直接用
        ("new born baby feet", "old man tombstone art"),
        ("white dove olive branch", "scrooge mcduck money bin")
    ]
}


def download_images():
    print("🚀 开始自动抓取 14 天素材...")

    for day, questions in DATA_PLAN.items():
        day_folder = os.path.join(ROOT_DIR, f"day{day}")

        # 1. 创建当天文件夹
        if not os.path.exists(day_folder):
            os.makedirs(day_folder)

        print(f"\n📅 Processing Day {day}...")

        # 遍历3个问题
        for q_idx, (kw_a, kw_b) in enumerate(questions):
            # Q1, Q2, Q3
            q_num = q_idx + 1

            # 下载并重命名 Option A
            download_single(day_folder, f"q{q_num}_a", kw_a)

            # 下载并重命名 Option B
            download_single(day_folder, f"q{q_num}_b", kw_b)


def download_single(folder, filename_prefix, keyword):
    """
    使用 Bing 爬虫下载一张图片，并重命名
    """
    # 目标文件路径
    target_path = os.path.join(folder, f"{filename_prefix}.jpg")

    # 如果文件已存在，跳过
    if os.path.exists(target_path):
        print(f"  ✅ {filename_prefix}.jpg 已存在，跳过。")
        return

    # 临时文件夹
    temp_dir = os.path.join(folder, "temp")

    crawler = BingImageCrawler(storage={'root_dir': temp_dir})

    # 添加后缀以保证竖屏高清
    search_query = f"{keyword} vertical wallpaper 4k"

    # 爬取 1 张
    crawler.crawl(keyword=search_query, max_num=1)

    # 移动并重命名
    try:
        # 获取爬下来的文件名 (通常是 000001.jpg)
        downloaded_files = os.listdir(temp_dir)
        if downloaded_files:
            src = os.path.join(temp_dir, downloaded_files[0])
            shutil.move(src, target_path)
            print(f"  📥 下载成功: {filename_prefix}.jpg")
        else:
            print(f"  ⚠️ 下载失败: {keyword}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    finally:
        # 清理临时文件夹
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    download_images()