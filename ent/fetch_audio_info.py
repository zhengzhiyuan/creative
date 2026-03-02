import whisper
import os
import sys


def transcribe_video_content(video_path, model_size="small"):
    # 1. 再次确认文件是否存在
    if not os.path.exists(video_path):
        print(f"❌ 找不到文件: {os.path.abspath(video_path)}")
        return

    # 按照你的习惯命名，避开 cleansed_P
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    output_txt = f"script_{base_name}.txt"

    print(f"--- 🚀 开始处理视频: {video_path} ---")

    try:
        # 2. 加载模型 (针对 Mac 优化)
        print(f"正在加载 Whisper [{model_size}] 模型...")
        model = whisper.load_model(model_size)

        # 3. 语音识别 (Whisper 直接读视频通常比提取音频更稳)
        print("语音识别中，可能需要几分钟（视视频长度而定）...")
        result = model.transcribe(
            video_path,
            fp16=False,
            language="Chinese",
            initial_prompt="这是一段关于娱乐八卦、冯小刚和范冰冰的视频。"
        )

        # 4. 保存文本
        with open(output_txt, "w", encoding="utf-8") as f:
            f.write(result["text"])

        print(f"--- ✅ 成功！原始旁白已存至: {output_txt} ---")

    except Exception as e:
        print(f"❌ 运行出错: {e}")


if __name__ == "__main__":
    # 请确保该文件在当前目录下，或者填写绝对路径
    # 建议你把视频改名为这个，或者把这里改成你实际的文件名
    target_file = "/Users/huangyun/Desktop/搬运/ENT/my_videos/a.mp4"

    transcribe_video_content(target_file, model_size="small")