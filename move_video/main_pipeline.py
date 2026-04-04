import os
import sys
import shutil
# 导入配置和函数
from move_video.download_tt import download_tiktok_videos
from move_video.process_merge_video import batch_process
# 注意：这里需要去 config.py 增加 GLOBAL_BGM_DIR 的定义
from move_video.config import TaskType, GLOBAL_SUB_VIDEO_DIR, GLOBAL_BGM_DIR


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
    env_name, target_url, main_video_dir, sub_video_dir = task.value

    print(f"\n🚀 === 启动任务赛道: {task.name} ({env_name}) ===")

    # 1. 清理老旧视频，确保环境干净
    clean_directory(main_video_dir)

    # 2. 下载阶段
    print(f"Step 1: 开始下载 {env_name} 赛道视频...")
    download_tiktok_videos(target_url, main_video_dir)

    # 3. 处理阶段 (核心修改点)
    print(f"\nStep 2: 开始 FFmpeg 终极去重合成处理...")

    # 【修改点】现在传递 3 个目录：主视频、副视频、BGM目录
    # 确保你的 batch_process 函数接收这三个参数
    batch_process(main_video_dir, sub_video_dir, GLOBAL_BGM_DIR)

    print(f"\n✅ 任务 {task.name} 执行完毕！")
    print("-" * 40)


if __name__ == "__main__":
    # 建议在运行前手动检查一遍 BGM 目录里是否有文件
    if not os.path.exists(GLOBAL_BGM_DIR) or not os.listdir(GLOBAL_BGM_DIR):
        print(f"⚠️ 警告: BGM 目录 {GLOBAL_BGM_DIR} 为空，请先运行 bgm_library.py 生成噪音文件！")
        sys.exit(1)

    run_pipeline(TaskType.A2)