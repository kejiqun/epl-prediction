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

def send_email(subject, content, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    message = MIMEText(content, 'plain', 'utf-8')
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

# 字典保持不变...
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
    if match_date < today_date: return "比赛已结束"
    if (match_date - today_date).days > 14: return "预报未覆盖"
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

# ==================== 1. 使用 ESPN 官方接口获取真实赛程 ====================
print("⏳ 正在从 ESPN 官方接口获取未来赛程...")
upcoming = []
today = datetime.now()
# 抓取未来 10 天的赛程
for i in range(10):
    date_str = (today + timedelta(days=i)).strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={date_str}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for event in data.get('events', []):
                # 只抓取未开始的比赛
                if event['status']['type']['state'] == 'pre':
                    competitions = event.get('competitions', [])
                    if competitions:
                        competitors = competitions[0].get('competitors', [])
                        home_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'home'), None)
                        away_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'away'), None)
                        
                        if home_team and away_team:
                            upcoming.append({
                                'datetime': event['date'], # ISO 8601 格式，包含时间和时区
                                'home_team': home_team,
                                'away_team': away_team
                            })
    except Exception as e:
        continue

if len(upcoming) == 0:
    print("❌ ESPN 未能获取到未来赛程，系统停止运行。")
    exit()

print(f"✅ ESPN 成功返回了 {len(upcoming)} 场未来比赛。")

df_upcoming = pd.DataFrame(upcoming)
# 转换时间为本地时间（北京时间）
df_upcoming['datetime_parsed'] = pd.to_datetime(df_upcoming['datetime']).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
today_ts = pd.Timestamp.now().normalize()
df_next_round = df_upcoming[(df_upcoming['datetime_parsed'] >= today_ts) & (df_upcoming['datetime_parsed'] <= today_ts + pd.Timedelta(days=10))].sort_values('datetime_parsed').reset_index(drop=True)

if len(df_next_round) == 0:
    print("❌ 未来 10 天内没有比赛，系统停止运行。")
    exit()

# ==================== 2. 获取赔率 ====================
print("\n⏳ 正在获取赔率...")
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

# ==================== 3. 加载积分榜与 FPL 伤停 ====================
print("⏳ 正在加载积分榜数据...")
try:
    df_standings = pd.read_csv('epl_standings.csv')
    team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
    team_avg_pts_dict = {k: v/30 for k, v in dict(zip(df_standings['球队'], df_standings['积分'])).items()}
except Exception as e:
    print(f"⚠️ 读取积分榜失败: {e}")
    team_rank_dict, team_avg_pts_dict = {}, {}

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
        print(f"✅ 成功从 FPL 获取伤停数据。")
except Exception as e:
    print(f"⚠️ FPL 伤停获取失败: {e}")

# ==================== 4. 加载模型与特征 ====================
print("⏳ 正在加载模型...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

model_result = joblib.load('epl_v11_result_model.pkl') if os.path.exists('epl_v11_result_model.pkl') else joblib.load('epl_v10_result_model.pkl')
model_home_goals = joblib.load('epl_v11_home_goals_model.pkl') if os.path.exists('epl_v11_home_goals_model.pkl') else joblib.load('epl_v10_home_goals_model.pkl')
model_away_goals = joblib.load('epl_v11_away_goals_model.pkl') if os.path.exists('epl_v11_away_goals_model.pkl') else joblib.load('epl_v10_away_goals_model.pkl')

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats = {}
for idx, row in df_hist.iterrows():
    home, away = row['home_team_cn'], row['away_team_cn']
    for t in [home, away]:
        if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[]}
    team_stats[home]['scored'].append(row['home_goals'])
    team_stats[home]['conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    team_stats[away]['scored'].append(row['away_goals'])
    team_stats[away]['conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)

# ==================== 5. 预测循环 ====================
df_next_round['主队'] = df_next_round['home_team'].apply(translate_team_name)
df_next_round['客队'] = df_next_round['away_team'].apply(translate_team_name)
df_merged = pd.merge(df_next_round, df_odds, on=['主队', '客队'], how='left')
for col in ['主胜概率', '平局概率', '客胜概率']:
    if col not in df_merged.columns: df_merged[col] = 0.33
    else: df_merged[col] = df_merged[col].fillna(0.33)

report_content = "【英超全自动预测系统 V11 - 专家深度分析报告】\n\n"

for _, match in df_merged.iterrows():
    home_cn, away_cn = match['主队'], match['客队']
    match_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
    
    h = team_stats.get(home_cn, {'scored':[], 'conceded':[], 'points':[]})
    a = team_stats.get(away_cn, {'scored':[], 'conceded':[], 'points':[]})
    
    h_avg_scored = np.mean(h['scored'][-5:]) if h['scored'] else league_avg_goals
    h_avg_conceded = np.mean(h['conceded'][-5:]) if h['conceded'] else league_avg_goals
    a_avg_scored = np.mean(a['scored'][-5:]) if a['scored'] else league_avg_goals
    a_avg_conceded = np.mean(a['conceded'][-5:]) if a['conceded'] else league_avg_goals
    
    h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
    a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
    h_win_rate = np.mean(h['points'][-5:]) if h['points'] else 0.5
    a_win_rate = np.mean(a['points'][-5:]) if a['points'] else 0.5
    
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
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False
        )
        expert_comment = response.choices[0].message.content.strip()
    except:
        expert_comment = "【AI深度分析暂时不可用】"
    
    report_line = f"\n{'='*60}\n"
    report_line += f"【比赛时间】{match_time}\n【对阵双方】{home_cn} vs {away_cn}\n{'='*60}\n"
    report_line += f"\n📊 球队数据对比：\n   {home_cn}：排名 {h_rank} | 近5场场均进球 {h_avg_scored:.2f} | 失球 {h_avg_conceded:.2f}\n   {away_cn}：排名 {a_rank} | 近5场场均进球 {a_avg_scored:.2f} | 失球 {a_avg_conceded:.2f}\n"
    if isinstance(weather, dict): report_line += f"\n🌤️ 比赛日天气：{weather['天气']} | 温度 {weather['温度']}°C\n"
    else: report_line += f"\n🌤️ 比赛日天气：{weather}\n"
    report_line += f"\n📈 赔率市场分析：市场平均：主胜 {match['主胜概率']*100:.1f}% | 平局 {match['平局概率']*100:.1f}% | 客胜 {match['客胜概率']*100:.1f}%\n"
    report_line += f"\n📈 价值投注分析：\n{value_msg}"
    report_line += f"\n🎯 V11模型综合预测：主胜 {probs[2]*100:.1f}% | 平局 {probs[1]*100:.1f}% | 客胜 {probs[0]*100:.1f}%\n   最可能比分：{top3[0][0]} | {top3[1][0]} | {top3[2][0]}\n"
    report_line += f"\n🧠 DeepSeek 专家深度点评：\n   {expert_comment}\n"
    report_line += f"\n💡 综合推荐：{recommend}\n{'='*60}\n"

    print(report_line)
    report_content += report_line

send_email("本周末英超真实赛程预测报告", report_content)