#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import numpy as np
import requests
import joblib
import os
import json
from scipy.stats import poisson
from datetime import datetime, timedelta
import warnings
from openai import OpenAI

warnings.filterwarnings('ignore')
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.width', 1000)

# ==================== ⚠️ 必须配置的密钥区 ====================
import os
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

# ==================== 初始化 DeepSeek 客户端 ====================
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# ==================== 翻译字典与辅助函数 ====================
team_mapping = {
    'Arsenal FC': '阿森纳', 'Arsenal': '阿森纳', 'Aston Villa FC': '阿斯顿维拉', 'Aston Villa': '阿斯顿维拉',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Brighton & Hove Albion FC': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西', 'Crystal Palace FC': '水晶宫', 'Crystal Palace': '水晶宫',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿', 'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Ipswich Town FC': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester City FC': '莱斯特城', 'Leicester City': '莱斯特城',
    'Liverpool FC': '利物浦', 'Liverpool': '利物浦', 'Manchester City FC': '曼城', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United FC': '曼联', 'Manchester United': '曼联', 'Man United': '曼联',
    'Newcastle United FC': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联', 'Nottingham Forest FC': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林',
    'Southampton FC': '南安普顿', 'Southampton': '南安普顿', 'Tottenham Hotspur FC': '托特纳姆热刺', 'Tottenham Hotspur': '托特纳姆热刺',
    'West Ham United FC': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolverhampton Wanderers FC': '狼队', 'Wolverhampton Wanderers': '狼队',
    'Leeds United FC': '利兹联', 'Leeds United': '利兹联', 'Sunderland AFC': '桑德兰', 'Sunderland': '桑德兰',
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂',
    'Burnley FC': '伯恩利', 'Burnley': '伯恩利', 'Sheffield United FC': '谢菲尔德联', 'Sheffield United': '谢菲尔德联',
    'Luton Town FC': '卢顿', 'Luton Town': '卢顿', 'Watford FC': '沃特福德', 'Watford': '沃特福德', 'Norwich City FC': '诺维奇', 'Norwich City': '诺维奇'
}
def translate_team_name(name):
    if isinstance(name, str):
        return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

team_city_mapping = {
    '阿森纳': 'London', '切尔西': 'London', '托特纳姆热刺': 'London', '西汉姆联': 'London', '水晶宫': 'London', '富勒姆': 'London', '布伦特福德': 'London',
    '曼联': 'Manchester', '曼城': 'Manchester', '利物浦': 'Liverpool', '埃弗顿': 'Liverpool',
    '纽卡斯尔联': 'Newcastle', '阿斯顿维拉': 'Birmingham', '狼队': 'Wolverhampton', '布莱顿': 'Brighton',
    '诺丁汉森林': 'Nottingham', '莱斯特城': 'Leicester', '南安普顿': 'Southampton', '伯恩茅斯': 'Bournemouth', '伊普斯维奇': 'Ipswich',
    '利兹联': 'Leeds', '桑德兰': 'Sunderland', '赫尔城': 'Hull', '考文垂': 'Coventry', '伯恩利': 'Burnley', '谢菲尔德联': 'Sheffield',
    '卢顿': 'Luton', '沃特福德': 'Watford', '诺维奇': 'Norwich'
}

def get_match_weather(home_team, date_str):
    city = team_city_mapping.get(home_team, 'London')
    date_only = date_str[:10]
    try:
        match_date = datetime.strptime(date_only, '%Y-%m-%d').date()
    except:
        return "日期无效"
    today_date = datetime.now().date()
    if match_date < today_date: return "比赛已结束"
    if (match_date - today_date).days > 14: return "预报未覆盖"
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_only}&lang=zh"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            day = data['forecast']['forecastday'][0]['day']
            return {'天气': day['condition']['text'], '温度': round(day['avgtemp_c'], 1), '风速': round(day['maxwind_kph'], 1), '降雨概率': day['daily_chance_of_rain']}
    except: pass
    return "获取失败"

