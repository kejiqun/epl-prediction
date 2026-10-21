import requests
import pandas as pd
import json
import re
import os
from team_mapping import translate_team_name

def fetch_understat_xg():
    print("⏳ 启动 xG 雷达：开始抓取全球真实预期进球数据...")
    
    # Understat 的五大联赛代码
    leagues = {
        'EPL': '英超',
        'La_liga': '西甲',
        'Bundesliga': '德甲',
        'Serie_A': '意甲',
        'Ligue_1': '法甲'
    }
    
    all_data = []
    
    for league_code, league_name in leagues.items():
        # 抓取该联赛的赛程和 xG 数据
        url = f"https://understat.com/league/{league_code}/2023" # 抓2023-2024赛季
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                # Understat 把数据藏在网页源码的 JSON 字符串里，我们用正则提取出来
                match = re.search(r"var datesData\s*=\s*JSON.parse\('(.*?)'\)", resp.text)
                if match:
                    json_str = match.group(1).encode().decode('unicode_escape')
                    data = json.loads(json_str)
                    
                    for match_info in data:
                        h_team = translate_team_name(match_info['h']['title'])
                        a_team = translate_team_name(match_info['a']['title'])
                        
                        h_xg = float(match_info['xG']['h'])
                        a_xg = float(match_info['xG']['a'])
                        h_goals = int(match_info['goals']['h'])
                        a_goals = int(match_info['goals']['a'])
                        match_date = match_info['datetime'][:10]
                        
                        all_data.append({
                            'date': match_date,
                            'league': league_name,
                            'home_team': h_team,
                            'away_team': a_team,
                            'home_goals': h_goals,
                            'away_goals': a_goals,
                            'home_xg': h_xg,
                            'away_xg': a_xg
                        })
            print(f"✅ {league_name} xG 数据抓取完成！")
        except Exception as e:
            print(f"❌ {league_name} 抓取失败: {e}")
            
    if all_data:
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df.to_csv('xg_data.csv', index=False, encoding='utf-8-sig')
        print(f"🎉 大功告成！共抓取 {len(df)} 场比赛的真实 xG 数据，已保存为 xg_data.csv")
    else:
        print("⚠️ 没抓取到数据，可能是网络问题或反爬限制。")

if __name__ == "__main__":
    fetch_understat_xg()
