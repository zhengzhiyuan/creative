import asyncio
import json
import os
import re
import random
import csv
import yt_dlp
import edge_tts
import numpy as np
import subprocess
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

    def generate_srt(self, full_text, total_duration, srt_path):
        """优化：不再生成 ImageClip 序列，改为生成 SRT 字幕文件"""
        sentences = [s.strip() for s in re.split(r'[，。！？；\s]+', full_text) if s.strip()]
        if not sentences: return

        total_chars = sum(len(s) for s in sentences)
        start_time = 0

        def format_srt_time(seconds):
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            msecs = int((seconds - int(seconds)) * 1000)
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, s in enumerate(sentences):
                duration = (len(s) / total_chars) * total_duration
                end_time = start_time + duration
                f.write(f"{i + 1}\n")
                f.write(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n")
                f.write(f"{s}\n\n")
                start_time = end_time

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
        clips = []
        v_files = [os.path.join(interview_folder, f) for f in os.listdir(interview_folder) if f.endswith('.mp4')]
        if not v_files: return [], []
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
                if (target_dur - curr_dur) < d: d = target_dur - curr_dur
                start = random.uniform(0, max(0, video.duration - d))
                sub = video.subclip(start, start + d)
                clips.append(self.process_clip(sub))
                curr_dur += d
            except:
                break
        return clips, opened_vids

    def ffmpeg_render_final(self, video_path, srt_path, output_path):
        """
        核心优化点：使用 FFmpeg 滤镜高效渲染字幕和编码
        """
        # 字体路径适配
        font_paths = ["/System/Library/Fonts/PingFang.ttc", "C\\:/Windows/Fonts/msyh.ttc"]
        font_path = next((p for p in font_paths if os.path.exists(p.replace('\\', ''))), "Arial")

        # 构建 FFmpeg 命令
        # 使用 subtitles 滤镜直接渲染字幕文件
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f"subtitles='{srt_path}':force_style='Alignment=2,FontSize=11,FontName=PingFang SC,MarginV=15'",
            '-c:v', 'h264_videotoolbox',  # 硬件加速
            '-b:v', '1500k',
            '-c:a', 'copy',
            output_path
        ]

        try:
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg 渲染失败: {e}")
            return False


async def main(json_path, output_root, enable_extend=True, target_total_duration=1800, max_download_per_act=3):
    if not os.path.exists(json_path):
        print(f"⚠️ JSON文件不存在: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    p_name = re.sub(r'[\\/:*?"<>|]', '_', data['extreme_titles'][0][:10])
    auto = VideoAutomation(p_name, json_path=json_path, output_root=output_root,
                           max_download_per_act=max_download_per_act)
    all_video_parts, all_resources = [], []
    full_script_content = ""

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
            act_combined = act_video_stream.set_audio(a_clip)
            all_video_parts.append(act_combined)
            full_script_content += act_info['content'] + " "

    # 2. 补充采访内容
    current_script_dur = sum(c.duration for c in all_video_parts)
    if enable_extend and "protagonist_interview_queries" in data:
        if current_script_dur < target_total_duration:
            needed_dur = target_total_duration - current_script_dur
            print(f"🎬 时长补充：当前 {current_script_dur:.1f}s，需补充 {needed_dur:.1f}s")
            interview_path = os.path.join(auto.project_dir, "interview_extend")
            os.makedirs(interview_path, exist_ok=True)
            interview_urls = await auto.batch_search_bili(data["protagonist_interview_queries"], limit=3)
            i_tasks = [asyncio.to_thread(auto.download_with_ytdlp_enhanced, url,
                                         os.path.join(interview_path, f"interview_{i}.mp4"),
                                         data["protagonist_interview_queries"][0], f"interview_{i}.mp4", interview_path)
                       for i, url in enumerate(interview_urls)]
            if i_tasks: await asyncio.gather(*i_tasks)
            i_clips, i_vids = auto.get_interview_clips(interview_path, needed_dur)
            all_resources.extend(i_vids)
            if i_clips:
                extend_part = concatenate_videoclips(i_clips, method="compose").set_duration(needed_dur)
                all_video_parts.append(extend_part)

    if all_video_parts:
        temp_video = os.path.join(auto.project_dir, "TEMP_NO_SUB.mp4")
        srt_file = os.path.join(auto.project_dir, "subtitles.srt")
        output_file = os.path.join(auto.project_dir, "FINAL_VIDEO_480P.mp4")

        # 合并视频流（这一步由 MoviePy 完成拼接，但不进行复杂的图层叠加）
        final_concat = concatenate_videoclips(all_video_parts, method="compose")

        # 生成 SRT 字幕文件（仅针对前段有脚本的部分）
        auto.generate_srt(full_script_content, current_script_dur, srt_file)

        try:
            # 第一步：快速导出无字幕视频
            print("🚀 正在导出基础视频流...")
            final_concat.write_videofile(temp_video, fps=24, codec="h264_videotoolbox", audio_codec="aac",
                                         bitrate="2000k")

            # 第二步：使用 FFmpeg 快速烧录字幕
            if os.path.exists(srt_file):
                print("📝 正在使用 FFmpeg 烧录字幕...")
                auto.ffmpeg_render_final(temp_video, srt_file, output_file)
                if os.path.exists(output_file):
                    os.remove(temp_video)  # 清理中间文件
            else:
                os.rename(temp_video, output_file)

            print(f"✅ 视频制作完成: {output_file}")
        finally:
            for res in all_resources:
                try:
                    res.close()
                except:
                    pass


async def process_single_subdir(subdir, subdir_path, script_json_path, output_dir, enable_extend, target_seconds):
    print(f"\n🎬 开始处理: {subdir}")
    try:
        await main(json_path=script_json_path, output_root=output_dir, enable_extend=enable_extend,
                   target_total_duration=target_seconds)
        return True
    except Exception as e:
        print(f"❌ 处理出错: {e}")
        return False


if __name__ == "__main__":
    ENABLE_EXTEND = True
    TARGET_SECONDS = 1800
    selected_enum = TaskType.A1
    t_name, t_url, t_path = selected_enum.value

    if os.path.exists(t_path) and os.path.isdir(t_path):
        tasks_to_process = []
        for subdir in os.listdir(t_path):
            subdir_path = os.path.join(t_path, subdir)
            if not os.path.isdir(subdir_path): continue
            script_json_path = os.path.join(subdir_path, "script.json")
            output_dir = os.path.join(subdir_path, "output")
            if not os.path.exists(script_json_path): continue
            if os.path.exists(output_dir): continue
            tasks_to_process.append((subdir, subdir_path, script_json_path, output_dir))

        if tasks_to_process:
            async def run_all_tasks():
                for subdir, subdir_path, script_json_path, output_dir in tasks_to_process:
                    await process_single_subdir(subdir, subdir_path, script_json_path, output_dir, ENABLE_EXTEND,
                                                TARGET_SECONDS)


            asyncio.run(run_all_tasks())