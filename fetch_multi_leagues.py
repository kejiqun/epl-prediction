import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    for league_name, config in LEAGUES.items():
        print(f"⏳ 正在抓取 {league_name} 赛程与盘口...")
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
            
        odds_dict = {}
        try:
            resp = requests.get("https://api.the-odds-api.com/v4/sports/" + config['odds_api_code'] + "/odds", 
                                params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h,spreads,totals', 'oddsFormat': 'decimal'}, timeout=20)
            if resp.status_code == 200:
                for match in resp.json():
                    h_cn, a_cn = translate_team_name(match['home_team']), translate_team_name(match['away_team'])
                    
                    h_o, d_o, a_o = 0, 0, 0
                    handicap, hc_h_odd, hc_a_odd = -999.0, 0.0, 0.0  # 默认缺失为 -999
                    total_line, over_odd, under_odd = -999.0, 0.0, 0.0
                    
                    if match.get('bookmakers'):
                        for market in match['bookmakers'][0]['markets']:
                            if market['key'] == 'h2h':
                                for o in market['outcomes']:
                                    if o['name'] == match['home_team']: h_o = o['price']
                                    elif o['name'] == match['away_team']: a_o = o['price']
                                    elif o['name'] == 'Draw': d_o = o['price']
                            elif market['key'] == 'spreads':
                                for o in market['outcomes']:
                                    # 强校验：只有在有数据时才赋值
                                    if o['name'] == match['home_team'] and 'point' in o: 
                                        handicap = o['point']
                                        hc_h_odd = o['price']
                                    elif o['name'] == match['away_team'] and 'point' in o:
                                        hc_a_odd = o['price']
                            elif market['key'] == 'totals':
                                for o in market['outcomes']:
                                    if o['name'] == 'Over' and 'point' in o: 
                                        total_line = o['point']
                                        over_odd = o['price']
                                    elif o['name'] == 'Under' and 'point' in o:
                                        under_odd = o['price']
                                        
                    if h_o > 1:
                        odds_dict[(h_cn, a_cn)] = (h_o, d_o, a_o, handicap, hc_h_odd, hc_a_odd, total_line, over_odd, under_odd)
        except: pass
        
        for m in upcoming:
            h_cn, a_cn = m['home'], m['away']
            odds = odds_dict.get((h_cn, a_cn), (0, 0, 0, -999.0, 0.0, 0.0, -999.0, 0.0, 0.0))
            all_matches.append({
                '联赛': m['league'], '比赛时间': m['datetime'], '主队': h_cn, '客队': a_cn,
                '主胜赔率': odds[0], '平局赔率': odds[1], '客胜赔率': odds[2],
                '让球盘口': odds[3], '主让胜赔率': odds[4], '客受让胜赔率': odds[5],
                '大小球盘口': odds[6], '大球赔率': odds[7], '小球赔率': odds[8]
            })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df = df.drop_duplicates(subset=['比赛时间', '主队', '客队'])
        # 替换掉 -999 的假数据，转为 NaN
        df.replace(-999.0, pd.NA, inplace=True)
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 抓取完毕！共获取 {len(df)} 场比赛。")
