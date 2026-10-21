import requests
import pandas as pd
import os
from datetime import datetime
from team_mapping import translate_team_name

def fetch_500_odds():
    print("⏳ 启动国内数据源：正在从 500彩票网 抓取真实盘口...")
    url = "https://trade.500.com/jczq/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = 'gb2312'
        
        # 通过 pandas 极速抓取网页中的表格
        # 注意：需要 lxml 库支持，如果没装会报错
        try:
            tables = pd.read_html(resp.text)
        except Exception as e:
            print(f"⚠️ 网页解析失败，可能是反爬机制或缺少依赖: {e}")
            return

        if not tables:
            print("⚠️ 未能从 500彩票网 解析到表格数据。")
            return
            
        df_raw = tables[0]
        all_matches = []
        
        for idx, row in df_raw.iterrows():
            try:
                # 提取比赛时间、主队、客队
                match_time_str = str(row.get('比赛时间', ''))
                if not match_time_str or '未' in match_time_str:
                    continue
                    
                home_team = translate_team_name(str(row.get('主队', '')).strip())
                away_team = translate_team_name(str(row.get('客队', '')).strip())
                
                # 简单过滤掉一些非比赛的脏数据行
                if home_team and away_team and len(home_team) < 20 and len(away_team) < 20:
                    all_matches.append({
                        '比赛时间': match_time_str,
                        '主队': home_team,
                        '客队': away_team,
                        '主胜赔率': float(row.get('胜', 0)),
                        '平局赔率': float(row.get('平', 0)),
                        '客胜赔率': float(row.get('负', 0)),
                    })
            except Exception:
                continue
                
        if all_matches:
            df = pd.DataFrame(all_matches)
            # 去重
            df = df.drop_duplicates(subset=['比赛时间', '主队', '客队'])
            df.to_csv('domestic_odds.csv', index=False, encoding='utf-8-sig')
            print(f"✅ 500彩票网 抓取成功！共获取 {len(df)} 场比赛真实赔率。")
        else:
            print("⚠️ 500彩票网 未找到有效的比赛数据。")
            
    except Exception as e:
        print(f"❌ 抓取 500彩票网 失败: {e}")

if __name__ == "__main__":
    fetch_500_odds()
