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
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from espn_sports_api import Soccer

warnings.filterwarnings('ignore')
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.width', 1000)

# ==================== 密钥配置 ====================
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# ==================== 邮件发送函数（修复 550 错误） ====================
def send_email(subject, content, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("⚠️ 未配置 EMAIL_SENDER 或 EMAIL_PASSWORD，跳过邮件发送。")
        return
    message = MIMEText(content, 'plain', 'utf-8')
    # 🌟 核心修复：直接使用原始邮箱地址，去掉 Header 编码
    message['From'] = EMAIL_SENDER
    message['To'] = receiver
    message['Subject'] = Header(subject, 'utf-8')
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], message.as_string())
        print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# ==================== 翻译字典 ====================
team_mapping = {
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
    'Southampton FC': '南安普顿', 'Southampton': '南安普顿', 'Tottenham Hotspur FC': '托特纳姆热刺', 'Tottenham Hotspur': '托特纳姆热刺', 'Tottenham': '托特纳姆热刺',
    'West Ham United FC': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolverhampton Wanderers FC': '狼队', 'Wolverhampton Wanderers': '狼队', 'Wolves': '狼队',
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
    '阿森纳': 'London', '切尔西': 'London', '托特纳姆热刺': 'London', '西汉姆联': 'London',
    '水晶宫': 'London', '富勒姆': 'London', '布伦特福德': 'London', '曼联': 'Manchester', '曼城': 'Manchester',
    '利物浦': 'Liverpool', '埃弗顿': 'Liverpool', '纽卡斯尔联': 'Newcastle', '阿斯顿维拉': 'Birmingham',
    '狼队': 'Wolverhampton', '布莱顿': 'Brighton', '诺丁汉森林': 'Nottingham', '莱斯特城': 'Leicester',
    '南安普顿': 'Southampton', '伯恩茅斯': 'Bournemouth', '伊普斯维奇': 'Ipswich', '利兹联': 'Leeds',
    '桑德兰': 'Sunderland', '赫尔城': 'Hull', '考文垂': 'Coventry', '伯恩利': 'Burnley',
    '谢菲尔德联': 'Sheffield', '卢顿': 'Luton', '沃特福德': 'Watford', '诺维奇': 'Norwich'
}

def get_match_weather(home_team, date_str):
    city = team_city_mapping.get(home_team, 'London')
    date_only = date_str[:10]
    try:
        match_date = datetime.strptime(date_only, '%Y-%m-%d').date()
    except:
        return "日期无效"
    today_date = datetime.now().date()
    if match_date < today_date:
        return "比赛已结束"
    if (match_date - today_date).days > 14:
        return "预报未覆盖"
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_only}&lang=zh"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            day = data['forecast']['forecastday'][0]['day']
            return {'天气': day['condition']['text'], '温度': round(day['avgtemp_c'], 1), '风速': round(day['maxwind_kph'], 1), '降雨概率': day['daily_chance_of_rain']}
    except:
        pass
    return "获取失败"

# ==================== 1. 使用 ESPN 获取赛程与积分榜 ====================
print("⏳ 正在使用 ESPN 获取未来赛程与实时积分榜...")
upcoming = []
team_rank_dict = {}
team_avg_pts_dict = {}

