import os
import numpy as np
import wave


def generate_noise_files(target_folder, duration_sec=60):
    """
    不依赖网络，直接生成 5 段不同的数学噪音文件（白噪音、粉红噪音、布朗噪音）
    """
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    sample_rate = 44100
    num_samples = duration_sec * sample_rate

    noise_types = ["white", "pink", "brown", "low_hum", "static"]

    print(f"🚀 开始自主生成去重音频素材至: {target_folder}")

    for n_type in noise_types:
        file_path = os.path.join(target_folder, f"Noise_{n_type}.wav")
        if os.path.exists(file_path):
            continue

        print(f"Synthesizing: {n_type} noise...")

        # 1. 生成原始随机值
        samples = np.random.uniform(-1, 1, num_samples)

        # 2. 根据类型进行滤波处理
        if n_type == "pink":
            # 粉红噪音：对人耳更友好
            b = [0.049922035, -0.095993537, 0.050293001, -0.005111145]
            samples = np.cumsum(samples)  # 简单积分模拟
        elif n_type == "brown":
            # 布朗噪音：更低沉
            samples = np.cumsum(samples)
        elif n_type == "low_hum":
            # 低频嗡嗡声
            t = np.linspace(0, duration_sec, num_samples)
            samples = 0.5 * np.sin(2 * np.pi * 50 * t) + 0.2 * np.random.normal(0, 1, num_samples)

        # 归一化并转为 16-bit PCM
        samples = samples / np.max(np.abs(samples))
        audio_data = (samples * 32767).astype(np.int16)

        # 写入 WAV 文件
        with wave.open(file_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 2 bytes per sample
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

    print(f"✅ 生成完毕！共 5 段音频。")


if __name__ == "__main__":
    # 需要先安装 numpy: pip install numpy
    BGM_PATH = "/Users/huangyun/Desktop/搬运/BGM"
    generate_noise_files(BGM_PATH)