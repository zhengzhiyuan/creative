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
from datetime import datetime
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip, CompositeVideoClip
import moviepy.video.fx.all as vfx

from ent_v2.config import TaskType

# ================= 配置区 =================
TTS_VOICE = "zh-CN-XiaoxiaoNeural"
SEARCH_SEMAPHORE = asyncio.Semaphore(2)
TARGET_W = 854
TARGET_H = 480


class VideoAutomation:
    def __init__(self, project_name, json_path, output_root, max_download_per_act=3):
        self.json_path = json_path
        self.output_root = output_root
        self.max_download_per_act = max_download_per_act
        self.project_dir = os.path.abspath(
            os.path.join(self.output_root, f"{project_name}_{datetime.now().strftime('%m%d_%H%M')}"))
        os.makedirs(self.project_dir, exist_ok=True)

    # --- 逻辑修改 3: 补充视频也需要截取顶部水印 ---
    def simple_process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        """填充时长视频专用：截取顶部水印后缩放对齐"""
        y1 = int(clip.h * 0.10)  # 同样截取顶部 10%
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        return cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')

    def process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        y1 = int(clip.h * 0.10)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        main_v = cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')
        mask_h = int(target_h * 0.18)
        mask = ColorClip(size=(target_w, mask_h), color=(0, 0, 0)).set_opacity(0.8).set_duration(clip.duration)
        return CompositeVideoClip([main_v, mask.set_position(("center", "bottom"))])

    # --- 逻辑修改 1: 增强字幕生成的健壮性 ---
    def generate_srt(self, full_text, total_duration, srt_path):
        # 清洗文本，确保没有奇怪的转义符影响 FFmpeg
        clean_text = full_text.replace("\n", " ").replace("\r", " ").strip()
        sentences = [s.strip() for s in re.split(r'[，。！？；\s]+', clean_text) if s.strip()]
        if not sentences: return

        total_chars = sum(len(s) for s in sentences)
        start_time = 0

        def format_srt_time(seconds):
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            msecs = int(round((seconds - int(seconds)) * 1000))
            if msecs == 1000:  # 防止四舍五入进位溢出
                secs += 1
                msecs = 0
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, s in enumerate(sentences):
                # 按字数比例分配时间，确保字幕不重叠且覆盖全时长
                duration = (len(s) / total_chars) * total_duration
                end_time = start_time + duration
                f.write(f"{i + 1}\n")
                f.write(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n")
                f.write(f"{s}\n\n")
                start_time = end_time

    def ffmpeg_render_final(self, video_path, srt_path, output_path):
        # 兼容 Mac 的路径处理
        abs_srt_path = os.path.abspath(srt_path).replace("\\", "/").replace(":", "\\:")
        # 字体改为通用的粗体，MarginV 调高防止被平台进度条遮挡
        filter_str = f"subtitles='{abs_srt_path}':force_style='Alignment=2,FontSize=13,FontName=Arial,Bold=1,MarginV=25,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=1'"

        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', filter_str,
            '-c:v', 'h264_videotoolbox',  # 保持 Mac 硬件加速
            '-b:v', '3000k',
            '-c:a', 'copy',
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except Exception as e:
            print(f"❌ FFmpeg 报错: {e}")
            return False

    # 剩余搜索/下载逻辑保持原样...
    async def _single_search(self, context, keyword, limit):
        async with SEARCH_SEMAPHORE:
            candidate_videos = []
            page = await context.new_page()
            try:
                await page.goto(f"https://search.bilibili.com/all?keyword={keyword}", wait_until="load", timeout=30000)
                await page.evaluate("window.scrollTo(0, 500)")
                await asyncio.sleep(1)
                cards = await page.query_selector_all(".bili-video-card, .video-list-item")
                for card in cards:
                    title_el = await card.query_selector("h3, .title")
                    link_el = await card.query_selector("a[href*='/video/BV']")
                    if title_el and link_el:
                        title = await title_el.inner_text()
                        href = await link_el.get_attribute("href")
                        score = self.calculate_relevance(title, keyword)
                        if score > 10:
                            candidate_videos.append(
                                {"url": f"https:{href}" if href.startswith("//") else href, "score": score})
                candidate_videos.sort(key=lambda x: x['score'], reverse=True)
                return [v['url'].split("?")[0] for v in candidate_videos[:limit]]
            except:
                return []
            finally:
                await page.close()

    async def batch_search_bili(self, keywords, limit=2):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            results = await asyncio.gather(*[self._single_search(context, kw, limit) for kw in keywords])
            await browser.close()
            return list(set([item for sublist in results for item in sublist]))

    def download_with_ytdlp_enhanced(self, url, save_path, keyword, filename, act_path):
        ydl_opts = {'format': 'bestvideo[height<=480]+bestaudio/best', 'outtmpl': save_path, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.extract_info(url, download=True); return True
            except:
                return False

    async def make_audio(self, text, path):
        await edge_tts.Communicate(text, TTS_VOICE).save(path)
        return AudioFileClip(path)

    def get_clips(self, folder, target_dur):
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]
        if not v_files: return [ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0)).set_duration(target_dur)], []
        clips, opened, curr = [], [], 0
        while curr < target_dur:
            v = VideoFileClip(random.choice(v_files), audio=False);
            opened.append(v)
            d = min(v.duration - 0.5, random.uniform(5, 8))
            sub = v.subclip(0.5, 0.5 + d)
            clips.append(self.process_clip(sub));
            curr += d
        return clips, opened

    def get_interview_clips(self, folder, target_dur):
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]
        if not v_files: return [], []
        clips, opened, curr = [], [], 0
        while curr < target_dur:
            v = VideoFileClip(random.choice(v_files), audio=True);
            opened.append(v)
            d = min(v.duration - 0.5, random.uniform(10, 20))
            if (target_dur - curr) < d: d = target_dur - curr
            sub = v.subclip(0, d)
            clips.append(self.simple_process_clip(sub));
            curr += d
        return clips, opened