try:
    epl = Soccer(league="epl")
    
    # 1. 获取积分榜
    try:
        standings = epl.standings()
        if standings and 'children' in standings and len(standings['children']) > 0:
            entries = standings['children'][0]['standings']['entries']
            for entry in entries:
                team_name = translate_team_name(entry['team']['name'])
                # 查找排名和积分
                rank = next((int(stat['value']) for stat in entry['stats'] if stat['name'] == 'rank'), 15)
                points = next((int(stat['value']) for stat in entry['stats'] if stat['name'] == 'points'), 0)
                games = next((int(stat['value']) for stat in entry['stats'] if stat['name'] == 'gamesPlayed'), 1)
                
                team_rank_dict[team_name] = rank
                team_avg_pts_dict[team_name] = points / max(1, games)
            print(f"✅ 成功从 ESPN 获取实时积分榜！")
    except Exception as e:
        print(f"⚠️ ESPN 获取积分榜失败: {e}")
    
    # 2. 获取未来赛程 (使用 ESPN 的日期范围)
    today = datetime.now().date()
    end_date = today + timedelta(days=10)
    try:
        # ESPN 库可能提供 date_range 或者直接获取赛程
        matches = epl.matches(date_from=today.strftime('%Y-%m-%d'), date_to=end_date.strftime('%Y-%m-%d'))
        if matches:
            for m in matches:
                upcoming.append({
                    'datetime': m.get('date'),
                    'home_team': m.get('homeTeam', {}).get('name'),
                    'away_team': m.get('awayTeam', {}).get('name')
                })
        print(f"✅ ESPN 返回了 {len(upcoming)} 场未来比赛。")
    except Exception as e:
        print(f"⚠️ ESPN 获取赛程失败: {e}")
except Exception as e:
    print(f"⚠️ 初始化 ESPN 失败: {e}")

if len(upcoming) == 0:
    print("   ⚠️ 使用内置演示赛程（10场，带准确时间）...")
    upcoming = [
        {'datetime': '2026-10-17 19:30:00', 'home_team': 'Arsenal', 'away_team': 'Leeds United'},
        {'datetime': '2026-10-17 22:00:00', 'home_team': 'Manchester City', 'away_team': 'Bournemouth'},
        {'datetime': '2026-10-18 00:30:00', 'home_team': 'Chelsea', 'away_team': 'Sunderland'},
        {'datetime': '2026-10-18 03:00:00', 'home_team': 'Liverpool', 'away_team': 'Brighton & Hove Albion'},
        {'datetime': '2026-10-18 20:00:00', 'home_team': 'Manchester United', 'away_team': 'Newcastle United'}
    ]

df_upcoming = pd.DataFrame(upcoming)
df_upcoming['datetime_parsed'] = pd.to_datetime(df_upcoming['datetime'], errors='coerce')
today_ts = pd.Timestamp.now().normalize()
df_next_round = df_upcoming[(df_upcoming['datetime_parsed'] >= today_ts) & (df_upcoming['datetime_parsed'] <= today_ts + pd.Timedelta(days=10))].sort_values('datetime_parsed').reset_index(drop=True)

# ==================== 2. 获取赔率 ====================
print("\n⏳ 正在获取多平台赔率并进行伪数据筛查...")
odds_records = []
try:
    resp = requests.get("https://api.the-odds-api.com/v4/sports/soccer_epl/odds", params={'apiKey': ODDS_API_KEY, 'regions': 'uk', 'markets': 'h2h', 'oddsFormat': 'decimal'}, timeout=20)
    odds_data = resp.json() if resp.status_code == 200 else []
    for match in odds_data:
        home_cn = translate_team_name(match['home_team'])
        away_cn = translate_team_name(match['away_team'])
        bookmaker_odds = []
        if match.get('bookmakers'):
            for bookmaker in match['bookmakers']:
                market = bookmaker['markets'][0]
                outcomes = market.get('outcomes', [])
                h_odd = next((o['price'] for o in outcomes if o['name'] == match['home_team']), None)
                d_odd = next((o['price'] for o in outcomes if o['name'] == 'Draw'), None)
                a_odd = next((o['price'] for o in outcomes if o['name'] == match['away_team']), None)
                if h_odd and d_odd and a_odd:
                    total = 1/h_odd + 1/d_odd + 1/a_odd
                    bookmaker_odds.append({'h': (1/h_odd)/total, 'd': (1/d_odd)/total, 'a': (1/a_odd)/total})
        if bookmaker_odds:
            probs_h = [b['h'] for b in bookmaker_odds]
            probs_d = [b['d'] for b in bookmaker_odds]
            probs_a = [b['a'] for b in bookmaker_odds]
            valid_h = [p for p in probs_h if abs(p - np.mean(probs_h)) / np.mean(probs_h) < 0.2]
            valid_d = [p for p in probs_d if abs(p - np.mean(probs_d)) / np.mean(probs_d) < 0.2]
            valid_a = [p for p in probs_a if abs(p - np.mean(probs_a)) / np.mean(probs_a) < 0.2]
            if valid_h and valid_d and valid_a:
                odds_records.append({'主队': home_cn, '客队': away_cn, '主胜概率': round(np.mean(valid_h), 4), '平局概率': round(np.mean(valid_d), 4), '客胜概率': round(np.mean(valid_a), 4)})
