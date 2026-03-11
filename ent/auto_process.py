import asyncio
import os
import sys
from datetime import datetime

# 导入你原来的逻辑
from download_video import get_bili_video_tasks, download_with_ytdlp
from merge_video import run_video_pipeline


async def main():
    # 1. 输入搜索词
    raw_kw = input("🔍 请输入搜索关键字 (将自动下载并合并): ").strip()
    if not raw_kw:
        print("未输入关键词，程序退出。")
        return

    # 2. 执行下载逻辑
    print("\n--- 阶段 1: 正在检索并下载素材 ---")
    video_tasks = await get_bili_video_tasks(raw_kw)

    # 【关键修复】获取下载后的实际文件夹路径，增加 await 关键字
    downloaded_dir = await download_with_ytdlp(video_tasks, raw_kw)

    if not downloaded_dir or not os.path.exists(downloaded_dir):
        print("❌ 下载失败或未发现素材，流程终止。")
        return

    # 3. 配置合并路径
    # 我们在下载目录同级创建一个 output 文件夹存放结果
    parent_dir = os.path.dirname(downloaded_dir)
    temp_dir = os.path.join(parent_dir, "temp_work_dir")

    # 生成最终文件名：关键词_时间.mp4
    timestamp = datetime.now().strftime("%H%M%S")
    output_filename = f"merged_{raw_kw}_{timestamp}.mp4"
    output_path = os.path.join(parent_dir, output_filename)

    # 4. 执行合并逻辑
    print("\n--- 阶段 2: 正在进行视频去重与合并 ---")
    try:
        # 调用 merge_video.py 中的函数
        run_video_pipeline(downloaded_dir, temp_dir, output_path)

        print("\n" + "=" * 30)
        print(f"✨ 全流程完成！")
        print(f"📂 素材目录: {downloaded_dir}")
        print(f"🎬 最终成品: {output_path}")
        print("=" * 30)

    except Exception as e:
        print(f"❌ 合并阶段发生错误: {e}")


if __name__ == "__main__":
    # 确保 ffmpeg 环境可用
    asyncio.run(main())