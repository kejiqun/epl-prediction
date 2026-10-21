import requests
import pandas as pd
import os
from datetime import datetime, timedelta
from team_mapping import translate_team_name

# 从 GitHub Secrets 获取 Key，如果没有设置，默认使用 'demo'
PINNWIRE_API_KEY = os.environ.get("PINNWIRE_API_KEY", "demo")

# PinnWire 的 REST API 基础地址
PINNWIRE_BASE_URL = "https://pinnwire.com/kit/v1"

# PinnWire 中足球的 sport_id 是 1
SOCCER_SPORT_ID = 1

def fetch_real_odds():
    print("⏳ 正在通过 PinnWire 获取全球真实盘口...")
    
    params = {
        "key": PINNWIRE_API_KEY,
        "sport_id": SOCCER_SPORT_ID
    }
    
    # 我们抓取赛前（Prematch）的赔率
    url = f"{PINNWIRE_BASE_URL}/prematch/fixtures"
    
    try:
        resp = requests.get(url, params=params, timeout=20)
        
        if resp.status_code != 200:
            print(f"❌ PinnWire 请求失败，状态码: {resp.status_code}")
            # 尝试打印错误信息
            try:
                print(resp.json())
            except:
                pass
            return

        data = resp.json()
        # PinnWire 的响应结构通常是 { "fixtures": [...] }
        fixtures = data.get('fixtures', data.get('data', []))
        
        if not fixtures:
            print("⚠️ PinnWire 未返回任何赛前比赛数据。")
            return

        all_odds = []
        
        for match in fixtures:
            try:
                # 解析比赛和赔率信息
                home_team = translate_team_name(match['home'])
                away_team = translate_team_name(match['away'])
                match_time_str = match['start_time'] # ISO 格式时间
                
                # 获取赔率字典
                odds_dict = match.get('odds', {})
                # 这里我们尝试提取最常规的赔率：胜平负（Moneyline）和大小球（Totals）
                # 注意：具体字段名需要根据 PinnWire 实际返回的 JSON 调整，这里使用常见命名
                
                # 胜平负赔率
                moneyline = odds_dict.get('moneyline', {})
                h_odd = moneyline.get('home')
                d_odd = moneyline.get('draw')
                a_odd = moneyline.get('away')
                
                # 大小球盘口
                totals = odds_dict.get('totals', {})
                over_under_line = totals.get('points') # 盘口，如 2.5
                
                if h_odd and a_odd:
                    all_odds.append({
                        '比赛时间': match_time_str,
                        '主队': home_team,
                        '客队': away_team,
                        '主胜赔率': float(h_odd),
                        '平局赔率': float(d_odd) if d_odd else 0.0,
                        '客胜赔率': float(a_odd),
                        '大小球盘口': float(over_under_line) if over_under_line else 2.5
                    })
            except Exception as e:
                print(f"⚠️ 解析单场比赛数据失败: {e}")
                continue
        
        if all_odds:
            df = pd.DataFrame(all_odds).drop_duplicates(subset=['比赛时间', '主队', '客队'])
            df.to_csv('real_odds.csv', index=False, encoding='utf-8-sig')
            print(f"✅ PinnWire 真实盘口抓取成功！共获取 {len(df)} 场比赛数据。")
        else:
            print("⚠️ 未能解析出有效的赔率数据。")
            
    except Exception as e:
        print(f"❌ 请求 PinnWire 时发生异常: {e}")

if __name__ == "__main__":
    fetch_real_odds()
