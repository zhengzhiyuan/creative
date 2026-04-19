import asyncio
import json
import os
import re
import random
import yt_dlp
import edge_tts
import subprocess
from datetime import datetime
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip, CompositeVideoClip, TextClip
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
        # 简化目录名，避免系统路径解析错误
        short_name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '_', project_name[:15])
        self.project_dir = os.path.abspath(
            os.path.join(self.output_root, f"{short_name}_{datetime.now().strftime('%m%d_%H%M')}"))
        os.makedirs(self.project_dir, exist_ok=True)

    def simple_process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        """处理补充视频：去水印，无遮罩"""
        # 裁切顶部 10% 去掉水印
        y1 = int(clip.h * 0.10)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        return cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')

    def process_clip(self, clip, target_w=TARGET_W, target_h=TARGET_H):
        """处理主脚本视频：去水印，带半透明遮罩"""
        y1 = int(clip.h * 0.10)
        cropped = vfx.crop(clip, x1=0, y1=y1, x2=clip.w, y2=clip.h)
        main_v = cropped.resize(height=target_h).on_color(size=(target_w, target_h), color=(0, 0, 0), pos='center')
        # 底部遮罩，为字幕提供背景
        mask_h = int(target_h * 0.18)
        mask = ColorClip(size=(target_w, mask_h), color=(0, 0, 0)).set_opacity(0.8).set_duration(clip.duration)
        return CompositeVideoClip([main_v, mask.set_position(("center", "bottom"))])

    def make_moviepy_subtitles(self, full_text, total_duration):
        """使用 MoviePy 渲染字幕"""
        clean_text = full_text.replace("\n", " ").strip()
        sentences = [s.strip() for s in re.split(r'[，。！？；\s]+', clean_text) if s.strip()]
        if not sentences: return []

        total_chars = sum(len(s) for s in sentences)
        start_time = 0
        subtitle_clips = []

        for s in sentences:
            dur = (len(s) / total_chars) * total_duration
            if dur <= 0: continue

            # 创建文字剪辑 (根据 Mac 环境调整字体名，如 'Arial-Bold' 或 'PingFang-SC-Regular')
            txt = TextClip(s, fontsize=22, color='white', font='Arial-Bold',
                           method='caption', size=(TARGET_W * 0.8, None))
            txt = txt.set_start(start_time).set_duration(dur).set_position(('center', TARGET_H - 45))
            subtitle_clips.append(txt)
            start_time += dur

        return subtitle_clips

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
                        score = 50 if keyword in title else 10
                        if score >= 10:
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

    def download_with_ytdlp(self, url, save_path):
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': save_path,
            'quiet': True,
            'ignoreerrors': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.extract_info(url, download=True)
                return True
            except:
                return False

    async def make_audio(self, text, path):
        await edge_tts.Communicate(text, TTS_VOICE).save(path)
        return AudioFileClip(path)

    def get_clips(self, folder, target_dur):
        """主脚本切片逻辑：素材池洗牌防止重复"""
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]
        if not v_files: return [ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0)).set_duration(target_dur)], []

        clips, opened, curr, pool = [], [], 0, []
        while curr < target_dur:
            if not pool:
                pool = v_files.copy()
                random.shuffle(pool)
            video_file = pool.pop()
            try:
                v = VideoFileClip(video_file, audio=False)
                opened.append(v)
                d = min(v.duration - 0.5, random.uniform(5, 8))
                if d <= 0: continue
                sub = v.subclip(0.5, 0.5 + d)
                clips.append(self.process_clip(sub))
                curr += d
            except:
                continue
        return clips, opened

    def get_interview_clips_fast(self, folder, target_dur):
        """补充视频逻辑：大段拼接，不剪碎，节省渲染时间"""
        v_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.mp4')]
        if not v_files: return [], []

        clips, opened, curr, pool = [], [], 0, []
        while curr < target_dur:
            if not pool:
                pool = v_files.copy()
                random.shuffle(pool)
            video_file = pool.pop()
            try:
                v = VideoFileClip(video_file, audio=True)
                opened.append(v)
                # 直接取大段，最多取整段，不超过剩余所需时长
                remaining = target_dur - curr
                d = min(v.duration, remaining)
                if d <= 0: break
                sub = v.subclip(0, d)
                clips.append(self.simple_process_clip(sub))
                curr += d
            except:
                continue
        return clips, opened


