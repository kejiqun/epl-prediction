import pandas as pd
import requests
from datetime import datetime
import os
from team_mapping import translate_team_name

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

# API-Football 联赛 ID
LEAGUES = {
    '英超': 39, '西甲': 140, '德甲': 78, '意甲': 135, '法甲': 61
}
# 抓取近三个赛季
SEASONS = [2024, 2025, 2026] 

def fetch_history():
    if not API_FOOTBALL_KEY:
        print("❌ 没有找到 API_FOOTBALL_KEY")
        return
        
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    all_matches = []
    
    for league_name, league_id in LEAGUES.items():
        print(f"⏳ 正在抓取 {league_name} 历史数据...")
        for season in SEASONS:
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&status=FT"
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    for fixture in resp.json().get('response', []):
                        hg = fixture['goals']['home']
                        ag = fixture['goals']['away']
                        if hg is None or ag is None: continue
                        
                        all_matches.append({
                            'date': fixture['fixture']['date'][:10],
                            'home_team': translate_team_name(fixture['teams']['home']['name']),
                            'away_team': translate_team_name(fixture['teams']['away']['name']),
                            'home_goals': hg,
                            'away_goals': ag
                        })
            except Exception as e:
                print(f"⚠️ {league_name} 抓取异常: {e}")
                
    if all_matches:
        df = pd.DataFrame(all_matches).drop_duplicates()
        # 强制覆盖旧的仅仅包含英超的数据库
        df.to_csv('all_leagues_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 历史数据抓取完成，共 {len(df)} 场，已保存至 all_leagues_matches.csv！")
    else:
        print("❌ 未抓取到任何历史数据。")

if __name__ == "__main__":
    fetch_history()
