import asyncio
import os
import sys
import re
from datetime import datetime

# 假设你刚才修改的两个脚本文件名如下，请确保文件名对应
from download_video import get_bili_video_tasks, download_with_ytdlp
from merge_video import run_video_pipeline

# ================= 静态配置区 =================
# 🎯 已按要求修改为 10~20 分钟范围
TARGET_RANGE = (10, 20)


# =============================================

async def main():
    # 1. 分别输入两个核心搜索词
    min_m, max_m = TARGET_RANGE
    print(f"🎬 --- 视频素材 1080P 高清增强版 ({min_m}-{max_m}min) ---")

    hot_kw = input("🔥 请输入【当前热点】关键词 (1.mp4): ").strip()
    history_kw = input("📜 请输入【黑历史】关键词 (2.mp4...): ").strip()

    if not hot_kw or not history_kw:
        print("❌ 必须输入两个关键词才能确保时长达标，程序退出。")
        return

    # 2. 执行下载逻辑
    print(f"\n--- 阶段 1: 正在检索并下载素材 (目标总时长 {min_m}-{max_m}min) ---")

    # 适配刚才修改过的下载逻辑
    video_tasks = await get_bili_video_tasks(
        hot_kw,
        history_kw,
        target_total_range=TARGET_RANGE
    )

    if not video_tasks:
        print("❌ 未检索到符合条件的视频任务，流程终止。")
        return

    # 传入 target_min_sec 为 600秒 (10分钟)
    downloaded_dir = await download_with_ytdlp(video_tasks, hot_kw, target_min_sec=min_m * 60)

    if not downloaded_dir or not os.path.exists(downloaded_dir):
        print("❌ 下载失败或未发现素材，流程终止。")
        return

    # 3. 配置路径
    # 这里建议把输出路径固定到你刚才 merge_video 脚本里的 target 目录，或者保持当前逻辑
    parent_dir = os.path.dirname(downloaded_dir)
    temp_dir = os.path.join(parent_dir, "temp_work_dir")

    safe_hot_kw = re.sub(r'[\\/:*?"<>|]', '_', hot_kw)
    timestamp = datetime.now().strftime("%H%M%S")
    # 标记为 1080P 以便区分旧视频
    output_filename = f"final_1080P_{safe_hot_kw}_{timestamp}.mp4"
    output_path = os.path.join(parent_dir, output_filename)

    # 4. 执行合并逻辑
    print(f"\n--- 阶段 2: 正在进行 1080P 视频去重与高清合成 ---")
    try:
        # 调用已经升级为 1080P 逻辑的 run_video_pipeline
        run_video_pipeline(downloaded_dir, temp_dir, output_path)

        print("\n" + "=" * 50)
        print(f"✨ 全流程执行成功！")
        print(f"📂 原始素材库: {downloaded_dir}")
        print(f"🎬 最终高清成品: {output_path}")
        print(f"📏 时长范围: {min_m}-{max_m}min (1080P/6000k)")
        print("=" * 50)

    except Exception as e:
        print(f"❌ 合并阶段发生严重错误: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户手动终止程序。")
        sys.exit()