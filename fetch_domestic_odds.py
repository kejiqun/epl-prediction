import requests
import pandas as pd
import re
import os
from team_mapping import translate_team_name

def fetch_163_odds():
    print("⏳ 尝试自动抓取国内彩票（网易彩票）...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        url = "https://caipiao.163.com/award/jczq.html"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # 简单解析网易的 DOM (因结构可能随时变化，使用简单容错正则)
            pattern = r'<tr[^>]*>.*?<td[^>]*>(\d{4}-\d{2}-\d{2}).*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>([\d\.]+)</td>.*?<td[^>]*>([\d\.]+)</td>.*?<td[^>]*>([\d\.]+)</td>'
            matches = re.findall(pattern, resp.text, re.DOTALL)
            all_matches = []
            for m in matches:
                all_matches.append({
                    '比赛日期': m[0], '主队': translate_team_name(m[1].strip()), '客队': translate_team_name(m[2].strip()),
                    '主胜赔率': float(m[3]), '平局赔率': float(m[4]), '客胜赔率': float(m[5]),
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                })
            
            if all_matches:
                df = pd.DataFrame(all_matches)
                df.to_csv('manual_odds.csv', index=False, encoding='utf-8-sig') # 直接覆盖手动表
                print(f"✅ 成功自动抓取 {len(df)} 场国彩并写入 manual_odds.csv！")
            else:
                print("⚠️ 网页反爬导致解析失败，自动降级使用手填数据。")
        else:
            print("⚠️ 网易彩票接口不可用，自动降级使用手填数据。")
    except Exception as e:
        print(f"⚠️ 抓取失败: {e}，自动降级使用手填数据。")

if __name__ == "__main__":
    fetch_163_odds()
