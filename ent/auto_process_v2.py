import asyncio
import json
import os
import re
import random
import csv
import yt_dlp
import edge_tts
from playwright.async_api import async_playwright
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip, CompositeVideoClip
import moviepy.video.fx.all as vfx
from datetime import datetime

# ================= 配置区 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(CURRENT_DIR, "ent_v")
OUTPUT_ROOT = os.path.join(CURRENT_DIR, "video_projects")
MAX_DOWNLOAD_PER_ACT = 3
TTS_VOICE = "zh-CN-XiaoxiaoNeural"
SEARCH_SEMAPHORE = asyncio.Semaphore(2)


# ==========================================

class VideoAutomation:
    def __init__(self, project_name):
        self.project_dir = os.path.join(OUTPUT_ROOT, f"{project_name}_{datetime.now().strftime('%m%d_%H%M')}")
        os.makedirs(self.project_dir, exist_ok=True)

    def save_to_csv(self, data, act_path):
        csv_path = os.path.join(act_path, "video_metadata.csv")
        file_exists = os.path.isfile(csv_path)
        with open(csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f,
                                    fieldnames=["搜索关键词", "文件名", "标题", "播放量", "点赞数", "时长", "发布日期",
                                                "视频链接"])
            if not file_exists: writer.writeheader()
            writer.writerow(data)

    async def _single_search(self, context, keyword, limit):
        async with SEARCH_SEMAPHORE:
            videos = []
            page = await context.new_page()
            # 模拟随机视口大小，减少被检测概率
            await page.set_viewport_size(
                {"width": 1280 + random.randint(0, 100), "height": 720 + random.randint(0, 100)})

            url = f"https://search.bilibili.com/all?keyword={keyword}"
            try:
                # 1. 优化：改用更稳健的等待方式
                await page.goto(url, wait_until="load", timeout=30000)

                # 2. 优化：模拟真实滚动，触发 B 站懒加载
                await page.evaluate("window.scrollTo(0, 500)")
                await asyncio.sleep(1)

                try:
                    # 尝试点击排序（非必须，失败则跳过）
                    sort_btn = await page.get_by_text("最多点击").first
                    if await sort_btn.is_visible():
                        await sort_btn.click()
                        await asyncio.sleep(2)  # 等待排序后的列表加载
                except:
                    pass

                # 3. 优化：等待选择器，并稍微延长超时到 20s
                selector = ".bili-video-card, .video-list-item, .video-item"
                await page.wait_for_selector(selector, timeout=20000, state="visible")

                cards = await page.query_selector_all(selector)
                print(f"✅ 关键词 [{keyword}] 找到 {len(cards)} 个结果")

                for card in cards:
                    if len(videos) >= limit: break
                    link_el = await card.query_selector("a[href*='/video/BV']")
                    if link_el:
                        href = await link_el.get_attribute("href")
                        # 格式化 URL
                        raw_url = f"https:{href}" if href.startswith("//") else href
                        clean_url = raw_url.split("?")[0]
                        if "bilibili.com/video/" in clean_url:
                            videos.append(clean_url)
            except Exception as e:
                print(f"⚠️ 关键词 [{keyword}] 检索超时或异常: {e}")
            finally:
                await page.close()
            return videos

    async def batch_search_bili(self, keywords, limit=2):
        all_found = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # 增加更加真实的浏览器环境参数
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            tasks = [self._single_search(context, kw, limit) for kw in keywords]
            results = await asyncio.gather(*tasks)
            for r in results: all_found.extend(r)
            await browser.close()
        return list(set(all_found))

    def download_with_ytdlp_enhanced(self, url, save_path, keyword, filename, act_path):
        ydl_opts = {
            'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=1080]+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': save_path,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiesfrombrowser': ('chrome',),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                self.save_to_csv({
                    "搜索关键词": keyword, "文件名": filename,
                    "标题": info.get('title'), "播放量": info.get('view_count'),
                    "点赞数": info.get('like_count'), "时长": info.get('duration_string'),
                    "发布日期": info.get('upload_date'), "视频链接": url
                }, act_path)
                return True
            except:
                return False

    async def make_audio(self, text, path):
        clean_text = re.sub(r'[^\w\s\u4e00-\u9fa5，。！？“”‘’（）：；、]', '', text)
        await edge_tts.Communicate(clean_text, TTS_VOICE).save(path)
        return AudioFileClip(path)

    def process_clip(self, clip, target_w=1920, target_h=1080):
        # 裁剪并 resize
        y1, y2 = int(clip.h * 0.12), int(clip.h * 0.88)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=y2)
        # 使用 on_color 替代 Composite 提高合成速度
        return cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')

    def get_clips(self, folder, target_dur):
        clips = []
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]
        if not v_files: return [], []
        video_cache, opened_vids, curr_dur = {}, [], 0
        while curr_dur < target_dur:
            f = random.choice(v_files)
            try:
                if f not in video_cache:
                    video = VideoFileClip(f)
                    video_cache[f] = video
                    opened_vids.append(video)
                else:
                    video = video_cache[f]
                d = min(video.duration - 0.5, random.uniform(30, 50))
                start = random.uniform(0.5, max(0.5, video.duration - d))
                sub = video.subclip(start, start + d)
                clips.append(self.process_clip(sub))
                curr_dur += d
            except:
                continue
        return clips, opened_vids


async def main():
    if not os.path.exists(JSON_PATH): return
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    p_name = re.sub(r'[\\/:*?"<>|]', '_', data['extreme_titles'][0][:10])
    auto = VideoAutomation(p_name)

    all_video_parts = []
    all_resources = []

    for act_id, act_info in data['video_script'].items():
        act_path = os.path.join(auto.project_dir, act_id)
        os.makedirs(act_path, exist_ok=True)

        # 1. 采集
        unique_urls = await auto.batch_search_bili(act_info['search_queries'], limit=2)

        # 2. 下载
        download_tasks = [
            asyncio.to_thread(auto.download_with_ytdlp_enhanced, url, os.path.join(act_path, f"raw_{i}.mp4"),
                              act_info['search_queries'][0], f"raw_{i}.mp4", act_path) for i, url in
            enumerate(unique_urls[:MAX_DOWNLOAD_PER_ACT])]
        if download_tasks: await asyncio.gather(*download_tasks)

        # 3. 剪辑
        a_path = os.path.join(act_path, "voice.mp3")
        a_clip = await auto.make_audio(act_info['content'], a_path)
        all_resources.append(a_clip)

        v_clips, act_videos = auto.get_clips(act_path, a_clip.duration)
        all_resources.extend(act_videos)

        if v_clips:
            act_combined = concatenate_videoclips(v_clips, method="compose").set_duration(a_clip.duration).set_audio(
                a_clip)
            all_video_parts.append(act_combined)

    # 4. 导出
    if all_video_parts:
        output_file = os.path.join(auto.project_dir, "FINAL_VIDEO_1080P.mp4")
        final_v = concatenate_videoclips(all_video_parts, method="compose")
        print(f"\n🎬 开始合成渲染 (设置 threads=4)...")
        try:
            final_v.write_videofile(
                output_file,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                threads=4,
                preset="superfast",
                bitrate="5000k"
            )
        finally:
            for res in all_resources:
                try:
                    res.close()
                    if hasattr(res, 'reader'): res.reader.close()
                except:
                    pass


if __name__ == "__main__":
    asyncio.run(main())