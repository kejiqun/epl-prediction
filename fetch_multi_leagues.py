import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_schedule_and_odds():
    all_matches = []
    
    # 🌟 核心升级：优先读取你手动填写的比赛清单
    if os.path.exists('manual_matches.csv'):
        print("✅ 侦测到 manual_matches.csv，系统将优先以手动数据为准！")
        try:
            df_manual = pd.read_csv('manual_matches.csv')
            for _, r in df_manual.iterrows():
                m_date = str(r['比赛日期']).strip()
                # 转换成带时区的标准时间格式
                dt_parsed = pd.to_datetime(m_date + 'T12:00:00Z') 
                
                all_matches.append({
                    '联赛': r['赛事'], '比赛时间': dt_parsed, '主队': translate_team_name(r['主队']), '客队': translate_team_name(r['客队']),
                    '主胜赔率': r['主胜赔率'], '平局赔率': r['平局赔率'], '客胜赔率': r['客胜赔率'],
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                })
        except Exception as e:
            print(f"⚠️ 手动数据解析失败，请检查 CSV 格式: {e}")
            
    # 如果手动文件为空或不存在，再尝试外网抓取（备用）
    if not all_matches:
        print("⚠️ 未发现手动数据，尝试从 ESPN 抓取...")
        today = datetime.now()
        for league_name, config in LEAGUES.items():
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
                                        all_matches.append({
                                            '联赛': league_name, '比赛时间': event['date'], 
                                            '主队': translate_team_name(h_t), '客队': translate_team_name(a_t),
                                            '主胜赔率': 0, '平局赔率': 0, '客胜赔率': 0,
                                            '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                                            '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                                        })
                except: continue

    df = pd.DataFrame(all_matches)
    if not df.empty:
        df = df.drop_duplicates(subset=['主队', '客队'])
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 赛程数据已生成！共 {len(df)} 场比赛进入待预测池。")
    else:
        print("❌ 没有比赛数据。")

if __name__ == "__main__":
    fetch_schedule_and_odds()
