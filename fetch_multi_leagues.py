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
    real_odds = {}
    if os.path.exists('real_odds.csv'):
        df_odds = pd.read_csv('real_odds.csv')
        # 将 PinnWire 的时间统一转为纯日期格式，并建立 (日期, 主队, 客队) 的索引
        for _, r in df_odds.iterrows():
            try:
                # 统一转成 YYYY-MM-DD 格式
                m_date = pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d')
                real_odds[(m_date, r['主队'], r['客队'])] = (
                    r['主胜赔率'], r['平局赔率'], r['客胜赔率'],
                    r.get('让球盘口', 0.0), r.get('主让胜赔率', 0.0), r.get('客受让胜赔率', 0.0),
                    r.get('大小球盘口', 2.5), r.get('大球赔率', 0.0), r.get('小球赔率', 0.0)
                )
            except Exception as e:
                pass
        print(f"✅ PinnWire 赔率库加载完毕，包含 {len(real_odds)} 场比赛。")

    print("⏳ 正在抓取多联赛赛程...")
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
                                    upcoming.append({
                                        'league': league_name, 
                                        'datetime': event['date'], 
                                        'home': translate_team_name(h_t), 
                                        'away': translate_team_name(a_t)
                                    })
            except: continue
            
        for m in upcoming:
            h_cn, a_cn = m['home'], m['away']
            # ESPN 的时间通常带 Z（UTC），我们需要转成北京时间（UTC+8）再取日期
            try:
                espn_utc_time = pd.to_datetime(m['datetime'])
                espn_cn_time = espn_utc_time.tz_convert('Asia/Shanghai')
                espn_date_str = espn_cn_time.strftime('%Y-%m-%d')
            except:
                espn_date_str = m['datetime'][:10]

            # 严格按 日期 + 主队 + 客队 去 PinnWire 库里找
            odds_data = real_odds.get((espn_date_str, h_cn, a_cn))
            
            if odds_data:
                print(f"🎯 匹配成功：【{espn_date_str}】{h_cn} vs {a_cn} 拿到真实赔率！")
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': h_cn, '客队': a_cn,
                    '主胜赔率': odds_data[0], '平局赔率': odds_data[1], '客胜赔率': odds_data[2],
                    '让球盘口': odds_data[3], '主让胜赔率': odds_data[4], '客受让胜赔率': odds_data[5],
                    '大小球盘口': odds_data[6], '大球赔率': odds_data[7], '小球赔率': odds_data[8]
                })
            else:
                # 匹配不到，老老实实给 0
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
        
        success_matches = len(df[df['主胜赔率'] > 0])
        print(f"✅ 赛程与盘口融合完毕！总比赛: {len(df)} 场，其中成功匹配到真实赔率的: {success_matches} 场。")
