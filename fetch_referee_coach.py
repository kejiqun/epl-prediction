import pandas as pd
import requests
import os
from datetime import datetime, timedelta
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_referee_and_coach():
    print("⏳ 启动侦察兵：开始抓取真实裁判与教练数据...")
    
    # 1. 抓取裁判数据 (通过 ESPN 接口提取)
    referee_records = []
    today = datetime.now()
    
    for league_name, config in LEAGUES.items():
        for i in range(7): # 抓取未来一周的裁判安排
            date_str = (today + timedelta(days=i)).strftime('%Y%m%d')
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={date_str}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for event in data.get('events', []):
                        competitions = event.get('competitions', [])
                        if competitions:
                            # 寻找裁判信息
                            officials = competitions[0].get('officials', [])
                            ref_name = "未公布"
                            for off in officials:
                                if off.get('position', {}).get('displayName') == 'Referee':
                                    ref_name = off.get('displayName')
                                    break
                            
                            competitors = competitions[0].get('competitors', [])
                            home_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'home'), None)
                            away_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'away'), None)
                            
                            if home_team and away_team:
                                referee_records.append({
                                    'date': event['date'][:10],
                                    'league': league_name,
                                    'home_team': translate_team_name(home_team),
                                    'away_team': translate_team_name(away_team),
                                    'referee': ref_name,
                                    # 因为没有免费的裁判历史统计API，这里用行业均值作为基准，后续可通过实战复盘更新
                                    'avg_yellow_cards': 4.2, 
                                    'avg_penalties': 0.25 
                                })
            except: continue
            
    if referee_records:
        df_ref = pd.DataFrame(referee_records).drop_duplicates(subset=['date', 'home_team', 'away_team'])
        df_ref.to_csv('referee_stats.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 裁判数据已记录，共 {len(df_ref)} 场。")
    else:
        print("⚠️ 暂未抓取到裁判数据。")

    # 2. 提炼教练风格数据 (通过真实历史战绩计算)
    print("⏳ 正在计算各队教练的攻防风格...")
    if os.path.exists('epl_matches_10y.csv'):
        df_hist = pd.read_csv('epl_matches_10y.csv')
        df_hist['date'] = pd.to_datetime(df_hist['date'])
        df_hist = df_hist.sort_values('date').reset_index(drop=True)
        df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
        df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)
        
        coach_stats = {}
        for idx, row in df_hist.tail(500).iterrows(): # 只看最近500场，了解近期风格
            home, away = row['home_team_cn'], row['away_team_cn']
            for t in [home, away]:
                if t not in coach_stats:
                    coach_stats[t] = {'scored': [], 'conceded': []}
            coach_stats[home]['scored'].append(row['home_goals'])
            coach_stats[home]['conceded'].append(row['away_goals'])
            coach_stats[away]['scored'].append(row['away_goals'])
            coach_stats[away]['conceded'].append(row['home_goals'])
            
        coach_records = []
        for team, stats in coach_stats.items():
            if len(stats['scored']) >= 3: # 至少有3场数据
                avg_scored = sum(stats['scored'][-5:]) / len(stats['scored'][-5:])
                avg_conceded = sum(stats['conceded'][-5:]) / len(stats['conceded'][-5:])
                
                # 风格判定
                if avg_scored > 1.8:
                    style = "激进进攻"
                elif avg_conceded < 0.8:
                    style = "保守防守"
                else:
                    style = "攻守平衡"
                    
                coach_records.append({
                    'team': team,
                    'coach_style': style,
                    'avg_goals_scored': round(avg_scored, 2),
                    'avg_goals_conceded': round(avg_conceded, 2)
                })
                
        pd.DataFrame(coach_records).to_csv('coach_stats.csv', index=False, encoding='utf-8-sig')
        print("✅ 教练风格数据已计算并保存。")
    else:
        print("⚠️ 找不到历史数据，跳过教练分析。")

if __name__ == "__main__":
    fetch_referee_and_coach()
