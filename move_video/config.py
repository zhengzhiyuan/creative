from enum import Enum

class TaskType(Enum):
    # 格式：任务名 = (环境标识, TikTok URL, 下载/处理路径)
    A1 = (
        "A1",
        "https://www.tiktok.com/@smoorfy_julia",
        "/Users/huangyun/Desktop/搬运/A1"
    )
    A2 = (
        "A2",
        "https://www.tiktok.com/@willstar.media",
        "/Users/huangyun/Desktop/搬运/A2"
    )

# 副视频目录是全局统一的，保持不变
GLOBAL_SUB_VIDEO_DIR = "/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"