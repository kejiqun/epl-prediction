import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    # 🌟 读取抓到的真实赔率，并把日期格式统一为 YYYY-MM-DD
    real_odds = {}
    if os.path.exists('real_odds.csv'):
        df_odds = pd.read_csv('real_odds.csv')
        for _, r in df_odds.iterrows():
            try:
                date_only = pd.to_datetime(r['比赛时间']).date()
                real_odds[(date_only, r['主队'], r['客队'])] = (r['主胜赔率'], r['平局赔率'], r['客胜赔率'], r['大小球盘口'])
            except: pass

    for league_name, config in LEAGUES.items():
        print(f"⏳ 正在抓取 {league_name} 赛程...")
        upcoming = []
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
                                    upcoming.append({'league': league_name, 'datetime': event['date'], 'home': translate_team_name(h_t), 'away': translate_team_name(a_t)})
            except: continue
            
        for m in upcoming:
            h_cn, a_cn = m['home'], m['away']
            match_date = pd.to_datetime(m['datetime']).date()
            
            # 用 日期 + 主队 + 客队 去匹配真实赔率
            if (match_date, h_cn, a_cn) in real_odds:
                odds = real_odds[(match_date, h_cn, a_cn)]
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': h_cn, '客队': a_cn,
                    '主胜赔率': odds[0], '平局赔率': odds[1], '客胜赔率': odds[2],
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': odds[3], '大球赔率': 0.0, '小球赔率': 0.0
                })
            else:
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': h_cn, '客队': a_cn,
                    '主胜赔率': 0, '平局赔率': 0, '客胜赔率': 0,
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df = df.drop_duplicates(subset=['比赛时间', '主队', '客队'])
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 赛程与真实盘口融合完毕！")