async def main(json_path, output_root, target_total_duration=1800):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    title = data.get('extreme_titles', ['Video'])[0]
    auto = VideoAutomation(title, json_path, output_root)
    all_parts, resources, full_txt = [], [], ""

    # 1. 制作主脚本段
    for act_id, info in data['video_script'].items():
        act_path = os.path.join(auto.project_dir, act_id)
        os.makedirs(act_path, exist_ok=True)
        urls = await auto.batch_search_bili(info['search_queries'], limit=2)
        await asyncio.gather(
            *[asyncio.to_thread(auto.download_with_ytdlp, u, os.path.join(act_path, f"{i}.mp4")) for i, u in
              enumerate(urls)])

        a_clip = await auto.make_audio(info['content'], os.path.join(act_path, "v.mp3"))
        v_clips, vids = auto.get_clips(act_path, a_clip.duration)
        resources.extend(vids)
        resources.append(a_clip)

        part = concatenate_videoclips(v_clips, method="compose").set_audio(a_clip)
        all_parts.append(part)
        full_txt += info['content'] + " "

    script_dur = sum(p.duration for p in all_parts)
    dynamic_target = target_total_duration + random.randint(-120, 120)

    # 2. 制作大段补充素材（去水印，不切碎）
    if script_dur < dynamic_target:
        needed = dynamic_target - script_dur
        print(f"🎬 脚本时长 {script_dur / 60:.1f}min，开始补充 {needed / 60:.1f}min 大段素材...")
        i_path = os.path.join(auto.project_dir, "extend")
        os.makedirs(i_path, exist_ok=True)
        queries = data.get("protagonist_interview_queries", [])
        if queries:
            i_urls = await auto.batch_search_bili(queries, limit=3)
            await asyncio.gather(
                *[asyncio.to_thread(auto.download_with_ytdlp, u, os.path.join(i_path, f"{i}.mp4")) for i, u in
                  enumerate(i_urls)])
            i_clips, i_vids = auto.get_interview_clips_fast(i_path, needed)
            resources.extend(i_vids)
            if i_clips:
                all_parts.append(concatenate_videoclips(i_clips, method="compose"))

    if all_parts:
        # 3. 合成与字幕渲染
        final_video = concatenate_videoclips(all_parts, method="compose")
        total_dur = final_video.duration

        # 渲染字幕剪辑
        print(f"📝 正在通过 MoviePy 生成字幕 (时长: {total_dur / 60:.1f}min)...")
        subtitle_clips = auto.make_moviepy_subtitles(full_txt, script_dur)

        # 将字幕叠加到视频上
        final_combined = CompositeVideoClip([final_video] + subtitle_clips)

        out_path = os.path.join(auto.project_dir, "FINAL_VERSION.mp4")
        final_combined.write_videofile(out_path, fps=24, codec="h264_videotoolbox", bitrate="3500k", audio_codec="aac")

        for r in resources:
            try:
                r.close()
            except:
                pass


if __name__ == "__main__":
    TARGET_SECONDS = 1800  # 目标 30 分钟

    selected_enum = TaskType.A4
    _, _, t_path = selected_enum.value


    async def run_tasks():
        for subdir in sorted(os.listdir(t_path)):
            p = os.path.join(t_path, subdir)
            if not os.path.isdir(p) or os.path.exists(os.path.join(p, "output")): continue

            script_json_path = os.path.join(p, "script.json")
            if not os.path.exists(script_json_path):
                print(f"⚠️ 跳过 {subdir}: script.json 不存在")
                continue
            
            # 检查 script.json 是否为空文件或空 JSON
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

            print(f"\n🎬 开始任务: {subdir}")
            try:
                await main(script_json_path, os.path.join(p, "output"), TARGET_SECONDS)
                print(f"✅ 任务成功: {subdir}\n")
            except Exception as e:
                print(f"❌ 任务崩溃: {subdir} -> {e}\n")


    asyncio.run(run_tasks())