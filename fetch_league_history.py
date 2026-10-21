import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_history():
    print("⏳ 启动粮仓计划：按月抓取多联赛历史赛果...")
    all_matches = []
    
    # 🌟 优化点：只抓最近12个月的数据，足够模型认人了，而且速度快
    today = datetime.now()
    months_to_fetch = []
    for i in range(12):
        # 计算往前推 i 个月的年份和月份
        year = today.year if today.month - i > 0 else today.year - 1
        month = today.month - i if today.month - i > 0 else today.month - i + 12
        months_to_fetch.append((year, month))
    
    for league_name, config in LEAGUES.items():
        print(f"正在抓取 {league_name} 的历史数据...")
        for year, month in months_to_fetch:
            # 计算该月的第一天和最后一天
            start_date = f"{year}{month:02d}01"
            if month == 12:
                end_date = f"{year}1231"
            else:
                end_date = f"{year}{month+1:02d}01"
            
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={start_date}-{end_date}"
            try:
                # 加上 timeout=10，如果超过10秒没反应就跳过，绝不死等
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for event in data.get('events', []):
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
                                    
                                    all_matches.append({
                                        'date': match_date,
                                        'league': league_name,
                                        'home_team': h_name,
                                        'away_team': a_name,
                                        'home_goals': h_score,
                                        'away_goals': a_score
                                    })
            except Exception as e:
                # 失败就跳过，绝不卡死
                pass
            time.sleep(0.5) # 稍微停顿，防止被ESPN当机器人
            
    if all_matches:
        df = pd.DataFrame(all_matches)
        df = df.drop_duplicates(subset=['date', 'home_team', 'away_team'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        df.to_csv('all_leagues_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 粮仓建设完毕！共抓取 {len(df)} 场比赛。")
    else:
        print("❌ 未能抓取到任何历史数据。")

if __name__ == "__main__":
    fetch_history()
