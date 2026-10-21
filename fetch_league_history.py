import requests
import pandas as pd
import time
from datetime import datetime
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_history():
    print("⏳ 启动粮仓计划：开始抓取多联赛历史赛果...")
    all_matches = []
    
    # 我们抓取最近两个赛季的数据（2022-2023, 2023-2024），足够模型认清所有球队了
    seasons = ["2022", "2023"]
    
    for league_name, config in LEAGUES.items():
        print(f"正在抓取 {league_name} 的历史数据...")
        for season in seasons:
            # ESPN 的赛程接口支持传入年份
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={season}0101-{season}1231"
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    for event in data.get('events', []):
                        # 我们只要已经踢完的比赛 (post)
                        if event['status']['type']['state'] == 'post':
                            competitions = event.get('competitions', [])
                            if competitions:
                                competitors = competitions[0].get('competitors', [])
                                home = next((c for c in competitors if c['homeAway'] == 'home'), None)
                                away = next((c for c in competitors if c['homeAway'] == 'away'), None)
                                
                                if home and away:
                                    h_name = translate_team_name(home['team']['name'])
                                    a_name = translate_team_name(away['team']['name'])
                                    h_score = int(home.get('score', 0))
                                    a_score = int(away.get('score', 0))
                                    match_date = event['date'][:10]
                                    
                                    # 我们还需要球队的射门等基础数据作为特征（如果ESPN提供了的话）
                                    all_matches.append({
                                        'date': match_date,
                                        'league': league_name,
                                        'home_team': h_name,
                                        'away_team': a_name,
                                        'home_goals': h_score,
                                        'away_goals': a_score
                                    })
            except Exception as e:
                print(f"⚠️ {league_name} {season} 抓取失败: {e}")
            time.sleep(1) # 稍微等一秒，防止被ESPN封IP
            
    if all_matches:
        df = pd.DataFrame(all_matches)
        # 去重
        df = df.drop_duplicates(subset=['date', 'home_team', 'away_team'])
        # 按日期排序
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 保存为全新的全球历史数据集
        df.to_csv('all_leagues_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 粮仓建设完毕！共抓取 {len(df)} 场比赛，已保存为 all_leagues_matches.csv")
    else:
        print("❌ 未能抓取到任何历史数据。")

if __name__ == "__main__":
    fetch_history()