except:
    pass
df_odds = pd.DataFrame(odds_records) if odds_records else pd.DataFrame(columns=['主队', '客队', '主胜概率', '平局概率', '客胜概率'])

# ==================== 3. 获取 FPL 伤停数据 ====================
print("⏳ 正在从 FPL 官方 API 自动获取伤停数据...")
injury_dict = {}
try:
    fpl_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    fpl_resp = requests.get(fpl_url, timeout=15)
    if fpl_resp.status_code == 200:
        fpl_data = fpl_resp.json()
        teams_map = {t['id']: t['name'] for t in fpl_data['teams']}
        for element in fpl_data['elements']:
            if element['status'] in ['d', 'i', 's', 'u']:
                team_name_cn = translate_team_name(teams_map.get(element['team']))
                player_name = element['web_name']
                news = element['news']
                status_cn = {"d": "出战成疑", "i": "受伤", "s": "停赛", "u": "不可用"}.get(element['status'], "未知")
                if team_name_cn not in injury_dict: injury_dict[team_name_cn] = []
                if news: injury_dict[team_name_cn].append(f"{player_name}({status_cn}: {news})")
                else: injury_dict[team_name_cn].append(f"{player_name}({status_cn})")
        print(f"✅ 成功从 FPL 获取伤停数据，覆盖 {len(injury_dict)} 支球队。")
except Exception as e:
    print(f"⚠️ FPL 伤停数据获取失败: {e}")