async def main(json_path, output_root, enable_extend=True, target_total_duration=1200):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    auto = VideoAutomation("Video", json_path, output_root)
    all_parts, resources, full_txt = [], [], ""

    # 1. 主脚本部分
    for act_id, info in data['video_script'].items():
        act_path = os.path.join(auto.project_dir, act_id);
        os.makedirs(act_path, exist_ok=True)
        urls = await auto.batch_search_bili(info['search_queries'], limit=2)
        await asyncio.gather(
            *[asyncio.to_thread(auto.download_with_ytdlp_enhanced, u, os.path.join(act_path, f"{i}.mp4"), "", "", "")
              for i, u in enumerate(urls)])

        a_clip = await auto.make_audio(info['content'], os.path.join(act_path, "v.mp3"))
        v_clips, vids = auto.get_clips(act_path, a_clip.duration)
        resources.extend(vids);
        resources.append(a_clip)

        part = concatenate_videoclips(v_clips, method="compose").set_audio(a_clip)
        all_parts.append(part)
        full_txt += info['content'] + " "

    script_dur = sum(p.duration for p in all_parts)

    # --- 逻辑修改 2: 动态时长补充 (target -10min ~ +10min) ---
    # target_total_duration 现在设为 1200 (20min)，允许前后 600s 浮动
    dynamic_target = target_total_duration + random.randint(-600, 600)

    if enable_extend and script_dur < dynamic_target:
        needed = dynamic_target - script_dur
        i_path = os.path.join(auto.project_dir, "extend");
        os.makedirs(i_path, exist_ok=True)
        i_urls = await auto.batch_search_bili(data.get("protagonist_interview_queries", []), limit=3)
        await asyncio.gather(
            *[asyncio.to_thread(auto.download_with_ytdlp_enhanced, u, os.path.join(i_path, f"{i}.mp4"), "", "", "") for
              i, u in enumerate(i_urls)])
        i_clips, i_vids = auto.get_interview_clips(i_path, needed)
        resources.extend(i_vids)
        if i_clips: all_parts.append(concatenate_videoclips(i_clips, method="compose"))

    if all_parts:
        final = concatenate_videoclips(all_parts, method="compose")
        tmp = os.path.join(auto.project_dir, "tmp.mp4")
        srt = os.path.join(auto.project_dir, "sub.srt")
        out = os.path.join(auto.project_dir, "FINAL.mp4")

        # 仅为主脚本部分生成 SRT 字幕
        auto.generate_srt(full_txt, script_dur, srt)

        final.write_videofile(tmp, fps=24, codec="h264_videotoolbox", audio_codec="aac")
        if not auto.ffmpeg_render_final(tmp, srt, out):
            os.rename(tmp, out)

        for r in resources:
            try:
                r.close()
            except:
                pass


if __name__ == "__main__":
    # --- 逻辑修改 2: 修改基准时长 ---
    # 设为 1200s (25min)，动态代码会自动在 10min~30min 之间随机补充
    TARGET_SECONDS = 1500

    selected_enum = TaskType.A4
    _, _, t_path = selected_enum.value


    async def run_tasks():
        for subdir in os.listdir(t_path):
            p = os.path.join(t_path, subdir)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "script.json")):
                await main(os.path.join(p, "script.json"), os.path.join(p, "output"), True, TARGET_SECONDS)


    asyncio.run(run_tasks())