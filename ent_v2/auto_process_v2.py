import asyncio
import json
import os
import re
import random
import yt_dlp
import edge_tts
import subprocess
import shlex  # 增加：用于精确处理系统命令行参数
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
    def __init__(self, project_name, json_path, output_root):
        self.json_path = json_path
        self.output_root = output_root
        # 严格限制路径名，杜绝中文字符引起的 FFmpeg 滤镜崩溃
        short_name = "".join(filter(str.isalnum, project_name))[:10]
        self.project_dir = os.path.abspath(
            os.path.join(self.output_root, f"{short_name}_{datetime.now().strftime('%m%d_%H%M')}"))
        os.makedirs(self.project_dir, exist_ok=True)

    def simple_process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        y1 = int(clip.h * 0.10)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        return cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')

    def process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        y1 = int(clip.h * 0.10)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        main_v = cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')
        mask_h = int(target_h * 0.18)
        mask = ColorClip(size=(target_w, mask_h), color=(0, 0, 0)).set_opacity(0.8).set_duration(clip.duration)
        return CompositeVideoClip([main_v, mask.set_position(("center", "bottom"))])

    def generate_srt(self, full_text, total_duration, srt_path):
        clean_text = full_text.replace("\n", " ").strip()
        sentences = [s.strip() for s in re.split(r'[，。！？；\s]+', clean_text) if s.strip()]
        if not sentences: return
        total_chars = sum(len(s) for s in sentences)
        start_time = 0

        def format_srt_time(seconds):
            hrs, mins, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
            msecs = int(round((seconds - int(seconds)) * 1000))
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, s in enumerate(sentences):
                dur = (len(s) / total_chars) * total_duration
                end_time = start_time + dur
                f.write(f"{i + 1}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{s}\n\n")
                start_time = end_time

    def ffmpeg_render_final(self, video_path, srt_path, output_path):
        """满血版 FFmpeg 专属：物理路径强制关联 + 硬件加速渲染"""
        # 获取绝对路径
        abs_v = os.path.abspath(video_path)
        abs_s = os.path.abspath(srt_path)
        abs_o = os.path.abspath(output_path)

        # 核心转义：针对 Mac 绝对路径中的冒号进行特殊处理，确保滤镜能找到 srt
        safe_srt = abs_s.replace('\\', '/').replace(':', '\\:').replace("'", "'\\\\''")

        cmd = [
            'ffmpeg', '-y',
            '-i', abs_v,
            # 使用 subtitles 滤镜，force_style 确保字幕不会因为默认颜色太淡看不见
            '-vf',
            f"subtitles=filename='{safe_srt}':force_style='FontSize=12,MarginV=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1'",
            '-c:v', 'h264_videotoolbox', '-b:v', '4500k',  # 既然是 M1/M2，拉高码率确保画质
            '-c:a', 'copy',  # 直接流拷贝，确保声音 100% 还原
            '-map', '0:v:0',
            '-map', '0:a?',  # 自动抓取 tmp.mp4 里的所有音轨
            abs_o
        ]

        print(f"🎬 正在通过全路径烧录字幕...")
        try:
            # 直接运行，不再切换 cwd，全路径对轰最稳定
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.returncode != 0:
                print(f"❌ FFmpeg 详细报错: {process.stderr}")
                return False

            # 双重保险：检查文件是否存在且大小正常（大于 1MB）
            if os.path.exists(abs_o) and os.path.getsize(abs_o) > 1024 * 1024:
                return True
            return False
        except Exception as e:
            print(f"❌ 运行崩溃: {e}")
            return False

    async def _single_search(self, context, keyword, limit):
        async with SEARCH_SEMAPHORE:
            page = await context.new_page()
            try:
                await page.goto(f"https://search.bilibili.com/all?keyword={keyword}", wait_until="load", timeout=30000)
                cards = await page.query_selector_all(".bili-video-card, .video-list-item")
                urls = []
                for card in cards:
                    link_el = await card.query_selector("a[href*='/video/BV']")
                    if link_el:
                        href = await link_el.get_attribute("href")
                        urls.append(f"https:{href}" if href.startswith("//") else href)
                    if len(urls) >= limit: break
                return urls
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

    def download_with_ytdlp(self, url, save_path):
        ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]', 'outtmpl': save_path,
                    'quiet': True}
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
        clips, opened, curr, pool = [], [], 0, []
        while curr < target_dur:
            if not pool: pool = v_files.copy(); random.shuffle(pool)
            f = pool.pop()
            try:
                v = VideoFileClip(f, audio=False)
                opened.append(v)
                d = min(v.duration - 0.5, random.uniform(5, 8))
                clips.append(self.process_clip(v.subclip(0.5, 0.5 + d)));
                curr += d
            except:
                continue
        return clips, opened

    def get_interview_clips_fast(self, folder, target_dur):
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]
        if not v_files: return [], []
        clips, opened, curr, pool = [], [], 0, []
        while curr < target_dur:
            if not pool: pool = v_files.copy(); random.shuffle(pool)
            f = pool.pop()
            try:
                v = VideoFileClip(f, audio=True)
                opened.append(v)
                d = min(v.duration, target_dur - curr)
                clips.append(self.simple_process_clip(v.subclip(0, d)));
                curr += d
                if curr >= target_dur: break
            except:
                continue
        return clips, opened


