import pandas as pd
import numpy as np
import requests
import joblib
import os
import json
import io
from scipy.stats import poisson
from datetime import datetime, timedelta
import warnings
from openai import OpenAI
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.neural_network import MLPRegressor

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

# ==================== 密钥配置 ====================
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def send_rich_email(subject, html_content, img_buffers, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    msg = MIMEMultipart('related')
    msg['From'] = EMAIL_SENDER; msg['To'] = receiver; msg['Subject'] = Header(subject, 'utf-8')
    msg_alt = MIMEMultipart('alternative'); msg.attach(msg_alt)
    msg_alt.attach(MIMEText(html_content, 'html', 'utf-8'))
    for i, buf in enumerate(img_buffers):
        img = MIMEImage(buf.getvalue()); img.add_header('Content-ID', f'<chart_{i}>'); msg.attach(img)
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
        print("✅ 图文邮件发送成功！")
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

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
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂'
}

def translate_team_name(name):
    if isinstance(name, str): return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

team_city_mapping = {
    '阿森纳': 'London', '切尔西': 'London', '托特纳姆热刺': 'London', '西汉姆联': 'London', '水晶宫': 'London', '富勒姆': 'London', '布伦特福德': 'London',
    '曼联': 'Manchester', '曼城': 'Manchester', '利物浦': 'Liverpool', '埃弗顿': 'Liverpool', '纽卡斯尔联': 'Newcastle', '阿斯顿维拉': 'Birmingham',
    '狼队': 'Wolverhampton', '布莱顿': 'Brighton', '诺丁汉森林': 'Nottingham', '莱斯特城': 'Leicester', '南安普顿': 'Southampton', '伯恩茅斯': 'Bournemouth',
    '伊普斯维奇': 'Ipswich', '利兹联': 'Leeds', '桑德兰': 'Sunderland', '赫尔城': 'Hull', '考文垂': 'Coventry', '伯恩利': 'Burnley', '谢菲尔德联': 'Sheffield',
    '卢顿': 'Luton', '沃特福德': 'Watford', '诺维奇': 'Norwich'
}

def get_match_weather(home_team, date_str):
    city = team_city_mapping.get(home_team, 'London')
    date_only = date_str[:10]
    try: match_date = datetime.strptime(date_only, '%Y-%m-%d').date()
    except: return "日期无效"
    today_date = datetime.now().date()
    if match_date < today_date: return "比赛已结束"
    if (match_date - today_date).days > 14: return "预报未覆盖"
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_only}&lang=zh"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            day = data['forecast']['forecastday'][0]['day']
            return {'天气': day['condition']['text'], '温度': round(day['avgtemp_c'], 1)}
    except: pass
    return "获取失败"

print("⏳ 正在从 ESPN 获取未来赛程...")
upcoming = []
today = datetime.now()
for i in range(10):
    date_str = (today + timedelta(days=i)).strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={date_str}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for event in data.get('events', []):
                if event['status']['type']['state'] == 'pre':
                    competitions = event.get('competitions', [])
                    if competitions:
                        competitors = competitions[0].get('competitors', [])
                        home_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'home'), None)
                        away_team = next((c['team']['name'] for c in competitors if c['homeAway'] == 'away'), None)
                        if home_team and away_team:
                            upcoming.append({'datetime': event['date'], 'home_team': home_team, 'away_team': away_team})
    except: continue

if len(upcoming) == 0:
    print("❌ ESPN 未能获取到赛程。")
    exit()

df_upcoming = pd.DataFrame(upcoming)
df_upcoming['datetime_parsed'] = pd.to_datetime(df_upcoming['datetime']).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
today_ts = pd.Timestamp.now().normalize()
df_next_round = df_upcoming[(df_upcoming['datetime_parsed'] >= today_ts) & (df_upcoming['datetime_parsed'] <= today_ts + pd.Timedelta(days=10))].sort_values('datetime_parsed').reset_index(drop=True)

