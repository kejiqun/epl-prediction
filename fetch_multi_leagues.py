import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    print("⏳ 正在读取 PinnWire 真实盘口...")
    # 🌟 第一步：强行把 PinnWire 的真实盘口全部放进 all_matches
    if os.path.exists('real_odds.csv'):
        df_odds = pd.read_csv('real_odds.csv')
        for _, r in df_odds.iterrows():
            # 把 PinnWire 的时间格式转成标准 YYYY-MM-DD
            try:
                m_date = pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%dT20:00:00Z') # 假设都是晚上8点
            except:
                m_date = r['比赛时间']
                
            all_matches.append({
                '联赛': '真实盘口赛事', '比赛时间': m_date, '主队': r['主队'], '客队': r['客队'],
                '主胜赔率': r['主胜赔率'], '平局赔率': r['平局赔率'], '客胜赔率': r['客胜赔率'],
                '让球盘口': r.get('让球盘口', 0.0), '主让胜赔率': r.get('主让胜赔率', 0.0), '客受让胜赔率': r.get('客受让胜赔率', 0.0),
                '大小球盘口': r.get('大小球盘口', 2.5), '大球赔率': r.get('大球赔率', 0.0), '小球赔率': r.get('小球赔率', 0.0)
            })
        print(f"✅ 已强行导入 {len(df_odds)} 场 PinnWire 真实比赛。")

    print("⏳ 正在抓取多联赛赛程...")
    # 🌟 第二步：抓取 ESPN 赛程，如果 ESPN 有的比赛，且上面没抓到的，就补进去
    for league_name, config in LEAGUES.items():
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
            
            # 检查这个比赛是不是已经在 PinnWire 里了（通过主客队名字判断）
            existing = next((x for x in all_matches if x['主队'] == h_cn and x['客队'] == a_cn), None)
            
            if not existing:
                # 如果不在，说明 PinnWire 没这场的赔率，补 0
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': h_cn, '客队': a_cn,
                    '主胜赔率': 0, '平局赔率': 0, '客胜赔率': 0,
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df = df.drop_duplicates(subset=['主队', '客队'])
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 赛程与真实盘口融合完毕！包含真实赔率的比赛共 {len(df[df['主胜赔率']>0])} 场")