# ==================== 1-5. 数据获取（与上一版一致，保证运行顺畅）====================
print("⏳ 正在获取未来赛程...")
upcoming = []
try:
    now = datetime.now(); season = now.year if now.month >= 7 else now.year - 1
    resp = requests.get(f"https://api.football-data.org/v4/competitions/PL/matches?season={season}", headers={'X-Auth-Token': FOOTBALL_DATA_API_KEY}, timeout=15)
    if resp.status_code == 200:
        for m in resp.json().get('matches', []):
            if m.get('status') == 'SCHEDULED': upcoming.append({'datetime': m['utcDate'], 'home_team': m['homeTeam']['name'], 'away_team': m['awayTeam']['name']})
except: pass

if len(upcoming) == 0 and os.path.exists("en.1.json"):
    print("   ⚠️ API 数据为空，读取本地缓存文件 en.1.json...")
    try:
        with open("en.1.json", "r", encoding="utf-8") as f: data = json.load(f)
        for m in data.get('matches', []):
            score = m.get('score', {})
            if not score or 'ft' not in score: upcoming.append({'datetime': m.get('date'), 'home_team': m.get('team1'), 'away_team': m.get('team2')})
    except: pass

if len(upcoming) == 0:
    print("   ⚠️ 使用内置演示赛程（10场）...")
    upcoming = [
        {'datetime': '2026-10-17 19:30:00', 'home_team': 'Arsenal', 'away_team': 'Leeds United'},
        {'datetime': '2026-10-17 22:00:00', 'home_team': 'Manchester City', 'away_team': 'Bournemouth'},
        {'datetime': '2026-10-18 00:30:00', 'home_team': 'Chelsea', 'away_team': 'Sunderland'},
        {'datetime': '2026-10-18 03:00:00', 'home_team': 'Liverpool', 'away_team': 'Brighton & Hove Albion'},
        {'datetime': '2026-10-18 20:00:00', 'home_team': 'Manchester United', 'away_team': 'Newcastle United'},
        {'datetime': '2026-10-18 22:00:00', 'home_team': 'Aston Villa', 'away_team': 'Tottenham Hotspur'},
        {'datetime': '2026-10-19 00:30:00', 'home_team': 'Everton', 'away_team': 'Crystal Palace'},
        {'datetime': '2026-10-19 03:00:00', 'home_team': 'Fulham', 'away_team': 'West Ham United'},
        {'datetime': '2026-10-20 03:00:00', 'home_team': 'Brentford', 'away_team': 'Wolverhampton Wanderers'},
        {'datetime': '2026-10-20 03:00:00', 'home_team': 'Nottingham Forest', 'away_team': 'Leicester City'}
    ]

df_upcoming = pd.DataFrame(upcoming)
df_upcoming['datetime_parsed'] = pd.to_datetime(df_upcoming['datetime'], errors='coerce')
today = pd.Timestamp.now().normalize()
df_next_round = df_upcoming[(df_upcoming['datetime_parsed'] >= today) & (df_upcoming['datetime_parsed'] <= today + pd.Timedelta(days=10))].sort_values('datetime_parsed').reset_index(drop=True)

