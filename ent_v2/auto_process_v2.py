import asyncio
import json
import os
import re
import random
import csv
import yt_dlp
import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip, CompositeVideoClip, \
    ImageClip
import moviepy.video.fx.all as vfx
from datetime import datetime

from ent_v2.config import TaskType

# ================= 配置区 =================
TTS_VOICE = "zh-CN-XiaoxiaoNeural"
SEARCH_SEMAPHORE = asyncio.Semaphore(2)

TARGET_W = 854
TARGET_H = 480


# ==========================================

class VideoAutomation:
    def __init__(self, project_name, json_path, output_root, max_download_per_act=3):
        """
        初始化视频自动化处理类
        """
        self.json_path = json_path
        self.output_root = output_root
        self.max_download_per_act = max_download_per_act
        self.project_dir = os.path.join(self.output_root, f"{project_name}_{datetime.now().strftime('%m%d_%H%M')}")
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
        title = title.lower()
        keyword = keyword.lower()
        blacklist = ["直播", "回放", "合集", "预告", "mv", "混剪"]
        if any(w in title for w in blacklist): return 0
        score = 0
        if keyword in title: score += 50
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
                    title_el = await card.query_selector("h3, .title")
                    link_el = await card.query_selector("a[href*='/video/BV']")
                    if title_el and link_el:
                        title = await title_el.inner_text()
                        href = await link_el.get_attribute("href")
                        score = self.calculate_relevance(title, keyword)
                        if score > 10:
                            clean_url = (f"https:{href}" if href.startswith("//") else href).split("?")[0]
                            candidate_videos.append({"url": clean_url, "score": score})
                candidate_videos.sort(key=lambda x: x['score'], reverse=True)
                return [v['url'] for v in candidate_videos[:limit]]
            except:
                return []
            finally:
                await page.close()

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
            'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/best',
            'merge_output_format': 'mp4',
            'outtmpl': save_path,
            'quiet': True,
            'cookiesfrombrowser': ('chrome',),
            'nocheckcertificate': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                self.save_to_csv({"搜索关键词": keyword, "文件名": filename, "标题": info.get('title'),
                                  "播放量": info.get('view_count'), "点赞数": info.get('like_count'),
                                  "时长": info.get('duration_string'), "发布日期": info.get('upload_date'),
                                  "视频链接": url}, act_path)
                return True
            except:
                return False

    async def make_audio(self, text, path):
        clean_text = re.sub(r'[^\w\s\u4e00-\u9fa5，。！？“”‘’（）：；、]', '', text)
        await edge_tts.Communicate(clean_text, TTS_VOICE).save(path)
        return AudioFileClip(path)

    def process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        y1 = int(clip.h * 0.10)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        main_v = cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')
        mask_h = int(target_h * 0.18)
        mask = ColorClip(size=(target_w, mask_h), color=(0, 0, 0)).set_opacity(0.8).set_duration(clip.duration)
        return CompositeVideoClip([main_v, mask.set_position(("center", "bottom"))])

    def generate_subtitle_clip(self, full_text, total_duration):
        sentences = [s.strip() for s in re.split(r'[，。！？；\s]+', full_text) if s.strip()]
        if not sentences: return ColorClip((1, 1), ismask=True).set_duration(total_duration)

        total_chars = sum(len(s) for s in sentences)
        clips = []
        mask_h = int(TARGET_H * 0.18)

        font_paths = ["/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                      "C:\\Windows\\Fonts\\msyh.ttc"]
        font_path = next((p for p in font_paths if os.path.exists(p)), None)
        font = ImageFont.truetype(font_path, 22) if font_path else ImageFont.load_default()

        start_time = 0
        for s in sentences:
            duration = (len(s) / total_chars) * total_duration
            img = Image.new('RGBA', (TARGET_W, mask_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            try:
                w, h = draw.textsize(s, font=font) if hasattr(draw, 'textsize') else (TARGET_W // 2, 22)
            except:
                w, h = TARGET_W // 2, 22
            draw.text(((TARGET_W - w) // 2, (mask_h - h) // 2), s, font=font, fill="white")
            s_clip = ImageClip(np.array(img)).set_duration(duration).set_start(start_time).set_position(
                ('center', 'bottom'))
            clips.append(s_clip)
            start_time += duration
        return CompositeVideoClip(clips, size=(TARGET_W, TARGET_H))

    def get_clips(self, folder, target_dur):
        clips = []
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]

        if not v_files:
            for root, dirs, files in os.walk(self.project_dir):
                for f in files:
                    if f.endswith(".mp4"): v_files.append(os.path.join(root, f))

        if not v_files:
            return [ColorClip(size=(TARGET_W, TARGET_H), color=(20, 20, 20)).set_duration(target_dur)], []

        video_cache, opened_vids, curr_dur = {}, [], 0
        while curr_dur < target_dur:
            f = random.choice(v_files)
            try:
                if f not in video_cache:
                    video = VideoFileClip(f, audio=False)
                    video_cache[f] = video
                    opened_vids.append(video)
                else:
                    video = video_cache[f]
                d = min(video.duration - 0.5, random.uniform(5, 8))
                start = random.uniform(0.5, max(0.5, video.duration - d))
                sub = video.subclip(start, start + d)
                clips.append(self.process_clip(sub))
                curr_dur += d
            except:
                continue
        return clips, opened_vids

    def get_interview_clips(self, interview_folder, target_dur):
        """专门处理采访视频素材的循环补充"""
        clips = []
        v_files = [os.path.join(interview_folder, f) for f in os.listdir(interview_folder) if f.endswith('.mp4')]

        if not v_files:
            return [], []

        video_cache, opened_vids, curr_dur = {}, [], 0
        while curr_dur < target_dur:
            f = random.choice(v_files)
            try:
                if f not in video_cache:
                    video = VideoFileClip(f, audio=True)
                    video_cache[f] = video
                    opened_vids.append(video)
                else:
                    video = video_cache[f]

                d = min(video.duration - 0.5, random.uniform(10, 20))
                if (target_dur - curr_dur) < d:
                    d = target_dur - curr_dur

                start = random.uniform(0, max(0, video.duration - d))
                sub = video.subclip(start, start + d)
                clips.append(self.process_clip(sub))
                curr_dur += d
            except:
                break
        return clips, opened_vids


async def main(json_path, output_root, enable_extend=True, target_total_duration=1800, max_download_per_act=3):
    if not os.path.exists(json_path):
        print(f"⚠️ JSON文件不存在: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    p_name = re.sub(r'[\\/:*?"<>|]', '_', data['extreme_titles'][0][:10])
    auto = VideoAutomation(p_name, json_path=json_path,
                           output_root=output_root,
                           max_download_per_act=max_download_per_act)
    all_video_parts, all_resources = [], []

    # 1. 正常的 Script 视频建设
    for act_id, act_info in data['video_script'].items():
        act_path = os.path.join(auto.project_dir, act_id)
        os.makedirs(act_path, exist_ok=True)

        unique_urls = await auto.batch_search_bili(act_info['search_queries'], limit=2)
        download_tasks = [
            asyncio.to_thread(auto.download_with_ytdlp_enhanced, url, os.path.join(act_path, f"raw_{i}.mp4"),
                              act_info['search_queries'][0], f"raw_{i}.mp4", act_path) for i, url in
            enumerate(unique_urls[:auto.max_download_per_act])]
        if download_tasks: await asyncio.gather(*download_tasks)

        a_path = os.path.join(act_path, "voice.mp3")
        a_clip = await auto.make_audio(act_info['content'], a_path)
        all_resources.append(a_clip)

        v_clips, act_videos = auto.get_clips(act_path, a_clip.duration)
        all_resources.extend(act_videos)

        if v_clips:
            act_video_stream = concatenate_videoclips(v_clips, method="compose").set_duration(a_clip.duration)
            txt_layer = auto.generate_subtitle_clip(act_info['content'], a_clip.duration)
            act_combined = CompositeVideoClip([act_video_stream, txt_layer]).set_audio(a_clip)
            all_video_parts.append(act_combined)

    # 2. 补充采访内容（确保最终视频至少达到目标时长）
    if enable_extend and "protagonist_interview_queries" in data:
        current_dur = sum(c.duration for c in all_video_parts)

        if current_dur < target_total_duration:
            needed_dur = target_total_duration - current_dur
            print(f"🎬 触发时长补充：当前 {current_dur:.1f}s，需补充 {needed_dur:.1f}s")

            interview_path = os.path.join(auto.project_dir, "interview_extend")
            os.makedirs(interview_path, exist_ok=True)

            interview_urls = await auto.batch_search_bili(data["protagonist_interview_queries"], limit=3)
            i_tasks = [
                asyncio.to_thread(auto.download_with_ytdlp_enhanced, url,
                                  os.path.join(interview_path, f"interview_{i}.mp4"),
                                  data["protagonist_interview_queries"][0], f"interview_{i}.mp4", interview_path)
                for i, url in enumerate(interview_urls)
            ]
            if i_tasks: await asyncio.gather(*i_tasks)

            i_clips, i_vids = auto.get_interview_clips(interview_path, needed_dur)
            all_resources.extend(i_vids)

            if i_clips:
                extend_part = concatenate_videoclips(i_clips, method="compose").set_duration(needed_dur)
                all_video_parts.append(extend_part)
                final_duration = current_dur + needed_dur
                print(f"✅ 补充完成：最终视频时长约 {final_duration:.1f}s ({final_duration/60:.1f}分钟)")
        else:
            print(f"ℹ️ 当前时长 {current_dur:.1f}s 已达到目标，无需补充")

    if all_video_parts:
        output_file = os.path.join(auto.project_dir, "FINAL_VIDEO_480P.mp4")
        final_v = concatenate_videoclips(all_video_parts, method="compose")
        try:
            final_v.write_videofile(output_file, fps=24, codec="h264_videotoolbox", audio_codec="aac", threads=4,
                                    bitrate="1500k")
        finally:
            for res in all_resources:
                try:
                    res.close()
                except:
                    pass


async def process_single_subdir(subdir, subdir_path, script_json_path, output_dir, enable_extend, target_seconds):
    """处理单个子目录的异步任务"""
    print(f"\n🎬 开始处理: {subdir}")
    try:
        await main(
            json_path=script_json_path,
            output_root=output_dir,
            enable_extend=enable_extend,
            target_total_duration=target_seconds
        )
        print(f"✅ 完成处理: {subdir}\n")
        return True
    except Exception as e:
        print(f"❌ 处理 {subdir} 时出错: {e}\n")
        return False


if __name__ == "__main__":
    # 1. 设置补充行为配置
    ENABLE_EXTEND = True
    TARGET_SECONDS = 1800  # 30分钟

    # 2. 从枚举中提取基础值
    selected_enum = TaskType.A1
    t_name, t_url, t_path = selected_enum.value

    # 3. 遍历 t_path 目录下的所有子目录
    if os.path.exists(t_path) and os.path.isdir(t_path):
        # 收集所有需要处理的子目录
        tasks_to_process = []
        
        for subdir in os.listdir(t_path):
            subdir_path = os.path.join(t_path, subdir)
            
            # 只处理目录
            if not os.path.isdir(subdir_path):
                continue
            
            script_json_path = os.path.join(subdir_path, "script.json")
            output_dir = os.path.join(subdir_path, "output")
            
            # 检查 script.json 是否存在
            if not os.path.exists(script_json_path):
                print(f"⚠️ 跳过 {subdir}: script.json 不存在")
                continue
            
            # 检查 script.json 是否为非空 JSON
            try:
                with open(script_json_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        print(f"⚠️ 跳过 {subdir}: script.json 为空文件")
                        continue
                    json_data = json.loads(content)
                    if not json_data:
                        print(f"⚠️ 跳过 {subdir}: script.json 是空 JSON")
                        continue
            except json.JSONDecodeError as e:
                print(f"⚠️ 跳过 {subdir}: script.json 格式错误 - {e}")
                continue
            except Exception as e:
                print(f"⚠️ 跳过 {subdir}: 读取 script.json 失败 - {e}")
                continue
            
            # 检查 output 文件夹是否已存在
            if os.path.exists(output_dir):
                print(f"⚠️ 跳过 {subdir}: output 文件夹已存在")
                continue
            
            # 满足条件，添加到待处理列表
            tasks_to_process.append((subdir, subdir_path, script_json_path, output_dir))
        
        # 在同一个事件循环中顺序处理所有任务
        if tasks_to_process:
            async def run_all_tasks():
                for subdir, subdir_path, script_json_path, output_dir in tasks_to_process:
                    await process_single_subdir(
                        subdir, subdir_path, script_json_path, output_dir, 
                        ENABLE_EXTEND, TARGET_SECONDS
                    )
            
            asyncio.run(run_all_tasks())
        else:
            print("\n📭 没有需要处理的任务")
    else:
        print(f"⚠️ t_path 目录不存在: {t_path}")
