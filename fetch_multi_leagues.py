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
    
    # 读取历史赔率记录 (如果有的话)
    odds_history = pd.DataFrame(columns=['date_str', 'home_team', 'away_team', 'init_h', 'init_d', 'init_a', 'current_h', 'current_d', 'current_a'])
    if os.path.exists('odds_history.csv'):
        odds_history = pd.read_csv('odds_history.csv')
    
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
            
        try:
            resp = requests.get("https://api.the-odds-api.com/v4/sports/" + config['odds_api_code'] + "/odds", 
                                params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h,spreads,totals', 'oddsFormat': 'decimal'}, timeout=20)
            if resp.status_code == 200:
                for match in resp.json():
                    h_cn, a_cn = translate_team_name(match['home_team']), translate_team_name(match['away_team'])
                    h_o, d_o, a_o, hc, tl = 0, 0, 0, 0.0, 2.5
                    if match.get('bookmakers'):
                        for market in match['bookmakers'][0]['markets']:
                            if market['key'] == 'h2h':
                                for o in market['outcomes']:
                                    if o['name'] == match['home_team']: h_o = o['price']
                                    elif o['name'] == match['away_team']: a_o = o['price']
                                    elif o['name'] == 'Draw': d_o = o['price']
                            elif market['key'] == 'spreads':
                                for o in market['outcomes']:
                                    if o['name'] == match['home_team']: hc = o['point']
                            elif market['key'] == 'totals':
                                for o in market['outcomes']:
                                    if o['name'] == 'Over': tl = o['point']
                    
                    if h_o > 1:
                        # 记录或更新赔率轨迹
                        match_date = match['commence_time'][:10]
                        existing = odds_history[(odds_history['date_str'] == match_date) & (odds_history['home_team'] == h_cn) & (odds_history['away_team'] == a_cn)]
                        if existing.empty:
                            # 第一次抓到这个盘，记录为初盘
                            new_row = {'date_str': match_date, 'home_team': h_cn, 'away_team': a_cn, 'init_h': h_o, 'init_d': d_o, 'init_a': a_o, 'current_h': h_o, 'current_d': d_o, 'current_a': a_o}
                            odds_history = pd.concat([odds_history, pd.DataFrame([new_row])], ignore_index=True)
                        else:
                            # 更新临场盘
                            idx = existing.index[0]
                            odds_history.at[idx, 'current_h'] = h_o
                            odds_history.at[idx, 'current_d'] = d_o
                            odds_history.at[idx, 'current_a'] = a_o
                            
                        upcoming_odds = (h_o, d_o, a_o, hc, tl)
            # 保存历史
            odds_history.to_csv('odds_history.csv', index=False, encoding='utf-8-sig')
        except Exception as e: pass
        
        for m in upcoming:
            odds = odds_history[(odds_history['home_team'] == m['home']) & (odds_history['away_team'] == m['away'])]
            if not odds.empty:
                row = odds.iloc[-1]
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': m['home'], '客队': m['away'],
                    '主胜赔率': row['current_h'], '平局赔率': row['current_d'], '客胜赔率': row['current_a'],
                    '初盘主胜': row['init_h'], '初盘平局': row['init_d'], '初盘客胜': row['init_a'],
                    '让球盘口': 0.0, '大小球盘口': 2.5
                })
            else:
                all_matches.append({
                    '联赛': m['league'], '比赛时间': m['datetime'], '主队': m['home'], '客队': m['away'],
                    '主胜赔率': 0, '平局赔率': 0, '客胜赔率': 0, '初盘主胜': 0, '初盘平局': 0, '初盘客胜': 0,
                    '让球盘口': 0.0, '大小球盘口': 2.5
                })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df = df.drop_duplicates(subset=['比赛时间', '主队', '客队'])
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 抓取完毕！共获取 {len(df)} 场比赛。")
