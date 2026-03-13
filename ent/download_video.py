import asyncio
from playwright.async_api import async_playwright
import yt_dlp
import sys
import re
import csv
import os
from datetime import datetime
import random # 在文件顶部导入

# ================= 配置区 =================
# 1. 这里设置你的输出根目录（支持绝对地址或相对地址）
OUTPUT_ROOT = "my_creative_material"

# 2. 是否为每次搜索创建独立的子文件夹？ (True: 开启隔离 | False: 全部塞进根目录)
USE_SUBFOLDER = True

# 3. 网络代理设置
# PROXY_URL = "http://127.0.0.1:7897" # 修改为你实际使用的代理地址
# ==========================================

def save_to_csv(data, folder_path):
    """将视频元数据保存到 CSV 文件中"""
    csv_path = os.path.join(folder_path, "video_metadata.csv")
    file_exists = os.path.isfile(csv_path)

    with open(csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "搜索关键词", "文件名", "是否最热第一个", "标题", "播放量", "点赞数", "时长", "发布日期", "视频链接"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)


async def get_bili_video_tasks(keyword, min_single_min=1, max_single_min=15, target_total_range=(18, 25), max_count=3):
    tasks = []
    accumulated_sec = 0
    min_total_sec = target_total_range[0] * 60
    max_total_sec = target_total_range[1] * 60
    min_single_sec = min_single_min * 60
    max_single_sec = max_single_min * 60

    async with async_playwright() as p:
        # 修改点：浏览器启动加入代理
        browser = await p.chromium.launch(
            headless=False,
            # proxy={"server": PROXY_URL}
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        async def fetch_urls(search_kw):
            nonlocal accumulated_sec
            current_urls = []
            url = f"https://search.bilibili.com/all?keyword={search_kw}"
            print(f"🌐 正在检索: {search_kw} ...")

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                if await page.query_selector(".not-found-content, .error-text, .search-no-data"):
                    return []

                await page.wait_for_selector(".bili-video-card, .video-list-item", timeout=8000)
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(1500)

                cards = await page.query_selector_all(".bili-video-card, .video-list-item")

                for card in cards:
                    if len(tasks) + len(current_urls) >= max_count:
                        break

                    duration_el = await card.query_selector(".bili-video-card__stats__duration, .duration")
                    if not duration_el: continue
                    d_str = (await duration_el.inner_text()).strip()

                    parts = list(map(int, d_str.split(':')))
                    sec = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]

                    if min_single_sec <= sec <= max_single_sec:
                        if accumulated_sec + sec > max_total_sec:
                            continue

                        link_el = await card.query_selector("a[href*='/video/BV']")
                        if link_el:
                            href = await link_el.get_attribute("href")
                            clean_url = (f"https:{href}" if href.startswith("//") else href).split("?")[0]

                            if clean_url not in tasks:
                                current_urls.append(clean_url)
                                accumulated_sec += sec
                                print(f"🎯 匹配 [#{len(tasks) + len(current_urls)}]: {d_str} | {clean_url}")

                                if accumulated_sec >= min_total_sec:
                                    return current_urls
                return current_urls
            except Exception as e:
                print(f"⚠️ 页面处理异常: {e}")
                return []

        tasks = await fetch_urls(keyword)
        if not tasks:
            simplified_kw = " ".join(re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]+", keyword)[:2])
            if simplified_kw != keyword:
                tasks = await fetch_urls(simplified_kw)

        await browser.close()
    return tasks


async def download_with_ytdlp(urls, keyword):
    if not urls:
        print("⚠️ 未发现符合要求的素材。")
        return None

    # 1. 路径处理
    abs_root = os.path.abspath(OUTPUT_ROOT)
    if USE_SUBFOLDER:
        date_str = datetime.now().strftime("%m%d_%H%M")
        safe_kw = re.sub(r'[\\/:*?"<>|]', '_', keyword)
        final_dir = os.path.join(abs_root, f"{safe_kw}_{date_str}")
    else:
        final_dir = abs_root

    if not os.path.exists(final_dir):
        os.makedirs(final_dir)

    # 2. yt-dlp 配置
        # 2. yt-dlp 配置 (优化后的格式选择逻辑)
        ydl_opts_base = {
            # 优先下载 480p 的 AVC 编码，如果没有，则下载 480p 的任意编码，最后保底下载 480p 单一格式
            'format': (
                'bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/'
                'bestvideo[height<=480]+bestaudio/'
                'best[height<=480]'
            ),
            'merge_output_format': 'mp4',
            'nocheckcertificate': True,
            'cookiesfrombrowser': ('chrome',),
            'restrictfilenames': True,
            'postprocessor_args': ['-movflags', 'faststart'],
            'quiet': True,
            'no_warnings': True,
            'writeinfojson': True,
            'writedescription': True,
            'retries': 10,
            'fragment_retries': 10,
            'retry_sleep_functions': {'http': lambda n: 5},
            'file_access_retries': 5,
            'noplaylist': True,
            'playlist_items': '1',
            # 'proxy': PROXY_URL,  # 确保这里的代理变量依然保留
        }

    print(f"🚀 素材将存放至: {final_dir}")

    try:
        for index, url in enumerate(urls):
            wait_time = random.uniform(3, 7)  # 随机等待 3 到 7 秒
            print(f"☕️ 正在冷却 {wait_time:.1f} 秒，防止触发 B 站限速...")
            await asyncio.sleep(wait_time)
            target_file_name = f"{index}.mp4"

            current_opts = ydl_opts_base.copy()
            current_opts['outtmpl'] = os.path.join(final_dir, f"{index}.%(ext)s")

            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                is_top_hot = "是" if index == 0 else "否"

                metadata = {
                    "搜索关键词": keyword,
                    "文件名": target_file_name,
                    "是否最热第一个": is_top_hot,
                    "标题": info.get('title'),
                    "播放量": info.get('view_count'),
                    "点赞数": info.get('like_count'),
                    "时长": info.get('duration_string'),
                    "发布日期": info.get('upload_date'),
                    "视频链接": url
                }

                save_to_csv(metadata, final_dir)
                print(f"✅ 下载成功: {target_file_name} | 最热: {is_top_hot}")

        print(f"\n✨ 全部完成！路径: {final_dir}")
        return final_dir

    except Exception as e:
        print(f"❌ 下载过程出错: {e}")
        return None


if __name__ == "__main__":
    raw_kw = input("请输入搜索关键字: ").strip()
    if not raw_kw: sys.exit()

    async def run():
        video_tasks = await get_bili_video_tasks(raw_kw)
        await download_with_ytdlp(video_tasks, raw_kw)

    asyncio.run(run())