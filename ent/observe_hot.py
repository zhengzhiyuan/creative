import os
import requests
import pandas as pd
from datetime import datetime

# --- ⚙️ 配置区域 ---
# 严格遵守命名习惯，严禁使用 cleansed_P
OUTPUT_DIR = "/Users/huangyun/Desktop/搬运/ENT/trend_reports"


# ------------------

def fetch_weibo_hot():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print(f"[{datetime.now()}] 🚀 启动微博娱乐热点雷达 (国内瓜源)...")

    url = "https://weibo.com/ajax/side/hotSearch"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://s.weibo.com/'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            hot_list = data.get('data', {}).get('realtime', [])

            items = []
            for item in hot_list:
                # 过滤出娱乐类目（通常带有 '剧集', '综艺', '明星' 等标签，或者直接全量抓取）
                # label_name 有时代表类别，比如 '爆', '沸', '热'
                title = item.get('word', '')
                category = item.get('category', '')
                num = item.get('num', 0)  # 热度值

                items.append({'Search_Term': title, 'Category': category, 'Hot_Value': num})

            if items:
                df = pd.DataFrame(items)
                # 按照热度排序
                df = df.sort_values(by='Hot_Value', ascending=False)

                timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                filename = f"Weibo_Hot_{timestamp}.csv"
                save_path = os.path.join(OUTPUT_DIR, filename)

                df.to_csv(save_path, index=False)
                print(f"✅ 微博热搜已捕获！当前第一名：{items[0]['Search_Term']}")
                print(df.head(10))  # 打印前 10 名
            else:
                print("⚠️ 未能抓取到微博热搜数据。")
        else:
            print(f"❌ 访问微博失败，状态码: {response.status_code}")

    except Exception as e:
        print(f"❌ 微博监控异常: {e}")


if __name__ == "__main__":
    fetch_weibo_hot()