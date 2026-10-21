import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    # 🌟 核心修改：抛弃日期，直接以 (主队, 客队) 为键构建赔率字典！
    real_odds = {}
    if os.path.exists('real_odds.csv'):
        df_odds = pd.read_csv('real_odds.csv')
        for _, r in df_odds.iterrows():
            # 将所有的赔率列全部塞进去
            real_odds[(r['主队'], r['客队'])] = (
                r['主胜赔率'], r['平局赔率'], r['客胜赔率'],
                r['让球盘口'], r['主让胜赔率'], r['客受让胜赔率'],
                r['大小球盘口'], r['大球赔率'], r['小球赔率']
            )

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
            
            # 🌟 核心修改：只要队名在字典里，直接赋值！
            if (h_cn, a_cn) in real_odds:
                odds = real_odds[(h_cn, a_cn)]
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': h_cn, '客队': a_cn,
                    '主胜赔率': odds[0], '平局赔率': odds[1], '客胜赔率': odds[2],
                    '让球盘口': odds[3], '主让胜赔率': odds[4], '客受让胜赔率': odds[5],
                    '大小球盘口': odds[6], '大球赔率': odds[7], '小球赔率': odds[8]
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
