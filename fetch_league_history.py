import pandas as pd
import requests
from datetime import datetime
from team_mapping import translate_team_name
import os

# API-Football 联赛 ID
LEAGUES = {
    '英超': 39, '西甲': 140, '德甲': 78, '意甲': 135, '法甲': 61
}
# 抓取近几个赛季 (比如23,24,25)
SEASONS = [2023, 2024, 2025] 

def fetch_history():
    all_matches = []
    if not os.environ.get("API_FOOTBALL_KEY"): return
    headers = {"x-apisports-key": os.environ.get("API_FOOTBALL_KEY")}
    
    for league_name, league_id in LEAGUES.items():
        print(f"⏳ 正在抓取 {league_name} 历史数据...")
        for season in SEASONS:
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&status=FT"
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    for fixture in resp.json().get('response', []):
                        all_matches.append({
                            'date': fixture['fixture']['date'][:10],
                            'home_team': translate_team_name(fixture['teams']['home']['name']),
                            'away_team': translate_team_name(fixture['teams']['away']['name']),
                            'home_goals': fixture['goals']['home'],
                            'away_goals': fixture['goals']['away']
                        })
            except Exception as e:
                print(f"⚠️ 抓取异常: {e}")
                
    df = pd.DataFrame(all_matches).drop_duplicates()
    df.to_csv('all_leagues_matches.csv', index=False, encoding='utf-8-sig')
    print(f"✅ 历史数据抓取完成，共 {len(df)} 场，已保存！")

if __name__ == "__main__":
    fetch_history()
