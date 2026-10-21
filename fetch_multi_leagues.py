import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_schedule():
    all_matches = []
    today = datetime.now()
    
    print("⏳ 正在抓取多联赛赛程...")
    for league_name, config in LEAGUES.items():
        for i in range(7): 
            date_str = (today + timedelta(days=i)).strftime('%Y%m%d')
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={date_str}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    for event in resp.json().get('events', []):
                        if event['status']['type']['state'] == 'pre':
                            comps = event.get('competitions', [])
                            if comps:
                                competitors = comps[0].get('competitors', [])
                                h_t = next((c['team']['name'] for c in competitors if c['homeAway'] == 'home'), None)
                                a_t = next((c['team']['name'] for c in competitors if c['homeAway'] == 'away'), None)
                                if h_t and a_t:
                                    all_matches.append({
                                        '联赛': league_name, '比赛时间': event['date'], 
                                        '主队': translate_team_name(h_t), '客队': translate_team_name(a_t)
                                    })
            except: continue
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df = df.drop_duplicates(subset=['比赛时间', '主队', '客队'])
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 赛程抓取完毕！共 {len(df)} 场比赛。")
