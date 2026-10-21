import requests
import pandas as pd
import re
import os
from datetime import datetime

def fetch_500_odds():
    print("⏳ 启动国内数据源：正在尝试从 500彩票网/网易彩票 抓取真实盘口...")
    
    # 强力伪装头，降低被封概率
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    all_matches = []
    
    # 方案 A：尝试 500 彩票网
    try:
        url_500 = "https://trade.500.com/jczq/"
        resp = requests.get(url_500, headers=headers, timeout=10)
        resp.encoding = 'gb2312'
        if resp.status_code == 200 and 'jczq' in resp.text:
            tables = pd.read_html(resp.text)
            if tables:
                df_raw = tables[0]
                for idx, row in df_raw.iterrows():
                    try:
                        match_time_str = str(row.get('比赛时间', ''))
                        if not match_time_str or '未' in match_time_str: continue
                        h_team = str(row.get('主队', '')).strip()
                        a_team = str(row.get('客队', '')).strip()
                        if h_team and a_team and len(h_team) < 20:
                            all_matches.append({
                                '比赛时间': match_time_str, '主队': h_team, '客队': a_team,
                                '主胜赔率': float(row.get('胜', 0)), '平局赔率': float(row.get('平', 0)), '客胜赔率': float(row.get('负', 0)),
                            })
                    except: continue
            print(f"✅ 500彩票网 抓取完成，获取 {len(all_matches)} 场。")
    except Exception as e:
        print(f"⚠️ 500彩票网 抓取失败，尝试备用源: {e}")

    # 方案 B：如果 500 挂了，尝试网易彩票公开接口
    if not all_matches:
        try:
            url_163 = "https://caipiao.163.com/award/jczq.html"
            resp = requests.get(url_163, headers=headers, timeout=10)
            if resp.status_code == 200:
                # 简单解析网易的 DOM 结构（如果存在）
                # 这里用正则粗略提取，适配网易的简单结构
                pattern = r'<tr[^>]*>.*?<td[^>]*>(\d{4}-\d{2}-\d{2}).*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>([\d\.]+)</td>.*?<td[^>]*>([\d\.]+)</td>.*?<td[^>]*>([\d\.]+)</td>'
                matches = re.findall(pattern, resp.text, re.DOTALL)
                for m in matches:
                    all_matches.append({
                        '比赛时间': m[0], '主队': m[1].strip(), '客队': m[2].strip(),
                        '主胜赔率': float(m[3]), '平局赔率': float(m[4]), '客胜赔率': float(m[5])
                    })
                print(f"✅ 网易彩票 抓取完成，获取 {len(all_matches)} 场。")
        except Exception as e:
            print(f"⚠️ 网易彩票 也挂了: {e}")

    if all_matches:
        df = pd.DataFrame(all_matches).drop_duplicates(subset=['比赛时间', '主队', '客队'])
        # 翻译队名（复用你的 team_mapping）
        from team_mapping import translate_team_name
        df['主队'] = df['主队'].apply(translate_team_name)
        df['客队'] = df['客队'].apply(translate_team_name)
        
        df.to_csv('domestic_odds.csv', index=False, encoding='utf-8-sig')
        print("✅ 国内盘口数据已成功写入 domestic_odds.csv")
    else:
        print("❌ 所有国内源均被反爬拦截，本轮回测将使用纯技术倾向。")

if __name__ == "__main__":
    fetch_500_odds()