async def main(json_path, output_root, target_total_duration=1800):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    auto = VideoAutomation(data.get('extreme_titles', ['Video'])[0], json_path, output_root)
    all_parts, resources, full_txt = [], [], ""

    for act_id, info in data['video_script'].items():
        act_path = os.path.join(auto.project_dir, act_id);
        os.makedirs(act_path, exist_ok=True)
        urls = await auto.batch_search_bili(info['search_queries'], limit=2)
        await asyncio.gather(
            *[asyncio.to_thread(auto.download_with_ytdlp, u, os.path.join(act_path, f"{i}.mp4")) for i, u in
              enumerate(urls)])
        a_clip = await auto.make_audio(info['content'], os.path.join(act_path, "v.mp3"))
        v_clips, vids = auto.get_clips(act_path, a_clip.duration)
        resources.extend(vids);
        resources.append(a_clip)
        all_parts.append(concatenate_videoclips(v_clips, method="compose").set_audio(a_clip))
        full_txt += info['content'] + " "

    script_dur = sum(p.duration for p in all_parts)
    dynamic_target = target_total_duration + random.randint(-120, 120)

    if script_dur < dynamic_target:
        needed = dynamic_target - script_dur
        i_path = os.path.join(auto.project_dir, "extend");
        os.makedirs(i_path, exist_ok=True)
        queries = data.get("protagonist_interview_queries", [])
        if queries:
            i_urls = await auto.batch_search_bili(queries, limit=3)
            await asyncio.gather(
                *[asyncio.to_thread(auto.download_with_ytdlp, u, os.path.join(i_path, f"{i}.mp4")) for i, u in
                  enumerate(i_urls)])
            i_clips, i_vids = auto.get_interview_clips_fast(i_path, needed)
            resources.extend(i_vids)
            if i_clips: all_parts.append(concatenate_videoclips(i_clips, method="compose"))

    if all_parts:
        final_video = concatenate_videoclips(all_parts, method="compose")
        tmp, srt, out = os.path.join(auto.project_dir, "tmp.mp4"), os.path.join(auto.project_dir,
                                                                                "sub.srt"), os.path.join(
            auto.project_dir, "FINAL.mp4")

        auto.generate_srt(full_txt, script_dur, srt)

        # 强制显式包含音频流
        print(f"🚀 渲染临时视频 (时长: {final_video.duration / 60:.1f}min)...")
        final_video.write_videofile(
            tmp,
            fps=24,
            codec="h264_videotoolbox",
            bitrate="3500k",
            audio=True,
            audio_codec="aac",
            temp_audiofile=os.path.join(auto.project_dir, "temp-audio.m4a"),
            remove_temp=True
        )

        print("📝 正在通过 FFmpeg 烧录字幕...")
        if not auto.ffmpeg_render_final(tmp, srt, out):
            print("⚠️ 烧录发生错误，请检查上方 FFmpeg 详细报错")
            if not os.path.exists(out): os.rename(tmp, out)

        for r in resources:
            try:
                r.close()
            except:
                pass


if __name__ == "__main__":
    TARGET_SECONDS = 20
    selected_enum = TaskType.A4
    _, _, t_path = selected_enum.value


    async def run_tasks():
        for subdir in sorted(os.listdir(t_path)):
            p = os.path.join(t_path, subdir)
            if not os.path.isdir(p) or os.path.exists(os.path.join(p, "output")): continue
            script_json_path = os.path.join(p, "script.json")
            if not os.path.exists(script_json_path): continue

            # 空 JSON 检查逻辑
            try:
                with open(script_json_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content: continue
                    json_data = json.loads(content)
                    if not json_data: continue
            except:
                continue

            print(f"\n🎬 开始任务: {subdir}")
            try:
                await main(script_json_path, os.path.join(p, "output"), TARGET_SECONDS)
                print(f"✅ 任务成功: {subdir}\n")
            except Exception as e:
                print(f"❌ 任务崩溃: {subdir} -> {e}\n")


    asyncio.run(run_tasks())