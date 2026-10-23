import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from config import LEAGUES
from team_mapping import translate_team_name

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    
    # 🌟 核心升级：优先读取你手动填写的比赛清单
    if os.path.exists('manual_matches.csv'):
        print("✅ 侦测到 manual_matches.csv，系统将优先以手动数据为准！")
        try:
            # 🌟 增加 encoding='utf-8-sig'，彻底免疫 BOM 头等隐藏字符
            df_manual = pd.read_csv('manual_matches.csv', encoding='utf-8-sig')
            
            # 强制清理列名前后可能带的空格
            df_manual.columns = [c.strip() for c in df_manual.columns]
            
            df_manual['比赛时间'] = pd.to_datetime(df_manual['比赛时间'])
            # 剔除已经开赛或结束的比赛（留出 2 小时的缓冲防错）
            buffer_time = today - timedelta(hours=2)
            df_manual = df_manual[df_manual['比赛时间'] > buffer_time]
            
            for _, r in df_manual.iterrows():
                m_time = r['比赛时间']
                dt_parsed = m_time.tz_localize('Asia/Shanghai').tz_convert('UTC') 
                
                all_matches.append({
                    '联赛': r['赛事'].strip(), '比赛时间': dt_parsed, '主队': translate_team_name(r['主队'].strip()), '客队': translate_team_name(r['客队'].strip()),
                    '主胜赔率': r['主胜赔率'], '平局赔率': r['平局赔率'], '客胜赔率': r['客胜赔率'],
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                })
            print(f"🧹 自动过滤了过期比赛，当前有效比赛共 {len(all_matches)} 场。")
        except Exception as e:
            print(f"⚠️ 手动数据解析失败，请检查 CSV 格式是否正确: {e}")
            
    # 如果手动文件为空或不存在，再尝试外网抓取（备用）
    if not all_matches:
        print("⚠️ 未发现有效的手动数据，尝试从 ESPN 抓取...")
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
