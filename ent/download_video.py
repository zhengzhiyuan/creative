import asyncio
from playwright.async_api import async_playwright
import yt_dlp
import sys
import re
import csv
import os
from datetime import datetime
import random

# ================= 配置区 =================
OUTPUT_ROOT = "my_creative_material"
USE_SUBFOLDER = True
PROXY_URL = "http://127.0.0.1:7897"


# ==========================================

def save_to_csv(data, folder_path):
    csv_path = os.path.join(folder_path, "video_metadata.csv")
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "搜索关键词", "文件名", "是否最热第一个", "标题", "播放量", "点赞数", "时长", "发布日期", "视频链接"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)


async def get_bili_video_tasks(hot_kw, history_kw, target_total_range=(15, 25)):
    final_tasks = []  # 格式: (url, duration_sec, filename)
    accumulated_sec = 0
    max_total_sec = target_total_range[1] * 60
    min_total_sec = target_total_range[0] * 60

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, proxy={"server": PROXY_URL})
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = await context.new_page()

        async def search_and_pick(search_kw, limit, start_num, min_len=60, max_len=1200):
            nonlocal accumulated_sec
            current_found = 0
            url = f"https://search.bilibili.com/all?keyword={search_kw}"
            print(f"\n🌐 正在检索关键词: {search_kw}")

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_selector(".bili-video-card, .video-list-item", timeout=8000)
                cards = await page.query_selector_all(".bili-video-card, .video-list-item")

                for card in cards:
                    if current_found >= limit: break

                    duration_el = await card.query_selector(".bili-video-card__stats__duration, .duration")
                    if not duration_el: continue
                    d_str = (await duration_el.inner_text()).strip()
                    parts = list(map(int, d_str.split(':')))
                    sec = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]

                    # 1. 长度过滤
                    if sec < min_len or sec > max_len: continue
                    # 2. 总时长上限过滤
                    if accumulated_sec + sec > max_total_sec:
                        print(f"⏩ 跳过: {d_str} (加入后将超过25min上限)")
                        continue

                    link_el = await card.query_selector("a[href*='/video/BV']")
                    if link_el:
                        href = await link_el.get_attribute("href")
                        clean_url = (f"https:{href}" if href.startswith("//") else href).split("?")[0]

                        # 避免重复
                        if any(x[0] == clean_url for x in final_tasks): continue

                        # 修正命名逻辑：根据当前 final_tasks 的长度自动生成序号
                        file_index = len(final_tasks) + 1
                        fn = f"{file_index}.mp4"

                        final_tasks.append((clean_url, sec, fn))
                        accumulated_sec += sec
                        current_found += 1
                        print(f"✅ 匹配成功 [{fn}] | 时长: {d_str} | URL: {clean_url}")

                if current_found == 0:
                    print(f"❌ 未在该关键词下找到符合条件的视频")
            except Exception as e:
                print(f"⚠️ 搜索过程异常: {e}")

        # 1. 下载当前热点 (1个, 1-20min, 命名1.mp4)
        await search_and_pick(hot_kw, limit=1, start_num=1, min_len=60, max_len=1200)

        # 2. 下载黑历史 (至多2个, >1min, 命名2.mp4, 3.mp4)
        # 即使热点没搜到，也会继续搜黑历史
        remaining_limit = 3 - len(final_tasks)
        if remaining_limit > 0:
            await search_and_pick(history_kw, limit=remaining_limit, start_num=len(final_tasks) + 1, min_len=60)

        await browser.close()

    print(f"\n📊 检索总结:")
    print(f"   - 预选视频总数: {len(final_tasks)}")
    print(f"   - 预估总时长: {accumulated_sec // 60}分{accumulated_sec % 60}秒")
    if accumulated_sec < min_total_sec:
        print(f"   - ⚠️ 警告: 总时长未达到 {target_total_range[0]}min 的要求")

    return final_tasks


async def download_with_ytdlp(tasks, hot_kw):
    if not tasks:
        print("\n终止: 没有符合要求的素材可供下载。")
        return None

    abs_root = os.path.abspath(OUTPUT_ROOT)
    if USE_SUBFOLDER:
        date_str = datetime.now().strftime("%m%d_%H%M")
        safe_kw = re.sub(r'[\\/:*?"<>|]', '_', hot_kw)
        final_dir = os.path.join(abs_root, f"{safe_kw}_{date_str}")
    else:
        final_dir = abs_root

    if not os.path.exists(final_dir):
        os.makedirs(final_dir)

    print(f"\n🚀 开始下载素材至: {final_dir}")

    ydl_opts_base = {
        'format': 'bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=480]+bestaudio/best',
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
        'legacy_server_connect': True,
        'socket_timeout': 60,
        'retries': 30,
        'cookiesfrombrowser': ('chrome',),
        'restrictfilenames': True,
        'proxy': PROXY_URL,
        'quiet': True,  # 减少冗余日志，只看我们的自定义日志
        'no_warnings': True,
    }

    try:
        for url, sec, filename in tasks:
            print(f"\n📥 正在下载 {filename} ...")
            print(f"🔗 URL: {url}")

            # 增加随机冷却
            await asyncio.sleep(random.uniform(2, 4))

            current_opts = ydl_opts_base.copy()
            name_only = filename.split('.')[0]
            current_opts['outtmpl'] = os.path.join(final_dir, name_only + ".%(ext)s")

            with yt_dlp.YoutubeDL(current_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    metadata = {
                        "搜索关键词": hot_kw,
                        "文件名": filename,
                        "是否最热第一个": "是" if filename == "1.mp4" else "否",
                        "标题": info.get('title'),
                        "播放量": info.get('view_count'),
                        "点赞数": info.get('like_count'),
                        "时长": info.get('duration_string'),
                        "发布日期": info.get('upload_date'),
                        "视频链接": url
                    }
                    save_to_csv(metadata, final_dir)
                    print(f"✨ 下载成功: {filename} ({info.get('duration_string')})")
                except Exception as e:
                    print(f"❌ 该条素材下载失败: {e}")

        print(f"\n✅ 全部任务处理完成！")
        return final_dir
    except Exception as e:
        print(f"❌ 核心下载流程中断: {e}")
        return None


if __name__ == "__main__":
    hot_kw = input("请输入当前热点关键词: ").strip()
    history_kw = input("请输入黑历史关键词: ").strip()

    if not hot_kw or not history_kw: sys.exit()


    async def run():
        video_tasks = await get_bili_video_tasks(hot_kw, history_kw)
        await download_with_ytdlp(video_tasks, hot_kw)


    asyncio.run(run())