print("\n⏳ 正在获取赔率并监控资金异动...")
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
                    bookmaker_odds.append({'h': (1/h_odd)/total, 'd': (1/d_odd)/total, 'a': (1/a_odd)/total, 'h_odd': h_odd, 'd_odd': d_odd, 'a_odd': a_odd})
        if bookmaker_odds:
            probs_h = [b['h'] for b in bookmaker_odds]; probs_d = [b['d'] for b in bookmaker_odds]; probs_a = [b['a'] for b in bookmaker_odds]
            valid_h = [p for p in probs_h if abs(p - np.mean(probs_h)) / np.mean(probs_h) < 0.2]
            valid_d = [p for p in probs_d if abs(p - np.mean(probs_d)) / np.mean(probs_d) < 0.2]
            valid_a = [p for p in probs_a if abs(p - np.mean(probs_a)) / np.mean(probs_a) < 0.2]
            if valid_h and valid_d and valid_a:
                ref_odds = bookmaker_odds[0]
                odds_records.append({
                    '主队': home_cn, '客队': away_cn, 
                    '主胜概率': round(np.mean(valid_h), 4), '平局概率': round(np.mean(valid_d), 4), '客胜概率': round(np.mean(valid_a), 4),
                    '真实赔率主胜': ref_odds['h_odd'], '真实赔率平局': ref_odds['d_odd'], '真实赔率客胜': ref_odds['a_odd']
                })
except: pass
df_odds = pd.DataFrame(odds_records) if odds_records else pd.DataFrame(columns=['主队', '客队', '主胜概率', '平局概率', '客胜概率', '真实赔率主胜', '真实赔率平局', '真实赔率客胜'])

try:
    df_standings = pd.read_csv('epl_standings.csv')
    team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
except: team_rank_dict = {}

injury_dict = {}
try:
    fpl_resp = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15)
    if fpl_resp.status_code == 200:
        fpl_data = fpl_resp.json()
        teams_map = {t['id']: t['name'] for t in fpl_data['teams']}
        for element in fpl_data['elements']:
            if element['status'] in ['d', 'i', 's', 'u']:
                team_name_cn = translate_team_name(teams_map.get(element['team']))
                player_name = element['web_name']; news = element['news']
                status_cn = {"d": "出战成疑", "i": "受伤", "s": "停赛", "u": "不可用"}.get(element['status'], "未知")
                if team_name_cn not in injury_dict: injury_dict[team_name_cn] = []
                injury_dict[team_name_cn].append(f"{player_name}({status_cn}: {news})" if news else f"{player_name}({status_cn})")
except: pass