print("\n⏳ 正在获取多平台赔率...")
odds_records = []
try:
    resp = requests.get("https://api.the-odds-api.com/v4/sports/soccer_epl/odds", params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h', 'oddsFormat': 'decimal'}, timeout=20)
    odds_data = resp.json() if resp.status_code == 200 else []
    for match in odds_data:
        home_cn, away_cn = translate_team_name(match['home_team']), translate_team_name(match['away_team'])
        bookmaker_odds = []
        if match.get('bookmakers'):
            for bookmaker in match['bookmakers']:
                market = bookmaker['markets'][0]; outcomes = market.get('outcomes', [])
                h_odd = next((o['price'] for o in outcomes if o['name'] == match['home_team']), None)
                d_odd = next((o['price'] for o in outcomes if o['name'] == 'Draw'), None)
                a_odd = next((o['price'] for o in outcomes if o['name'] == match['away_team']), None)
                if h_odd and d_odd and a_odd:
                    total = 1/h_odd + 1/d_odd + 1/a_odd
                    bookmaker_odds.append({'h': (1/h_odd)/total, 'd': (1/d_odd)/total, 'a': (1/a_odd)/total})
        if bookmaker_odds:
            odds_records.append({'主队': home_cn, '客队': away_cn, '主胜概率': round(np.mean([b['h'] for b in bookmaker_odds]), 4), '平局概率': round(np.mean([b['d'] for b in bookmaker_odds]), 4), '客胜概率': round(np.mean([b['a'] for b in bookmaker_odds]), 4)})
except: pass
df_odds = pd.DataFrame(odds_records) if odds_records else pd.DataFrame(columns=['主队', '客队', '主胜概率', '平局概率', '客胜概率'])

# ==================== 获取伤停数据（带兜底逻辑） ====================
print("⏳ 正在获取最新伤停数据...")
injury_dict = {}  # 初始化为空字典
try:
    from espn_sports_api import Soccer
    epl = Soccer(league="epl")
    raw_injuries = epl.injuries()
    
    # 兼容字典和列表，安全提取数据
    if isinstance(raw_injuries, dict) and 'injuries' in raw_injuries:
        injury_list = raw_injuries['injuries']
    elif isinstance(raw_injuries, list):
        injury_list = raw_injuries
    else:
        injury_list = []
        
    if injury_list:
        # 如果有数据，按球队整理（具体解析逻辑依赖实际结构，这里先做防御性处理）
        for inj in injury_list:
            # 提取队名（假设结构包含 team 信息）
            team = inj.get('team', {}).get('displayName', 'Unknown') if isinstance(inj, dict) else 'Unknown'
            if team not in injury_dict:
                injury_dict[team] = []
            player = inj.get('athlete', {}).get('displayName', 'Unknown') if isinstance(inj, dict) else 'Unknown'
            status = inj.get('status', 'Unknown') if isinstance(inj, dict) else 'Unknown'
            injury_dict[team].append(f"{player}({status})")
        print(f"✅ 成功获取 {len(injury_list)} 条伤停记录。")
    else:
        print("⚠️ 当前无公开伤停数据（赛季初或休赛期正常现象）。")
except Exception as e:
    print(f"⚠️ 伤停数据获取失败（将忽略此特征）: {e}")

df_standings = pd.read_csv('epl_standings.csv')
team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
team_avg_pts_dict = {k: v/30 for k, v in dict(zip(df_standings['球队'], df_standings['积分'])).items()}

df_next_round['主队'] = df_next_round['home_team'].apply(translate_team_name)
df_next_round['客队'] = df_next_round['away_team'].apply(translate_team_name)
df_merged = pd.merge(df_next_round, df_odds, on=['主队', '客队'], how='left')
for col in ['主胜概率', '平局概率', '客胜概率']: df_merged[col] = df_merged[col].fillna(0.33)

df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

if os.path.exists('epl_v11_result_model.pkl'):
    model_result = joblib.load('epl_v11_result_model.pkl'); model_home_goals = joblib.load('epl_v11_home_goals_model.pkl'); model_away_goals = joblib.load('epl_v11_away_goals_model.pkl')
    print("✅ V11 模型加载成功！")
else:
    model_result = joblib.load('epl_v10_result_model.pkl'); model_home_goals = joblib.load('epl_v10_home_goals_model.pkl'); model_away_goals = joblib.load('epl_v10_away_goals_model.pkl')
    print("⚠️ 未找到 V11 模型，已自动回退使用 V10 模型。")

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats, last_match_date = {}, {}
for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[]}
        if t not in last_match_date: last_match_date[t] = None
    team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    last_match_date[home] = date; last_match_date[away] = date

