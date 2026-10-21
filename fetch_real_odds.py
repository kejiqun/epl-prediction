import requests
import pandas as pd
import os
from datetime import datetime
from team_mapping import translate_team_name

PINNWIRE_API_KEY = os.environ.get("PINNWIRE_API_KEY")
if not PINNWIRE_API_KEY:
    print("❌ 严重警告：没有读取到 PINNWIRE_API_KEY！请检查 GitHub Secrets。")
else:
    print(f"🔑 成功读取到 Key，前4位是: {PINNWIRE_API_KEY[:4]}...")

PINNWIRE_BASE_URL = "https://pinnwire.com/kit/v1"
SOCCER_SPORT_ID = 1

def fetch_real_odds():
    print("⏳ 正在通过 PinnWire 获取全球真实盘口...")
    params = {"key": PINNWIRE_API_KEY, "sport_id": SOCCER_SPORT_ID}
    url = f"{PINNWIRE_BASE_URL}/prematch/fixtures"
    
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            print(f"❌ PinnWire 请求失败，状态码: {resp.status_code}")
            return

        data = resp.json()
        events = data.get('events', [])
        if not events:
            print("⚠️ PinnWire 未返回任何赛前比赛数据。")
            return

        all_odds = []
        # 过滤白名单：只要五大联赛和欧战
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
                
                # 1. 胜平负
                ml = num_0.get('money_line', {})
                h_odd = ml.get('home')
                d_odd = ml.get('draw')
                a_odd = ml.get('away')
                
                # 2. 让球盘 (spreads)
                spreads = num_0.get('spreads', {})
                handicap = 0.0
                hc_h_odd = 0.0
                hc_a_odd = 0.0
                if spreads:
                    for key in spreads:
                        handicap = spreads[key].get('hdp', 0.0)
                        hc_h_odd = spreads[key].get('home', 0.0)
                        hc_a_odd = spreads[key].get('away', 0.0)
                        break # 只拿第一个盘口
                        
                # 3. 大小球 (totals)
                totals = num_0.get('totals', {})
                over_under_line = 2.5
                over_odd = 0.0
                under_odd = 0.0
                if totals:
                    for key in totals:
                        over_under_line = totals[key].get('points', 2.5)
                        over_odd = totals[key].get('over', 0.0)
                        under_odd = totals[key].get('under', 0.0)
                        break # 只拿第一个盘口

                if h_odd and a_odd and home_team and away_team:
                    all_odds.append({
                        '比赛时间': match_time_str,
                        '主队': home_team,
                        '客队': away_team,
                        '主胜赔率': float(h_odd),
                        '平局赔率': float(d_odd) if d_odd else 0.0,
                        '客胜赔率': float(a_odd),
                        '让球盘口': float(handicap),
                        '主让胜赔率': float(hc_h_odd),
                        '客受让胜赔率': float(hc_a_odd),
                        '大小球盘口': float(over_under_line),
                        '大球赔率': float(over_odd),
                        '小球赔率': float(under_odd)
                    })
            except Exception as e:
                continue
        
        if all_odds:
            df = pd.DataFrame(all_odds).drop_duplicates(subset=['比赛时间', '主队', '客队'])
            df.to_csv('real_odds.csv', index=False, encoding='utf-8-sig')
            print(f"✅ PinnWire 真实盘口抓取成功！过滤后共获取 {len(df)} 场有效比赛数据。")
        else:
            print("⚠️ 解析到了数据，但经过联赛过滤后，没有找到符合条件的比赛。")
            
    except Exception as e:
        print(f"❌ 请求 PinnWire 时发生异常: {e}")

if __name__ == "__main__":
    fetch_real_odds()