# ==================== 4. 加载模型与计算特征 ====================
print("⏳ 正在加载模型...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

if os.path.exists('epl_v11_result_model.pkl'):
    model_result = joblib.load('epl_v11_result_model.pkl')
    model_home_goals = joblib.load('epl_v11_home_goals_model.pkl')
    model_away_goals = joblib.load('epl_v11_away_goals_model.pkl')
    print("✅ V11 模型加载成功！")
else:
    model_result = joblib.load('epl_v10_result_model.pkl')
    model_home_goals = joblib.load('epl_v10_home_goals_model.pkl')
    model_away_goals = joblib.load('epl_v10_away_goals_model.pkl')
    print("⚠️ 未找到 V11 模型，已自动回退使用 V10 模型。")

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats, last_match_date = {}, {}
for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[]}
        if t not in last_match_date: last_match_date[t] = None
    team_stats[home]['scored'].append(row['home_goals'])
    team_stats[home]['conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    team_stats[away]['scored'].append(row['away_goals'])
    team_stats[away]['conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    last_match_date[home] = date
    last_match_date[away] = date

# ==================== 5. 合并赛程与赔率 ====================
df_next_round['主队'] = df_next_round['home_team'].apply(translate_team_name)
df_next_round['客队'] = df_next_round['away_team'].apply(translate_team_name)
df_merged = pd.merge(df_next_round, df_odds, on=['主队', '客队'], how='left')
for col in ['主胜概率', '平局概率', '客胜概率']:
    if col not in df_merged.columns: df_merged[col] = 0.33
    else: df_merged[col] = df_merged[col].fillna(0.33)

# ==================== 6. 逐场预测 + LLM 专家点评 ====================
report_content = "【英超全自动预测系统 V11 - 专家深度分析报告】\n\n"

for _, match in df_merged.iterrows():
    home_cn, away_cn = match['主队'], match['客队']
    
    # 优化时间显示逻辑：如果直接有 datetime，就直接用
    try:
        dt = pd.to_datetime(match['datetime'])
        if dt.hour == 0 and dt.minute == 0:
            match_time = dt.strftime('%Y-%m-%d (时间待定)')
        else:
            match_time = dt.strftime('%Y-%m-%d %H:%M')
    except:
        match_time = str(match['datetime'])[:16]

    h, a = team_stats.get(home_cn, {'scored':[], 'conceded':[], 'points':[]}), team_stats.get(away_cn, {'scored':[], 'conceded':[], 'points':[]})
    
    h_avg_scored = np.mean(h['scored'][-5:]) if h['scored'] else league_avg_goals
    h_avg_conceded = np.mean(h['conceded'][-5:]) if h['conceded'] else league_avg_goals
    a_avg_scored = np.mean(a['scored'][-5:]) if a['scored'] else league_avg_goals
    a_avg_conceded = np.mean(a['conceded'][-5:]) if a['conceded'] else league_avg_goals
    
    h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
    a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
    h_win_rate = np.mean(h['points'][-5:]) if h['points'] else 0.5
    a_win_rate = np.mean(a['points'][-5:]) if a['points'] else 0.5
    
    # 使用实时积分榜的排名
    h_rank = team_rank_dict.get(home_cn, 15)
    a_rank = team_rank_dict.get(away_cn, 15)
    h_avg_pts = team_avg_pts_dict.get(home_cn, 1.0)
    a_avg_pts = team_avg_pts_dict.get(away_cn, 1.0)

    feature_dict = {
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'rest_days': 7, 'opp_rest_days': 7, 'is_home': 1,
        'home_rank': h_rank, 'away_rank': a_rank,
        'home_avg_points': h_avg_pts, 'away_avg_points': a_avg_pts,
        'prob_h_odds': match['主胜概率'], 'prob_d_odds': match['平局概率'], 'prob_a_odds': match['客胜概率']
    }
    X_pred = pd.DataFrame([feature_dict])
    probs = model_result.predict_proba(X_pred)[0]
    home_xg, away_xg = max(0.1, model_home_goals.predict(X_pred)[0]), max(0.1, model_away_goals.predict(X_pred)[0])
    
    score_probs = [(f"{hg}-{ag}", poisson.pmf(hg, home_xg) * poisson.pmf(ag, away_xg)) for hg in range(6) for ag in range(6)]
    score_probs.sort(key=lambda x: x[1], reverse=True)
    top3 = score_probs[:3]
    weather = get_match_weather(home_cn, match_time)
    pred_result = np.argmax(probs)
    recommend = "主胜" if pred_result == 2 else ("平局" if pred_result == 1 else "客胜")
    
    market_h, market_d, market_a = match['主胜概率'], match['平局概率'], match['客胜概率']
    model_h, model_d, model_a = probs[2], probs[1], probs[0]
    value_home, value_draw, value_away = model_h - market_h, model_d - market_d, model_a - market_a
    value_msg = ""
    if value_home > 0.05: value_msg += f"   🌟 发现主胜价值：模型 {model_h*100:.1f}% > 市场 {market_h*100:.1f}% (差额 +{value_home*100:.1f}%)\n"
    elif value_draw > 0.05: value_msg += f"   🌟 发现平局价值：模型 {model_d*100:.1f}% > 市场 {market_d*100:.1f}% (差额 +{value_draw*100:.1f}%)\n"
    elif value_away > 0.05: value_msg += f"   🌟 发现客胜价值：模型 {model_a*100:.1f}% > 市场 {market_a*100:.1f}% (差额 +{value_away*100:.1f}%)\n"
    else: value_msg += "   ⚪ 市场定价合理，未发现明显的价值机会。\n"
    
    home_injuries = injury_dict.get(home_cn, ["暂无重大伤停"])
    away_injuries = injury_dict.get(away_cn, ["暂无重大伤停"])
    injury_info = f"{home_cn}伤停：{'，'.join(home_injuries)}；{away_cn}伤停：{'，'.join(away_injuries)}。"
    
    prompt = f"""你是一位精通英超的资深数据分析专家。请基于以下数据，写一段精炼、有洞察力、口语化的赛前点评（不超过150字）：
    比赛：{home_cn}（排名 {h_rank}） vs {away_cn}（排名 {a_rank}）
    近5场状态：{home_cn} 场均进 {h_avg_scored:.2f} 球，失 {h_avg_conceded:.2f} 球；{away_cn} 场均进 {a_avg_scored:.2f} 球，失 {a_avg_conceded:.2f} 球。
    天气：{weather if isinstance(weather, str) else weather['天气']}。
    市场赔率倾向：主胜 {match['主胜概率']*100:.1f}%，平局 {match['平局概率']*100:.1f}%，客胜 {match['客胜概率']*100:.1f}%。
    V11模型预测：主胜 {probs[2]*100:.1f}%，平局 {probs[1]*100:.1f}%，客胜 {probs[0]*100:.1f}%。
    **实时伤停情报：**
    {injury_info}
    请综合以上所有信息给出你的分析，并以“推荐关注：XXX”结尾。"""
    
    try:
        response = llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        expert_comment = response.choices[0].message.content.strip()
    except Exception as e:
        expert_comment = "【AI深度分析暂时不可用】"
    
    report_line = f"\n{'='*60}\n"
    report_line += f"【比赛时间】{match_time}\n"
    report_line += f"【对阵双方】{home_cn} vs {away_cn}\n"
    report_line += f"{'='*60}\n"
    report_line += f"\n📊 球队数据对比：\n"
    report_line += f"   {home_cn}：排名 {h_rank} | 场均积分 {h_avg_pts:.2f} | 近5场场均进球 {h_avg_scored:.2f} | 近5场场均失球 {h_avg_conceded:.2f}\n"
    report_line += f"   {away_cn}：排名 {a_rank} | 场均积分 {a_avg_pts:.2f} | 近5场场均进球 {a_avg_scored:.2f} | 近5场场均失球 {a_avg_conceded:.2f}\n"
    if isinstance(weather, dict):
        report_line += f"\n🌤️ 比赛日天气：{weather['天气']} | 温度 {weather['温度']}°C | 风速 {weather['风速']} km/h | 降雨概率 {weather['降雨概率']}%\n"
    else:
        report_line += f"\n🌤️ 比赛日天气：{weather}\n"
    report_line += f"\n📈 赔率市场分析（已剔除异常值）：\n"
    report_line += f"   市场平均：主胜 {match['主胜概率']*100:.1f}% | 平局 {match['平局概率']*100:.1f}% | 客胜 {match['客胜概率']*100:.1f}%\n"
    report_line += f"\n📈 价值投注分析：\n{value_msg}"
    report_line += f"\n🎯 V11模型综合预测：\n"
    report_line += f"   胜平负：主胜 {probs[2]*100:.1f}% | 平局 {probs[1]*100:.1f}% | 客胜 {probs[0]*100:.1f}%\n"
    report_line += f"   进球期望：主队 {home_xg:.2f} 球 | 客队 {away_xg:.2f} 球\n"
    report_line += f"   最可能比分：{top3[0][0]} ({top3[0][1]*100:.1f}%) | {top3[1][0]} ({top3[1][1]*100:.1f}%) | {top3[2][0]} ({top3[2][1]*100:.1f}%)\n"
    report_line += f"\n🧠 DeepSeek 专家深度点评：\n   {expert_comment}\n"
    report_line += f"\n💡 综合推荐：{recommend}\n"
    report_line += f"{'='*60}\n"

    print(report_line)
    report_content += report_line

print("\n" + "="*70)
print("✅ 全自动预测完成！准备发送邮件...")
print("="*70)

send_email("本周末英超预测报告及价值分析", report_content)