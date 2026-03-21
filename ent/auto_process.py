import asyncio
import os
import sys
import re
from datetime import datetime

# 导入你原来的逻辑
from download_video import get_bili_video_tasks, download_with_ytdlp
from merge_video import run_video_pipeline


async def main():
    # 1. 分别输入两个核心搜索词，以适配新的时长与内容比例逻辑
    print("🎬 --- 视频素材自动化下载合并工具 ---")
    hot_kw = input("🔥 请输入【当前热点】关键词 (用于生成 1.mp4): ").strip()
    history_kw = input("📜 请输入【黑历史】关键词 (用于生成 2.mp4, 3.mp4): ").strip()

    if not hot_kw or not history_kw:
        print("❌ 必须输入两个关键词才能确保时长达标，程序退出。")
        return

    # 2. 执行下载逻辑
    print("\n--- 阶段 1: 正在检索并下载素材 (目标总时长 15-25min) ---")

    # 适配优化后的 get_bili_video_tasks
    video_tasks = await get_bili_video_tasks(hot_kw, history_kw)

    if not video_tasks:
        print("❌ 未检索到符合条件的视频任务，流程终止。")
        return

    # 获取下载后的实际文件夹路径
    # 使用 hot_kw 作为文件夹命名标识
    downloaded_dir = await download_with_ytdlp(video_tasks, hot_kw)

    if not downloaded_dir or not os.path.exists(downloaded_dir):
        print("❌ 下载失败或未发现素材，流程终止。")
        return

    # 3. 配置合并路径
    parent_dir = os.path.dirname(downloaded_dir)
    # 创建临时的中间处理目录
    temp_dir = os.path.join(parent_dir, "temp_work_dir")

    # 清理文件名中的非法字符，防止 ffmpeg 报错
    safe_hot_kw = re.sub(r'[\\/:*?"<>|]', '_', hot_kw)
    timestamp = datetime.now().strftime("%H%M%S")
    output_filename = f"final_{safe_hot_kw}_{timestamp}.mp4"
    output_path = os.path.join(parent_dir, output_filename)

    # 4. 执行合并逻辑
    print("\n--- 阶段 2: 正在进行视频去重与合并 (混剪模式) ---")
    try:
        # 调用 merge_video.py 中的函数
        # 注意：此函数内部会自动识别文件夹内的 1.mp4, 2.mp4, 3.mp4 并进行拼接
        run_video_pipeline(downloaded_dir, temp_dir, output_path)

        print("\n" + "=" * 50)
        print(f"✨ 全流程执行成功！")
        print(f"📂 原始素材库: {downloaded_dir}")
        print(f"🎬 最终混剪成品: {output_path}")
        print(f"📏 总时长已按 15-25min 逻辑进行优化")
        print("=" * 50)

    except Exception as e:
        print(f"❌ 合并阶段发生严重错误: {e}")


if __name__ == "__main__":
    # 确保环境已安装 ffmpeg 且在 PATH 中
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户手动终止程序。")
        sys.exit()