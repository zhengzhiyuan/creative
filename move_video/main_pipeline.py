import os
import sys
import shutil
# 导入配置和函数
from move_video.download_tt import download_tiktok_videos
from move_video.process_merge_video import batch_process
from move_video.config import TaskType, GLOBAL_SUB_VIDEO_DIR


def clean_directory(directory):
    """
    清空指定目录下的视频文件和 target 文件夹，
    但保留 downloaded_history.txt 进度文件。
    """
    if not os.path.exists(directory):
        return

    print(f"🧹 正在清理目录: {directory}")
    valid_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')

    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)

        # 1. 删除视频文件
        if os.path.isfile(item_path):
            if item.lower().endswith(valid_extensions):
                os.remove(item_path)
                print(f"   - 已删除视频: {item}")

        # 2. 删除旧的 target 结果文件夹
        elif os.path.isdir(item_path) and item == "target":
            shutil.rmtree(item_path)
            print(f"   - 已清理旧的 target 文件夹")


def run_pipeline(task: TaskType):
    # 解构 Enum 里的值
    env_name, target_url, main_video_dir = task.value

    print(f"\n🚀 === 启动任务赛道: {task.name} ({env_name}) ===")

    # 【新增环节】清理老旧视频，确保环境干净
    clean_directory(main_video_dir)

    # 1. 下载阶段
    print(f"Step 1: 开始下载 {env_name} 赛道视频...")
    download_tiktok_videos(target_url, main_video_dir)

    # 2. 处理阶段
    print(f"\nStep 2: 开始 FFmpeg 合成处理...")
    # 确保 batch_process 内部逻辑会在 main_video_dir 下重新创建 target 文件夹
    batch_process(main_video_dir, GLOBAL_SUB_VIDEO_DIR)

    print(f"\n✅ 任务 {task.name} 执行完毕！")
    print("-" * 40)


if __name__ == "__main__":
    run_pipeline(TaskType.A8)
    # 运行所有定义的赛道
    # for task in TaskType:
    #     run_pipeline(task)