print("⏳ 正在加载 V15 模型与神经网络集成模型...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

model_home_goals = joblib.load('epl_v15_home_goals_model.pkl')
model_away_goals = joblib.load('epl_v15_away_goals_model.pkl')

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats = {}; last_match_date = {}; h2h_stats = {}

for idx, row in df_hist.iterrows():
    home, away, match_date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]}
        if t not in last_match_date: last_match_date[t] = None
    
    if (home, away) not in h2h_stats: h2h_stats[(home, away)] = []
    
    team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
    team_stats[home]['home_scored'].append(row['home_goals']); team_stats[home]['home_conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    
    team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
    team_stats[away]['away_scored'].append(row['away_goals']); team_stats[away]['away_conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    
    h2h_stats[(home, away)].append((row['home_goals'], row['away_goals']))
    last_match_date[home] = match_date; last_match_date[away] = match_date

knowledge_base = ""
if os.path.exists('knowledge.txt'):
    with open('knowledge.txt', 'r', encoding='utf-8') as f: knowledge_base = f.read()

df_next_round['主队'] = df_next_round['home_team'].apply(translate_team_name)
df_next_round['客队'] = df_next_round['away_team'].apply(translate_team_name)
df_merged = pd.merge(df_next_round, df_odds, on=['主队', '客队'], how='left')
for col in ['主胜概率', '平局概率', '客胜概率']:
    if col not in df_merged.columns: df_merged[col] = 0.33
    else: df_merged[col] = df_merged[col].fillna(0.33)

html_report = "<html><body><h2>⚽ 英超全自动预测系统 V22 - 图文战报</h2>"
prediction_logs = []
img_buffers = []
odds_history_list = []

for idx, (_, match) in enumerate(df_merged.iterrows()):
    home_cn, away_cn = match['主队'], match['客队']
    match_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
    match_date_only = pd.to_datetime(match['datetime_parsed']).date()
    
    past_h2h = h2h_stats.get((home_cn, away_cn), [])[-3:]
    h2h_home_win_rate = sum(1 for h, a in past_h2h if h > a) / len(past_h2h) if past_h2h else 0.5

    h_rest = (match_date_only - last_match_date.get(home_cn, match_date_only - timedelta(days=7)).date()).days
    a_rest = (match_date_only - last_match_date.get(away_cn, match_date_only - timedelta(days=7)).date()).days
    
    h = team_stats.get(home_cn, {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]})
    a = team_stats.get(away_cn, {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]})
    
    h_avg_scored = np.mean(h['scored'][-5:]) if h['scored'] else league_avg_goals
    h_avg_conceded = np.mean(h['conceded'][-5:]) if h['conceded'] else league_avg_goals
    a_avg_scored = np.mean(a['scored'][-5:]) if a['scored'] else league_avg_goals
    a_avg_conceded = np.mean(a['conceded'][-5:]) if a['conceded'] else league_avg_goals
    
    h_home_scored = np.mean(h['home_scored'][-3:]) if h['home_scored'] else league_avg_goals
    h_home_conceded = np.mean(h['home_conceded'][-3:]) if h['home_conceded'] else league_avg_goals
    a_away_scored = np.mean(a['away_scored'][-3:]) if a['away_scored'] else league_avg_goals
    a_away_conceded = np.mean(a['away_conceded'][-3:]) if a['away_conceded'] else league_avg_goals

    h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
    a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
    h_home_attack, h_home_defense = h_home_scored / league_avg_goals, h_home_conceded / league_avg_goals
    a_away_attack, a_away_defense = a_away_scored / league_avg_goals, a_away_conceded / league_avg_goals
    
    h_win_rate = np.mean(h['points'][-5:]) if h['points'] else 0.5
    a_win_rate = np.mean(a['points'][-5:]) if a['points'] else 0.5

    feature_dict = {
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'home_attack_spec': h_home_attack, 'home_defense_spec': h_home_defense, 
        'away_attack_spec': a_away_attack, 'away_defense_spec': a_away_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'rest_days': h_rest, 'opp_rest_days': a_rest, 'is_home': 1,
        'home_rank': team_rank_dict.get(home_cn, 15), 'away_rank': team_rank_dict.get(away_cn, 15),
        'prob_h_odds': match['主胜概率'], 'prob_d_odds': match['平局概率'], 'prob_a_odds': match['客胜概率']
    }
    X_pred = pd.DataFrame([feature_dict])
    home_xg, away_xg = max(0.1, model_home_goals.predict(X_pred)[0]), max(0.1, model_away_goals.predict(X_pred)[0])
    
    max_goals = 5
    prob_matrix = np.zeros((max_goals+1, max_goals+1))
    for hg in range(max_goals+1):
        for ag in range(max_goals+1):
            prob_matrix[hg][ag] = poisson.pmf(hg, home_xg) * poisson.pmf(ag, away_xg)
            
    prob_home_win = np.sum(np.tril(prob_matrix, -1))
    prob_draw = np.sum(np.diag(prob_matrix))
    prob_away_win = np.sum(np.triu(prob_matrix, 1))
    total_p = prob_home_win + prob_draw + prob_away_win
    prob_home_win /= total_p; prob_draw /= total_p; prob_away_win /= total_p
    
    probs = [prob_away_win, prob_draw, prob_home_win]
    pred_result = np.argmax(probs)
    recommend = "主胜" if pred_result == 2 else ("平局" if pred_result == 1 else "客胜")
    
    score_probs = [(f"{hg}-{ag}", prob_matrix[hg][ag]) for hg in range(max_goals+1) for ag in range(max_goals+1)]
    score_probs.sort(key=lambda x: x[1], reverse=True)
    top3 = score_probs[:3]
    prob_over_2_5 = sum(prob_matrix[hg][ag] for hg in range(max_goals+1) for ag in range(max_goals+1) if hg + ag > 2.5)
    over_under_msg = f"大2.5球" if prob_over_2_5 > 0.5 else f"小2.5球"

    weather = get_match_weather(home_cn, match_time)
    market_h, market_d, market_a = match['主胜概率'], match['平局概率'], match['客胜概率']
    
    kelly_h, kelly_d, kelly_a = 0.0, 0.0, 0.0
    odds_h = match.get('真实赔率主胜', 2.0)
    odds_d = match.get('真实赔率平局', 3.0)
    odds_a = match.get('真实赔率客胜', 3.0)
    if pd.notna(odds_h) and odds_h > 1.0: kelly_h = (prob_home_win * odds_h - 1) / (odds_h - 1)
    if pd.notna(odds_d) and odds_d > 1.0: kelly_d = (prob_draw * odds_d - 1) / (odds_d - 1)
    if pd.notna(odds_a) and odds_a > 1.0: kelly_a = (prob_away_win * odds_a - 1) / (odds_a - 1)
        
    kelly_msg = f"最优下注比例：主胜 {max(0, kelly_h)*100:.1f}% | 平局 {max(0, kelly_d)*100:.1f}% | 客胜 {max(0, kelly_a)*100:.1f}%"

    odds_drift_msg = "暂无历史赔率对比。"
    if os.path.exists('odds_history.csv'):
        hist_odds = pd.read_csv('odds_history.csv')
        past_match = hist_odds[(hist_odds['主队'] == home_cn) & (hist_odds['客队'] == away_cn)]
        if not past_match.empty:
            last_odds = past_match.iloc[-1]
            diff_h = (odds_h - last_odds['odds_h']) / last_odds['odds_h']
            diff_a = (odds_a - last_odds['odds_a']) / last_odds['odds_a']
            if abs(diff_h) > 0.1 or abs(diff_a) > 0.1:
                odds_drift_msg = f"⚠️ 资金异动：主胜赔率变化 {diff_h*100:.1f}%，客胜赔率变化 {diff_a*100:.1f}%"
            else:
                odds_drift_msg = "赔率相对稳定，无显著资金异动。"
                
    odds_history_list.append({'date': match_date_only.strftime('%Y-%m-%d'), '主队': home_cn, '客队': away_cn, 'odds_h': odds_h, 'odds_d': odds_d, 'odds_a': odds_a})

    home_injuries_str = '，'.join(injury_dict.get(home_cn, ["无"]))
    away_injuries_str = '，'.join(injury_dict.get(away_cn, ["无"]))
    weather_str = weather['天气'] if isinstance(weather, dict) else weather
    
    h_rot = f"{home_cn}休息{h_rest}天。" + ("赛程密集!" if h_rest <= 3 else "")
    a_rot = f"{away_cn}休息{a_rest}天。" + ("赛程密集!" if a_rest <= 3 else "")

    prompt = f"""你是一位精通英超的资深数据分析专家，同时也是战术大师。请基于以下数据，结合历史经验，写一段精炼、口语化的赛前点评（不超过180字）：
    比赛：{home_cn} vs {away_cn}
    赛程密度：{h_rot} {a_rot}
    历史交锋：近3次交手主队胜率 {h2h_home_win_rate*100:.1f}%
    主场龙/客场虫分析：{home_cn}主场进{h_home_scored:.2f}失{h_home_conceded:.2f}；{away_cn}客场进{a_away_scored:.2f}失{a_away_conceded:.2f}。
    进球期望：主队 {home_xg:.2f}，客队 {away_xg:.2f}。大小球倾向：{over_under_msg}。
    赔率倾向：主胜 {market_h*100:.1f}%，平局 {market_d*100:.1f}%，客胜 {market_a*100:.1f}%。
    赔率异动：{odds_drift_msg}
    {kelly_msg}
    伤停：{home_cn} [{home_injuries_str}]；{away_cn} [{away_injuries_str}]。
    **任务**：请务必结合两队大概率使用的阵型分析战术克制关系。
    **历史经验库**：{knowledge_base}
    请综合以上信息分析，并以“推荐关注：XXX”结尾。"""
    
    try:
        response = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        expert_comment = response.choices[0].message.content.strip()
    except: expert_comment = "【AI深度分析暂时不可用】"
    
    prediction_logs.append({
        'date': match_date_only.strftime('%Y-%m-%d'),
        'home_team': home_cn, 'away_team': away_cn,
        'predicted_result': recommend,
        'pred_prob_h': round(prob_home_win, 4), 'pred_prob_d': round(prob_draw, 4), 'pred_prob_a': round(prob_away_win, 4),
        'predicted_score': top3[0][0],
        'odds_h': odds_h, 'odds_d': odds_d, 'odds_a': odds_a,
        'weather': weather_str,
        'home_injuries': home_injuries_str,
        'away_injuries': away_injuries_str,
        'home_rest': h_rest,
        'away_rest': a_rest
    })

    # ==================== 中文化图表 ====================
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    labels = ['主胜', '平局', '客胜']
    model_probs = [prob_home_win, prob_draw, prob_away_win]
    market_probs = [market_h, market_d, market_a]
    x = np.arange(len(labels))
    width = 0.35
    ax1.bar(x - width/2, model_probs, width, label='V22 模型', color='royalblue')
    ax1.bar(x + width/2, market_probs, width, label='市场平均', color='gray', alpha=0.7)
    ax1.set_xticks(x); ax1.set_xticklabels(labels)
    ax1.set_ylabel('概率')
    ax1.set_title(f"{home_cn} vs {away_cn} - 胜平负概率")
    ax1.legend()
    
    kelly_vals = [max(0, kelly_h), max(0, kelly_d), max(0, kelly_a)]
    ax2.bar(labels, kelly_vals, color=['green', 'orange', 'red'])
    ax2.set_ylabel('建议下注比例 (%)')
    ax2.set_title(f"凯利下注建议")
    
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    img_buffers.append(buf)
    plt.close(fig)

    html_report += f"<hr><h3>{match_time} - {home_cn} vs {away_cn}</h3>"
    html_report += f"<img src='cid:chart_{idx}' width='600'><br>"
    html_report += f"<p><b>📊 核心数据：</b>{home_cn} 近5场 {h_avg_scored:.2f}进/{h_avg_conceded:.2f}失 | {away_cn} 近5场 {a_avg_scored:.2f}进/{a_avg_conceded:.2f}失</p>"
    html_report += f"<p><b>⚔️ 历史交锋：</b>近3次交手，主队胜率 {h2h_home_win_rate*100:.1f}%</p>"
    html_report += f"<p><b>⚠️ 临场异动：</b>{odds_drift_msg}</p>"
    html_report += f"<p><b>💰 凯利建议：</b>{kelly_msg}</p>"
    html_report += f"<p><b>🎯 模型预测：</b>主胜 {prob_home_win*100:.1f}% | 平局 {prob_draw*100:.1f}% | 客胜 {prob_away_win*100:.1f}% (比分推荐: {top3[0][0]})</p>"
    html_report += f"<p><b>🧠 AI战术点评：</b>{expert_comment}</p>"
    html_report += f"<p><b>💡 综合推荐：</b>{recommend}</p>"

html_report += "</body></html>"

log_df = pd.DataFrame(prediction_logs)
if os.path.exists('predictions_log.csv'):
    old_log = pd.read_csv('predictions_log.csv')
    for col in ['odds_h', 'odds_d', 'odds_a', 'weather', 'home_injuries', 'away_injuries', 'home_rest', 'away_rest']:
        if col not in old_log.columns: old_log[col] = ""
    log_df = pd.concat([old_log, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

history_df = pd.DataFrame(odds_history_list)
if os.path.exists('odds_history.csv'):
    old_hist = pd.read_csv('odds_history.csv')
    history_df = pd.concat([old_hist, history_df]).drop_duplicates(subset=['date', '主队', '客队'], keep='last')
history_df.to_csv('odds_history.csv', index=False, encoding='utf-8-sig')

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html_report)

send_rich_email("本周末英超 V22 图文预测报告", html_report, img_buffers)