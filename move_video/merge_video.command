#!/bin/bash

# 1. 获取当前目录路径（即主视频目录）
MAIN_VIDEO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 2. 写死副视频路径
SUB_VIDEO_DIR="/Users/huangyun/Desktop/搬运/副视频/data/关注/3710225754109904/视频"

# 3. 定义代码目录路径
CODE_DIR="/Users/huangyun/git/creative"

echo "------------------------------------------------"
echo "📂 主视频目录: $MAIN_VIDEO_DIR"
echo "📂 代码目录: $CODE_DIR"
echo "------------------------------------------------"

# 4. 切换到代码目录并启动虚拟环境
if [ -d "$CODE_DIR" ]; then
    cd "$CODE_DIR"
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        echo "✅ 已激活虚拟环境: $CODE_DIR/.venv"
    else
        echo "❌ 错误: 在 $CODE_DIR 下未找到 .venv 目录"
        exit 1
    fi
else
    echo "❌ 错误: 找不到代码目录 $CODE_DIR"
    exit 1
fi

# 5. 调用 Python 脚本的 batch_process 方法
# 使用 python3 -c 来导入并执行特定函数，同时传递路径参数
echo "🚀 开始调用合成任务..."

python3 -c "
import sys
import os
# 将代码目录添加到系统路径，确保能导入 move_video 模块
sys.path.append('$CODE_DIR')

try:
    from move_video.process_merge_video import batch_process
    batch_process('$MAIN_VIDEO_DIR', '$SUB_VIDEO_DIR')
except ImportError as e:
    print(f'❌ 导入失败: {e}')
except Exception as e:
    print(f'❌ 运行出错: {e}')
"

echo "------------------------------------------------"
echo "🎉 任务结束，按任意键退出..."
read -n 1