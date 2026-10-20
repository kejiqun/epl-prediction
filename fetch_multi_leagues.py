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
        print(f"⏳ 正在抓取 {league_name} 赛程与赔率...")
        upcoming = []
        
        # 只抓未来 3 天（确保比赛是马上要打的）
        for i in range(3): 
            date_str = (today + timedelta(days=i)).strftime('%Y%m%d')
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={date_str}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for event in data.get('events', []):
                        if event['status']['type']['state'] == 'pre':
                            competitions = event.get('competitions', [])
                            if competitions:
                                competitors = competitions[0].get('competitors', [])
                                home_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'home'), None)
                                away_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'away'), None)
                                if home_team and away_team:
                                    upcoming.append({
                                        'league': league_name, 'datetime': event['date'], 
                                        'home_team': home_team, 'away_team': away_team
                                    })
            except: continue
            
        odds_dict = {}
        try:
            # 🌟 恢复亚盘(spreads)和大小球(totals)请求
            resp = requests.get("https://api.the-odds-api.com/v4/sports/" + config['odds_api_code'] + "/odds", 
                                params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h,spreads,totals', 'oddsFormat': 'decimal'}, timeout=20)
            odds_data = resp.json() if resp.status_code == 200 else []
            for match in odds_data:
                h_cn = translate_team_name(match['home_team'])
                a_cn = translate_team_name(match['away_team'])
                
                h_odd, d_odd, a_odd = 0, 0, 0
                handicap, total_line = 0.0, 0.0
                
                if match.get('bookmakers'):
                    b = match['bookmakers'][0]
                    for market in b['markets']:
                        if market['key'] == 'h2h':
                            for o in market['outcomes']:
                                if o['name'] == match['home_team']: h_odd = o['price']
                                elif o['name'] == match['away_team']: a_odd = o['price']
                                elif o['name'] == 'Draw': d_odd = o['price']
                        elif market['key'] == 'spreads':
                            for o in market['outcomes']:
                                if o['name'] == match['home_team']: handicap = o['point']
                        elif market['key'] == 'totals':
                            for o in market['outcomes']:
                                if o['name'] == 'Over': total_line = o['point']
                                
                if h_odd > 1:
                    odds_dict[(h_cn, a_cn)] = (h_odd, d_odd, a_odd, handicap, total_line)
        except: pass
        
        for m in upcoming:
            h_cn = translate_team_name(m['home_team'])
            a_cn = translate_team_name(m['away_team'])
            odds = odds_dict.get((h_cn, a_cn), (0, 0, 0, 0.0, 0.0))
            all_matches.append({
                'league': m['league'], 'datetime': m['datetime'],
                'home_team': h_cn, 'away_team': a_cn,
                'odds_h': odds[0], 'odds_d': odds[1], 'odds_a': odds[2],
                'handicap': odds[3], 'total_line': odds[4]
            })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 抓取完毕！共获取 {len(df)} 场比赛，已保存到 daily_matches.csv")
    else:
        print("❌ 未能抓取到任何比赛。")

if __name__ == "__main__":
    fetch_schedule_and_odds()
