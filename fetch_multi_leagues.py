import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

EXTRA_MAPPING = {
    'Sabah FK': '萨巴巴库', 'Sabah': '萨巴巴库', 'Slovan Bratislava': '布拉迪斯拉发', 'FC Porto': '波尔图',
    'Qarabag FK': '卡拉巴赫', 'Qarabag': '卡拉巴赫', 'Sporting Braga': '布拉加', 'FC Copenhagen': '哥本哈根',
    'PSV Eindhoven': '埃因霍温', 'Feyenoord': '费耶诺德', 'Young Boys': '伯尔尼年轻人', 'Red Star Belgrade': '贝尔格莱德红星',
    'FC Salzburg': '萨尔茨堡红牛', 'Dinamo Zagreb': '萨格勒布迪纳摩', 'Slavia Prague': '布拉格斯拉维亚', 'Sturm Graz': '格拉茨风暴',
    'Sparta Prague': '布拉格斯巴达', 'Union St. Gilloise': '圣吉尔联', 'Shakhtar Donetsk': '顿涅茨克矿工',
    'Atalanta': '亚特兰大', 'Bayer Leverkusen': '勒沃库森'
}

def smart_translate(name):
    translated = translate_team_name(name)
    if translated == name:
        return EXTRA_MAPPING.get(name, name)
    return translated

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    for league_name, config in LEAGUES.items():
        print(f"⏳ 正在抓取 {league_name} 赛程与盘口...")
        upcoming = []
        
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
            resp = requests.get("https://api.the-odds-api.com/v4/sports/" + config['odds_api_code'] + "/odds", 
                                params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h,spreads,totals', 'oddsFormat': 'decimal'}, timeout=20)
            odds_data = resp.json() if resp.status_code == 200 else []
            
            for match in odds_data:
                h_cn = smart_translate(match['home_team'])
                a_cn = smart_translate(match['away_team'])
                
                h_odd, d_odd, a_odd = 0, 0, 0
                handicap, h_handicap_odd, a_handicap_odd = 0.0, 0.0, 0.0
                total_line, over_odd, under_odd = 0.0, 0.0, 0.0
                
                if match.get('bookmakers'):
                    # 🌟 核心修改：遍历所有博彩公司，只要有一家提供了盘口就抓取！
                    for b in match['bookmakers']:
                        for market in b['markets']:
                            if market['key'] == 'h2h' and h_odd == 0:
                                for o in market['outcomes']:
                                    if o['name'] == match['home_team']: h_odd = o['price']
                                    elif o['name'] == match['away_team']: a_odd = o['price']
                                    elif o['name'] == 'Draw': d_odd = o['price']
                            elif market['key'] == 'spreads' and handicap == 0.0:
                                for o in market['outcomes']:
                                    if o['name'] == match['home_team']: 
                                        handicap = o['point']
                                        h_handicap_odd = o['price']
                                    elif o['name'] == match['away_team']:
                                        a_handicap_odd = o['price']
                            elif market['key'] == 'totals' and total_line == 0.0:
                                for o in market['outcomes']:
                                    if o['name'] == 'Over': 
                                        total_line = o['point']
                                        over_odd = o['price']
                                    elif o['name'] == 'Under':
                                        under_odd = o['price']
                                
                if h_odd > 1:
                    odds_dict[(h_cn, a_cn)] = (h_odd, d_odd, a_odd, handicap, h_handicap_odd, a_handicap_odd, total_line, over_odd, under_odd)
        except Exception as e: 
            print(f"⚠️ 获取赔率出错: {e}")
        
        for m in upcoming:
            h_cn = smart_translate(m['home_team'])
            a_cn = smart_translate(m['away_team'])
            odds = odds_dict.get((h_cn, a_cn), (0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            all_matches.append({
                '联赛': m['league'], '比赛时间': m['datetime'],
                '主队': h_cn, '客队': a_cn,
                '主胜赔率': odds[0], '平局赔率': odds[1], '客胜赔率': odds[2],
                '让球盘口': odds[3], '主让胜赔率': odds[4], '客受让胜赔率': odds[5],
                '大小球盘口': odds[6], '大球赔率': odds[7], '小球赔率': odds[8]
            })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 抓取完毕！共获取 {len(df)} 场比赛，已保存到 daily_matches.csv")
    else:
        print("❌ 未能抓取到任何比赛。")

if __name__ == "__main__":
    fetch_schedule_and_odds()
