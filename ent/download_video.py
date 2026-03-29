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


async def get_bili_video_tasks(hot_kw, history_kw, target_total_range=(25, 40)):
    all_hot_candidates = []
    all_history_candidates = []
    max_total_sec = target_total_range[1] * 60

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, proxy={"server": PROXY_URL})
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = await context.new_page()

        async def search_and_pick(search_kw, is_hot=True, min_len=60, max_len=1800):
            url = f"https://search.bilibili.com/all?keyword={search_kw}"
            print(f"\n🌐 正在检索关键词: {search_kw}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                try:
                    await page.click("button:has-text('最多点击')", timeout=5000)
                    await asyncio.sleep(2)
                    print(f"📈 已切换至「最多点击」排序")
                except:
                    print(f"⚠️ 切换排序失败，使用默认排序")

                await page.wait_for_selector(".bili-video-card, .video-list-item", timeout=8000)
                cards = await page.query_selector_all(".bili-video-card, .video-list-item")

                found_count = 0
                for card in cards:
                    if found_count >= 8: break  # 检索备选池扩大到8个，应对下载失败

                    duration_el = await card.query_selector(".bili-video-card__stats__duration, .duration")
                    if not duration_el: continue
                    d_str = (await duration_el.inner_text()).strip()

                    parts = list(map(int, d_str.split(':')))
                    sec = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[
                        2] if len(parts) == 3 else 0

                    if sec < min_len or sec > max_len: continue

                    link_el = await card.query_selector("a[href*='/video/BV']")
                    if link_el:
                        href = await link_el.get_attribute("href")
                        clean_url = (f"https:{href}" if href.startswith("//") else href).split("?")[0]
                        task = (clean_url, sec, d_str)
                        if is_hot:
                            all_hot_candidates.append(task)
                        else:
                            all_history_candidates.append(task)
                        found_count += 1
            except Exception as e:
                print(f"⚠️ 搜索异常: {e}")

        await search_and_pick(hot_kw, is_hot=True)
        await search_and_pick(history_kw, is_hot=False)
        await browser.close()

    # --- 强化版动态匹配：区分主视频和候补副视频 ---
    final_tasks = []

    # 1. 确定主视频任务 (1个)
    if all_hot_candidates:
        url, sec, d_str = all_hot_candidates[0]
        final_tasks.append({"url": url, "sec": sec, "d_str": d_str, "type": "hot"})

    # 2. 确定副视频备选池 (全部历史视频作为候补)
    for url, sec, d_str in all_history_candidates:
        final_tasks.append({"url": url, "sec": sec, "d_str": d_str, "type": "history"})

    return final_tasks


async def download_with_ytdlp(tasks, hot_kw, target_min_sec=1500):  # 1500s = 25min
    if not tasks:
        print("\n终止: 没有符合要求的素材。")
        return None

    abs_root = os.path.abspath(OUTPUT_ROOT)
    if USE_SUBFOLDER:
        date_str = datetime.now().strftime("%m%d_%H%M")
        safe_kw = re.sub(r'[\\/:*?"<>|]', '_', hot_kw)
        final_dir = os.path.join(abs_root, f"{safe_kw}_{date_str}")
    else:
        final_dir = abs_root

    if not os.path.exists(final_dir): os.makedirs(final_dir)

    # 状态控制
    SUCCESS_LIMIT_HISTORY = 3  # 副视频最多3个
    actual_hot_success = 0
    actual_history_success = 0
    current_total_sec = 0

    ydl_opts_base = {
        'format': 'bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=480]+bestaudio/best',
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
        'socket_timeout': 60,
        'retries': 5,
        'cookiesfrombrowser': ('chrome',),
        'proxy': PROXY_URL,
        'quiet': True,
        'no_warnings': True,
    }

    print(f"\n🚀 开始动态补位下载 (目标: 1主+3副，且总长 > {target_min_sec // 60}min)...")

    for task in tasks:
        # 熔断逻辑：
        # 如果是副视频，且已经成功下载了3个，或者总时长已达标，则跳过
        if task['type'] == "history":
            if actual_history_success >= SUCCESS_LIMIT_HISTORY or current_total_sec >= target_min_sec:
                continue
        # 如果是主视频且已成功，跳过（防止重复）
        if task['type'] == "hot" and actual_hot_success >= 1:
            continue

        # 确定文件名
        if task['type'] == "hot":
            filename = "1.mp4"
        else:
            filename = f"{actual_history_success + 2}.mp4"

        print(f"📥 尝试下载 [{filename}] | 时长: {task['d_str']} | URL: {task['url']}")
        await asyncio.sleep(random.uniform(2, 4))

        opts = ydl_opts_base.copy()
        opts['outtmpl'] = os.path.join(final_dir, filename.split('.')[0] + ".%(ext)s")

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(task['url'], download=True)
                metadata = {
                    "搜索关键词": hot_kw, "文件名": filename,
                    "是否最热第一个": "是" if filename == "1.mp4" else "否",
                    "标题": info.get('title'), "播放量": info.get('view_count'),
                    "点赞数": info.get('like_count'), "时长": info.get('duration_string'),
                    "发布日期": info.get('upload_date'), "视频链接": task['url']
                }
                save_to_csv(metadata, final_dir)

                # 下载成功后更新状态
                if task['type'] == "hot":
                    actual_hot_success += 1
                else:
                    actual_history_success += 1

                current_total_sec += task['sec']
                print(f"✨ 下载成功! 当前已累积时长: {current_total_sec // 60}分{current_total_sec % 60}秒")

            except Exception as e:
                print(f"❌ 下载失败，将自动尝试后续候补视频补位: {e}")

    print(
        f"\n✅ 任务结束 | 成功下载: {actual_hot_success}主 + {actual_history_success}副 | 总长: {current_total_sec // 60}min")
    return final_dir


if __name__ == "__main__":
    hot_kw = input("🔥 输入热点词: ").strip()
    history_kw = input("📜 输入黑历史词: ").strip()
    if hot_kw and history_kw:
        async def run():
            # 搜索时放宽范围，多拿备选
            tasks = await get_bili_video_tasks(hot_kw, history_kw, target_total_range=(25, 40))
            # 下载时传入目标最小秒数 (25分钟 = 1500秒)
            await download_with_ytdlp(tasks, hot_kw, target_min_sec=1500)


        asyncio.run(run())