# ==================== 6. 逐场预测 + LLM 专家点评 ====================
print("\n" + "="*70)
print("【V11 模型 + DeepSeek 专家深度分析报告】")
print("="*70)

for _, match in df_merged.iterrows():
    home_cn, away_cn = match['主队'], match['客队']
    match_time = pd.to_datetime(match['datetime']).strftime('%Y-%m-%d %H:%M')
    h, a = team_stats.get(home_cn, {'scored':[], 'conceded':[], 'points':[]}), team_stats.get(away_cn, {'scored':[], 'conceded':[], 'points':[]})
    
    h_avg_scored = np.mean(h['scored'][-5:]) if h['scored'] else league_avg_goals
    h_avg_conceded = np.mean(h['conceded'][-5:]) if h['conceded'] else league_avg_goals
    a_avg_scored = np.mean(a['scored'][-5:]) if a['scored'] else league_avg_goals
    a_avg_conceded = np.mean(a['conceded'][-5:]) if a['conceded'] else league_avg_goals
    
    h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
    a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
    h_win_rate = np.mean(h['points'][-5:]) if h['points'] else 0.5
    a_win_rate = np.mean(a['points'][-5:]) if a['points'] else 0.5
    
    feature_dict = {
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'rest_days': 7, 'opp_rest_days': 7, 'is_home': 1,
        'home_rank': team_rank_dict.get(home_cn, 15), 'away_rank': team_rank_dict.get(away_cn, 15),
        'home_avg_points': team_avg_pts_dict.get(home_cn, 1.0), 'away_avg_points': team_avg_pts_dict.get(away_cn, 1.0),
        'prob_h_odds': match['主胜概率'], 'prob_d_odds': match['平局概率'], 'prob_a_odds': match['客胜概率']
    }
    X_pred = pd.DataFrame([feature_dict])
    probs = model_result.predict_proba(X_pred)[0]
    home_xg, away_xg = max(0.1, model_home_goals.predict(X_pred)[0]), max(0.1, model_away_goals.predict(X_pred)[0])
    
    score_probs = [(f"{hg}-{ag}", poisson.pmf(hg, home_xg) * poisson.pmf(ag, away_xg)) for hg in range(6) for ag in range(6)]
    score_probs.sort(key=lambda x: x[1], reverse=True); top3 = score_probs[:3]
    weather = get_match_weather(home_cn, match_time)
    pred_result = np.argmax(probs)
    recommend = "主胜" if pred_result == 2 else ("平局" if pred_result == 1 else "客胜")
    
    # 🌟 核心升级：调用 DeepSeek 进行专家点评
        # 获取本场比赛两队的伤停情况，带兜底
        home_injuries = injury_dict.get(home_cn, ["暂无重大伤停"])
        away_injuries = injury_dict.get(away_cn, ["暂无重大伤停"])
        injury_info = f"{home_cn}伤停：{'，'.join(home_injuries)}；{away_cn}伤停：{'，'.join(away_injuries)}。"
        
        # 在构建prompt的f-string中，把 {injury_info} 放在合适的位置
        prompt = f"""你是一位精通英超的资深数据分析专家。请基于以下数据，写一段精炼、有洞察力、口语化的赛前点评（不超过150字）：
        比赛：{home_cn}（联赛排名 {team_rank_dict.get(home_cn, '未知')}） vs {away_cn}（联赛排名 {team_rank_dict.get(away_cn, '未知')}）
        近5场状态：{home_cn} 场均进 {h_avg_scored:.2f} 球，失 {h_avg_conceded:.2f} 球；{away_cn} 场均进 {a_avg_scored:.2f} 球，失 {a_avg_conceded:.2f} 球。
        天气：{weather if isinstance(weather, str) else weather['天气']}。
        市场赔率倾向：主胜 {match['主胜概率']*100:.1f}%，平局 {match['平局概率']*100:.1f}%，客胜 {match['客胜概率']*100:.1f}%。
        V11模型预测：主胜 {probs[2]*100:.1f}%，平局 {probs[1]*100:.1f}%，客胜 {probs[0]*100:.1f}%。
        {injury_info}
        请给出你的综合分析，并以“推荐关注：XXX”结尾。"""
  
    try:
        response = llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        expert_comment = response.choices[0].message.content.strip()
    except Exception as e:
        expert_comment = "【AI深度分析暂时不可用】"
    
    # 打印报告
    print(f"\n{'='*60}")
    print(f"【比赛时间】{match_time}")
    print(f"【对阵双方】{home_cn} vs {away_cn}")
    print(f"{'='*60}")
    print(f"\n📊 球队数据对比：")
    print(f"   {home_cn}：排名 {team_rank_dict.get(home_cn, 15)} | 场均积分 {team_avg_pts_dict.get(home_cn, 1.0):.2f} | 近5场场均进球 {h_avg_scored:.2f} | 近5场场均失球 {h_avg_conceded:.2f}")
    print(f"   {away_cn}：排名 {team_rank_dict.get(away_cn, 15)} | 场均积分 {team_avg_pts_dict.get(away_cn, 1.0):.2f} | 近5场场均进球 {a_avg_scored:.2f} | 近5场场均失球 {a_avg_conceded:.2f}")
    if isinstance(weather, dict): print(f"\n🌤️ 比赛日天气：{weather['天气']} | 温度 {weather['温度']}°C | 风速 {weather['风速']} km/h | 降雨概率 {weather['降雨概率']}%")
    else: print(f"\n🌤️ 比赛日天气：{weather}")
    print(f"\n📈 赔率市场分析：\n   市场平均：主胜 {match['主胜概率']*100:.1f}% | 平局 {match['平局概率']*100:.1f}% | 客胜 {match['客胜概率']*100:.1f}%")
    print(f"\n🎯 V11模型综合预测：\n   胜平负：主胜 {probs[2]*100:.1f}% | 平局 {probs[1]*100:.1f}% | 客胜 {probs[0]*100:.1f}%")
    print(f"   进球期望：主队 {home_xg:.2f} 球 | 客队 {away_xg:.2f} 球")
    print(f"   最可能比分：{top3[0][0]} ({top3[0][1]*100:.1f}%) | {top3[1][0]} ({top3[1][1]*100:.1f}%) | {top3[2][0]} ({top3[2][1]*100:.1f}%)")
    print(f"\n🧠 DeepSeek 专家深度点评：")
    print(f"   {expert_comment}")
        # 🌟 新增：价值投注计算
    print(f"\n📈 价值投注分析：")
    # 市场隐含概率
    market_h = match['主胜概率']
    market_d = match['平局概率']
    market_a = match['客胜概率']
    
    # V11模型概率
    model_h = probs[2]
    model_d = probs[1]
    model_a = probs[0]
    
    # 寻找模型认为概率高于市场概率的机会
    value_home = model_h - market_h
    value_draw = model_d - market_d
    value_away = model_a - market_a
    
    if value_home > 0.05:
        print(f"   🌟 发现主胜价值：模型认为 {model_h*100:.1f}% > 市场 {market_h*100:.1f}%（差额 {value_home*100:.1f}%）")
    elif value_draw > 0.05:
        print(f"   🌟 发现平局价值：模型认为 {model_d*100:.1f}% > 市场 {market_d*100:.1f}%（差额 {value_draw*100:.1f}%）")
    elif value_away > 0.05:
        print(f"   🌟 发现客胜价值：模型认为 {model_a*100:.1f}% > 市场 {market_a*100:.1f}%（差额 {value_away*100:.1f}%）")
    else:
        print(f"   ⚪ 市场定价合理，未发现明显的价值机会。")
    
    print(f"\n💡 综合推荐：{recommend}")
    print(f"{'='*60}")
    print(f"{'='*60}")

print("\n" + "="*70)
print("✅ 全自动预测完成！报告已生成。")
print("="*70)


# In[ ]:




