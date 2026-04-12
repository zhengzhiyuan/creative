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

    def calculate_relevance(self, title, keyword):
        """简单相关性评分算法"""
        title = title.lower()
        keyword = keyword.lower()
        # 排除词黑名单
        blacklist = ["直播", "回放", "合集", "预告", "mv", "混剪"]
        if any(w in title for w in blacklist):
            return 0
        # 计算关键词匹配度
        score = 0
        # 1. 关键词完全包含
        if keyword in title: score += 50
        # 2. 分词匹配（简单处理）
        for word in list(keyword):
            if word in title: score += 2
        return score

    async def _single_search(self, context, keyword, limit):
        async with SEARCH_SEMAPHORE:
            candidate_videos = []
            page = await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 720})

            url = f"https://search.bilibili.com/all?keyword={keyword}"
            try:
                await page.goto(url, wait_until="load", timeout=30000)
                await page.evaluate("window.scrollTo(0, 500)")
                await asyncio.sleep(1)

                selector = ".bili-video-card, .video-list-item"
                await page.wait_for_selector(selector, timeout=20000)
                cards = await page.query_selector_all(selector)

                for card in cards:
                    # 获取标题用于校验
                    title_el = await card.query_selector("h3, .title")
                    link_el = await card.query_selector("a[href*='/video/BV']")

                    if title_el and link_el:
                        title = await title_el.inner_text()
                        href = await link_el.get_attribute("href")

                        # 执行算法过滤
                        score = self.calculate_relevance(title, keyword)
                        if score > 10:  # 只有超过基础分才加入候选列表
                            clean_url = (f"https:{href}" if href.startswith("//") else href).split("?")[0]
                            candidate_videos.append({"url": clean_url, "score": score})

                # 按得分排序，取前 limit 个
                candidate_videos.sort(key=lambda x: x['score'], reverse=True)
                final_urls = [v['url'] for v in candidate_videos[:limit]]
                print(f"✅ 关键词 [{keyword}] 检索完成，筛选出 {len(final_urls)} 个高质量匹配结果")
                return final_urls

            except Exception as e:
                print(f"⚠️ 检索异常: {e}")
            finally:
                await page.close()
            return []

    async def batch_search_bili(self, keywords, limit=2):
        all_found = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
            tasks = [self._single_search(context, kw, limit) for kw in keywords]
            results = await asyncio.gather(*tasks)
            for r in results: all_found.extend(r)
            await browser.close()
        return list(set(all_found))

    def download_with_ytdlp_enhanced(self, url, save_path, keyword, filename, act_path):
        ydl_opts = {
            'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/best',
            'merge_output_format': 'mp4',
            'outtmpl': save_path,
            'quiet': True,
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
        # 深度裁剪彻底去除水印 (顶部12% 底部12%)
        y1, y2 = int(clip.h * 0.12), int(clip.h * 0.88)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=y2)
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

        # 1. 采集（带语义过滤）
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

    # 4. 导出 (VideoToolbox 硬件加速)
    if all_video_parts:
        output_file = os.path.join(auto.project_dir, "FINAL_VIDEO_1080P.mp4")
        final_v = concatenate_videoclips(all_video_parts, method="compose")
        try:
            final_v.write_videofile(
                output_file,
                fps=24,
                codec="h264_videotoolbox",
                audio_codec="aac",
                threads=4,
                bitrate="5000k"
            )
        finally:
            for res in all_resources:
                try:
                    res.close()
                except:
                    pass


if __name__ == "__main__":
    asyncio.run(main())