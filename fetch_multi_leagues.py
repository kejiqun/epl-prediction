import pandas as pd
import requests
from datetime import datetime, timedelta
import os
from team_mapping import translate_team_name

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

TARGET_LEAGUES = {
    '英超': 39, '西甲': 140, '德甲': 78, '意甲': 135, '法甲': 61,
    '瑞典超': 113, '挪超': 103, '丹超': 119,
    '欧冠': 2, '欧联': 3
}
CURRENT_SEASON = 2026 

def fetch_schedule_and_odds():
    all_matches = []
    today = datetime.now()
    today_date_str = today.strftime('%Y-%m-%d')
    
    if not API_FOOTBALL_KEY:
        print("❌ 致命错误：没有读取到 API_FOOTBALL_KEY！")
        return

    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    print(f"⏳ 启动官方数据源：正在抓取 {today_date_str} 的比赛与赔率...")

    for league_name, league_id in TARGET_LEAGUES.items():
        print(f"正在抓取 {league_name}...")
        
        # 1. 抓取赛程
        url_fixtures = f"https://v3.football.api-sports.io/fixtures?date={today_date_str}&league={league_id}&season={CURRENT_SEASON}"
        try:
            resp = requests.get(url_fixtures, headers=headers, timeout=15)
            if resp.status_code != 200: continue
                
            fixtures_data = resp.json().get('response', [])
            if not fixtures_data: continue
                
            fixtures_dict = {}
            for fixture in fixtures_data:
                f_id = fixture['fixture']['id']
                home_team = translate_team_name(fixture['teams']['home']['name'])
                away_team = translate_team_name(fixture['teams']['away']['name'])
                match_time = fixture['fixture']['date']
                
                fixtures_dict[f_id] = {
                    '联赛': league_name, '比赛时间': match_time, '主队': home_team, '客队': away_team,
                    '主胜赔率': 0.0, '平局赔率': 0.0, '客胜赔率': 0.0,
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                }

            # 2. 抓取赔率
            url_odds = f"https://v3.football.api-sports.io/odds?date={today_date_str}&league={league_id}&season={CURRENT_SEASON}"
            resp_odds = requests.get(url_odds, headers=headers, timeout=15)
            if resp_odds.status_code == 200:
                for odd_info in resp_odds.json().get('response', []):
                    f_id = odd_info['fixture']['id']
                    if f_id not in fixtures_dict: continue
                        
                    bookmakers = odd_info.get('bookmakers', [])
                    if not bookmakers: continue
                        
                    bets = bookmakers[0].get('bets', [])
                    for bet in bets:
                        if bet['name'] == 'Match Winner':
                            for val in bet['values']:
                                if val['value'] == 'Home': fixtures_dict[f_id]['主胜赔率'] = float(val['odd'])
                                elif val['value'] == 'Draw': fixtures_dict[f_id]['平局赔率'] = float(val['odd'])
                                elif val['value'] == 'Away': fixtures_dict[f_id]['客胜赔率'] = float(val['odd'])
                        elif bet['name'] == 'Goals Over/Under':
                            for val in bet['values']:
                                if val['value'] == 'Over 2.5': 
                                    fixtures_dict[f_id]['大球赔率'] = float(val['odd'])
                                elif val['value'] == 'Under 2.5': 
                                    fixtures_dict[f_id]['小球赔率'] = float(val['odd'])
                        elif bet['name'] == 'Asian Handicap':
                            for val in bet['values']:
                                try:
                                    if val['value'].startswith('Home'):
                                        fixtures_dict[f_id]['让球盘口'] = float(val['value'].replace('Home ', ''))
                                        fixtures_dict[f_id]['主让胜赔率'] = float(val['odd'])
                                    elif val['value'].startswith('Away'):
                                        fixtures_dict[f_id]['客受让胜赔率'] = float(val['odd'])
                                except: pass
                                
            all_matches.extend(list(fixtures_dict.values()))
        except Exception as e:
            print(f"⚠️ {league_name} 抓取异常: {e}")

    if all_matches:
        df = pd.DataFrame(all_matches).drop_duplicates(subset=['主队', '客队'])
        df.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 成功抓取 {len(df)} 场比赛及真实赔率！")
    else:
        # 兜底：检查手动数据
        if os.path.exists('manual_matches.csv'):
            print("👀 尝试使用手动数据兜底...")
            try:
                df_manual = pd.read_csv('manual_matches.csv', encoding='utf-8-sig')
                df_manual['比赛时间'] = pd.to_datetime(df_manual['比赛时间'])
                df_manual = df_manual[df_manual['比赛时间'] > (today - timedelta(hours=2))]
                
                df_out = pd.DataFrame({
                    '联赛': df_manual['赛事'], '比赛时间': df_manual['比赛时间'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                    '主队': df_manual['主队'].apply(translate_team_name), '客队': df_manual['客队'].apply(translate_team_name),
                    '主胜赔率': df_manual['主胜赔率'], '平局赔率': df_manual['平局赔率'], '客胜赔率': df_manual['客胜赔率'],
                    '让球盘口': 0.0, '主让胜赔率': 0.0, '客受让胜赔率': 0.0,
                    '大小球盘口': 2.5, '大球赔率': 0.0, '小球赔率': 0.0
                })
                df_out.to_csv('daily_matches.csv', index=False, encoding='utf-8-sig')
                print(f"✅ 已降级使用手动数据，共 {len(df_out)} 场。")
            except Exception as e:
                print(f"❌ 兜底数据读取失败: {e}")

if __name__ == "__main__":
    fetch_schedule_and_odds()
