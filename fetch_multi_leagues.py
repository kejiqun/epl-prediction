import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

# 🌟 扩充后的超级字典，覆盖五大联赛常见球队
team_mapping = {
    # 英超
    'Arsenal FC': '阿森纳', 'Arsenal': '阿森纳', 'Aston Villa FC': '阿斯顿维拉', 'Aston Villa': '阿斯顿维拉',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Brighton & Hove Albion FC': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西', 'Crystal Palace FC': '水晶宫', 'Crystal Palace': '水晶宫',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿', 'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Ipswich Town FC': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester City FC': '莱斯特城', 'Leicester City': '莱斯特城',
    'Liverpool FC': '利物浦', 'Liverpool': '利物浦', 'Manchester City FC': '曼城', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United FC': '曼联', 'Manchester United': '曼联', 'Man United': '曼联', 'Man Utd': '曼联',
    'Newcastle United FC': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联', 'Newcastle': '纽卡斯尔联',
    'Nottingham Forest FC': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林',
    'Southampton FC': '南安普顿', 'Southampton': '南安普顿', 'Tottenham Hotspur FC': '托特纳姆热刺', 'Tottenham Hotspur': '托特纳姆热刺', 'Tottenham': '热刺',
    'West Ham United FC': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolverhampton Wanderers FC': '狼队', 'Wolverhampton Wanderers': '狼队', 'Wolves': '狼队',
    # 西甲
    'Real Madrid CF': '皇家马德里', 'Real Madrid': '皇家马德里', 'FC Barcelona': '巴塞罗那', 'Barcelona': '巴塞罗那',
    'Atletico Madrid': '马德里竞技', 'Atlético Madrid': '马德里竞技', 'Athletic Club': '毕尔巴鄂竞技', 'Getafe CF': '赫塔菲', 'Getafe': '赫塔菲',
    'Real Sociedad': '皇家社会', 'Sevilla FC': '塞维利亚', 'Sevilla': '塞维利亚', 'Real Betis': '皇家贝蒂斯', 'Villarreal CF': '比利亚雷亚尔', 'Villarreal': '比利亚雷亚尔',
    'Valencia CF': '瓦伦西亚', 'Valencia': '瓦伦西亚', 'Celta Vigo': '塞尔塔', 'Osasuna': '奥萨苏纳', 'Deportivo': '拉科鲁尼亚',
    'Levante': '莱万特', 'Girona': '赫罗纳', 'Alaves': '阿拉维斯', 'Mallorca': '马洛卡', 'Las Palmas': '拉斯帕尔马斯', 'Rayo Vallecano': '巴列卡诺',
    # 德甲
    'Bayern Munich': '拜仁慕尼黑', 'FC Bayern Munich': '拜仁慕尼黑', 'Borussia Dortmund': '多特蒙德', 'Bayer Leverkusen': '勒沃库森', 'RB Leipzig': '莱比锡红牛',
    'VfB Stuttgart': '斯图加特', 'Eintracht Frankfurt': '法兰克福', 'Borussia Mönchengladbach': '门兴格拉德巴赫', 'FC Augsburg': '奥格斯堡',
    '1. FC Union Berlin': '柏林联合', 'Union Berlin': '柏林联合', 'FC Cologne': '科隆', 'Schalke 04': '沙尔克04', 'Mainz': '美因茨', 'Mainz 05': '美因茨',
    'Werder Bremen': '云达不莱梅', 'SC Paderborn 07': '帕德博恩', 'Hamburg SV': '汉堡', 'SV Elversberg': '艾禾斯堡', 'Hoffenheim': '霍芬海姆',
    'SC Freiburg': '弗赖堡', 'VfL Wolfsburg': '沃尔夫斯堡', 'FC Heidenheim': '海登海姆', 'VfL Bochum': '波鸿', 'FC St. Pauli': '圣保利',
    # 意甲
    'Inter Milan': '国际米兰', 'Inter': '国际米兰', 'AC Milan': 'AC米兰', 'Juventus': '尤文图斯', 'Napoli': '那不勒斯', 'AS Roma': '罗马', 'Roma': '罗马',
    'Lazio': '拉齐奥', 'Atalanta': '亚特兰大', 'Fiorentina': '佛罗伦萨', 'Torino': '都灵', 'Monza': '蒙扎', 'Cagliari': '卡利亚里', 'Bologna': '博洛尼亚',
    'Udinese': '乌迪内斯', 'Genoa': '热那亚', 'Lecce': '莱切', 'Verona': '维罗纳', 'Empoli': '恩波利', 'Parma': '帕尔马', 'Como': '科莫', 'Venezia': '威尼斯',
    'Sassuolo': '萨索洛', 'Salernitana': '萨勒尼塔纳', 'Frosinone': '弗洛西诺内'
}

def translate_team_name(name):
    if isinstance(name, str): 
        # 有时候名字会带空格或 and，统一下
        cleaned_name = name.replace(" and ", " & ").strip()
        return team_mapping.get(cleaned_name, cleaned_name)
    return name

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    for league_name, config in LEAGUES.items():
        print(f"⏳ 正在抓取 {league_name} 赛程与赔率...")
        
        upcoming = []
        for i in range(7):
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
                                params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h', 'oddsFormat': 'decimal'}, timeout=20)
            odds_data = resp.json() if resp.status_code == 200 else []
            for match in odds_data:
                h_cn = translate_team_name(match['home_team'])
                a_cn = translate_team_name(match['away_team'])
                if match.get('bookmakers'):
                    b = match['bookmakers'][0]
                    h_odd, d_odd, a_odd = 0, 0, 0
                    for o in b['markets'][0]['outcomes']:
                        if o['name'] == match['home_team']: h_odd = o['price']
                        elif o['name'] == match['away_team']: a_odd = o['price']
                        elif o['name'] == 'Draw': d_odd = o['price']
                    if h_odd > 1:
                        odds_dict[(h_cn, a_cn)] = (h_odd, d_odd, a_odd)
        except: pass
        
        for m in upcoming:
            h_cn = translate_team_name(m['home_team'])
            a_cn = translate_team_name(m['away_team'])
            odds = odds_dict.get((h_cn, a_cn), (0, 0, 0))
            all_matches.append({
                'league': m['league'], 'datetime': m['datetime'],
                'home_team': h_cn, 'away_team': a_cn,
                'odds_h': odds[0], 'odds_d': odds[1], 'odds_a': odds[2]
            })
            
    df = pd.DataFrame(all_matches)
    if not df.empty:
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 抓取完毕！共获取 {len(df)} 场比赛，已保存到 daily_matches.csv")
    else:
        print("❌ 未能抓取到任何比赛。")

if __name__ == "__main__":
    fetch_schedule_and_odds()
