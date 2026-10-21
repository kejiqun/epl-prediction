import requests
import pandas as pd
import os
from datetime import datetime
from team_mapping import translate_team_name

PINNWIRE_API_KEY = os.environ.get("PINNWIRE_API_KEY")
if not PINNWIRE_API_KEY:
    print("❌ 没有读取到 PINNWIRE_API_KEY！")
    exit()

PINNWIRE_BASE_URL = "https://pinnwire.com/kit/v1"
SOCCER_SPORT_ID = 1

def fetch_real_odds():
    print("⏳ 正在通过 PinnWire 获取全球真实盘口...")
    params = {"key": PINNWIRE_API_KEY, "sport_id": SOCCER_SPORT_ID}
    url = f"{PINNWIRE_BASE_URL}/prematch/fixtures"
    
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            print(f"❌ PinnWire 请求失败: {resp.status_code}")
            return

        data = resp.json()
        events = data.get('events', [])
        if not events:
            print("⚠️ 未返回比赛数据。")
            return

        all_odds = []
        valid_leagues = ['England - Premier League', 'Spain - La Liga', 'Germany - Bundesliga', 'Italy - Serie A', 'France - Ligue 1', 'UEFA Champions League', 'UEFA Europa League']
        
        for match in events:
            try:
                league_name = match.get('league_name', '')
                if not any(vl in league_name for vl in valid_leagues):
                    continue
                    
                home_team = translate_team_name(match.get('home'))
                away_team = translate_team_name(match.get('away'))
                match_time_str = match.get('starts')
                
                periods = match.get('periods', {})
                num_0 = periods.get('num_0', {})
                
                ml = num_0.get('money_line', {})
                h_odd, d_odd, a_odd = ml.get('home'), ml.get('draw'), ml.get('away')
                
                spreads = num_0.get('spreads', {})
                handicap, hc_h_odd, hc_a_odd = 0.0, 0.0, 0.0
                if spreads:
                    for key in spreads:
                        handicap = spreads[key].get('hdp', 0.0)
                        hc_h_odd = spreads[key].get('home', 0.0)
                        hc_a_odd = spreads[key].get('away', 0.0)
                        break 
                        
                totals = num_0.get('totals', {})
                over_under_line, over_odd, under_odd = 2.5, 0.0, 0.0
                if totals:
                    for key in totals:
                        over_under_line = totals[key].get('points', 2.5)
                        over_odd = totals[key].get('over', 0.0)
                        under_odd = totals[key].get('under', 0.0)
                        break

                if h_odd and a_odd and home_team and away_team:
                    all_odds.append({
                        '比赛时间': match_time_str, '主队': home_team, '客队': away_team,
                        '主胜赔率': float(h_odd), '平局赔率': float(d_odd) if d_odd else 0.0, '客胜赔率': float(a_odd),
                        '让球盘口': float(handicap), '主让胜赔率': float(hc_h_odd), '客受让胜赔率': float(hc_a_odd),
                        '大小球盘口': float(over_under_line), '大球赔率': float(over_odd), '小球赔率': float(under_odd)
                    })
            except Exception:
                continue
        
        if all_odds:
            df = pd.DataFrame(all_odds).drop_duplicates(subset=['比赛时间', '主队', '客队'])
            df.to_csv('real_odds.csv', index=False, encoding='utf-8-sig')
            print(f"✅ PinnWire 真实盘口抓取成功！{len(df)} 场有效数据。")
            
    except Exception as e:
        print(f"❌ 异常: {e}")

if __name__ == "__main__":
    fetch_real_odds()
