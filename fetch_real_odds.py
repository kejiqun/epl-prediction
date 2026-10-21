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
    
    params = {
        "key": PINNWIRE_API_KEY,
        "sport_id": SOCCER_SPORT_ID
    }
    
    url = f"{PINNWIRE_BASE_URL}/prematch/fixtures"
    
    try:
        resp = requests.get(url, params=params, timeout=20)
        
        if resp.status_code != 200:
            print(f"❌ PinnWire 请求失败，状态码: {resp.status_code}")
            print(f"详细报错: {resp.text}")
            return

        data = resp.json()
        # 🌟 核心修正：根据截图，根节点是 events
        events = data.get('events', [])
        
        if not events:
            print("⚠️ PinnWire 未返回任何赛前比赛数据。")
            return

        all_odds = []
        
        for match in events:
            try:
                # 🌟 核心修正：根据截图提取字段
                home_team = translate_team_name(match.get('home'))
                away_team = translate_team_name(match.get('away'))
                match_time_str = match.get('starts') # 截图显示是 starts
                
                # 提取赔率
                periods = match.get('periods', {})
                num_0 = periods.get('num_0', {})
                
                # 1. 胜平负
                ml = num_0.get('money_line', {})
                h_odd = ml.get('home')
                d_odd = ml.get('draw')
                a_odd = ml.get('away')
                
                # 2. 大小球 (寻找最接近 2.5 或 3.0 的盘口)
                totals = num_0.get('totals', {})
                over_under_line = 2.5
                if totals:
                    # 尝试找 2.5
                    if "2.5" in totals:
                        over_under_line = 2.5
                    elif "3" in totals:
                        over_under_line = 3.0
                    else:
                        # 如果都没有，随便拿第一个
                        first_key = list(totals.keys())[0]
                        if isinstance(totals[first_key], dict):
                            over_under_line = totals[first_key].get('points', 2.5)

                # 如果主客胜赔率都有，就保存
                if h_odd and a_odd and home_team and away_team:
                    all_odds.append({
                        '比赛时间': match_time_str,
                        '主队': home_team,
                        '客队': away_team,
                        '主胜赔率': float(h_odd),
                        '平局赔率': float(d_odd) if d_odd else 0.0,
                        '客胜赔率': float(a_odd),
                        '大小球盘口': float(over_under_line)
                    })
            except Exception as e:
                # 如果某场比赛解析失败，跳过它，不影响其他比赛
                continue
        
        if all_odds:
            df = pd.DataFrame(all_odds).drop_duplicates(subset=['比赛时间', '主队', '客队'])
            df.to_csv('real_odds.csv', index=False, encoding='utf-8-sig')
            print(f"✅ PinnWire 真实盘口抓取成功！共获取 {len(df)} 场比赛数据。")
        else:
            print("⚠️ 解析到了数据，但没有找到符合条件的赔率盘口。")
            
    except Exception as e:
        print(f"❌ 请求 PinnWire 时发生异常: {e}")

if __name__ == "__main__":
    fetch_real_odds()
