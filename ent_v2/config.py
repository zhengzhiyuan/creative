from enum import Enum

class TaskType(Enum):
    # 格式：任务名 = (环境标识, ytb channel URL, 下载/处理路径)
    A1 = (
        "A1",
        "https://www.youtube.com/@%E5%8F%AF%E5%A8%B1%E5%8F%AF%E4%B9%90/videos",
        "/Users/huangyun/Desktop/搬运/A1_娱乐",
    )

    A4 = (
        "A4",
        "https://www.youtube.com/@IronCurtainArchives/videos",
        "/Users/huangyun/Desktop/搬运/A4_娱乐",
    )


