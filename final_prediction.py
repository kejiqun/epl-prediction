import pandas as pd
import numpy as np
import requests
import joblib
import os
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
from team_mapping import translate_team_name

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

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

# 基础字典（用于数据加载）
team_mapping = {
    '阿森纳': '阿森纳', '阿斯顿维拉': '阿斯顿维拉', '伯恩茅斯': '伯恩茅斯', '布伦特福德': '布伦特福德', '布莱顿': '布莱顿', '切尔西': '切尔西', '水晶宫': '水晶宫', '埃弗顿': '埃弗顿', '富勒姆': '富勒姆', '伊普斯维奇': '伊普斯维奇', '莱斯特城': '莱斯特城', '利物浦': '利物浦', '曼城': '曼城', '曼联': '曼联', '纽卡斯尔联': '纽卡斯尔联', '诺丁汉森林': '诺丁汉森林', '南安普顿': '南安普顿', '热刺': '热刺', '托特纳姆热刺': '热刺', '西汉姆联': '西汉姆联', '狼队': '狼队'
}

team_city_mapping = {
    '阿森纳': 'London', '切尔西': 'London', '托特纳姆热刺': 'London', '西汉姆联': 'London', '水晶宫': 'London', '富勒姆': 'London', '布伦特福德': 'London',
    '曼联': 'Manchester', '曼城': 'Manchester', '利物浦': 'Liverpool', '埃弗顿': 'Liverpool', '纽卡斯尔联': 'Newcastle', '阿斯顿维拉': 'Birmingham',
    '狼队': 'Wolverhampton', '布莱顿': 'Brighton', '诺丁汉森林': 'Nottingham', '莱斯特城': 'Leicester', '南安普顿': 'Southampton', '伯恩茅斯': 'Bournemouth',
    '伊普斯维奇': 'Ipswich', '利兹联': 'Leeds', '桑德兰': 'Sunderland', '赫尔城': 'Hull', '考文垂': 'Coventry', '伯恩利': 'Burnley', '谢菲尔德联': 'Sheffield',
    '卢顿': 'Luton', '沃特福德': 'Watford', '诺维奇': 'Norwich',
    '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '马德里竞技': 'Madrid', '塞维利亚': 'Seville', '皇家贝蒂斯': 'Seville', '瓦伦西亚': 'Valencia',
    '拜仁慕尼黑': 'Munich', '多特蒙德': 'Dortmund', '勒沃库森': 'Leverkusen', '莱比锡红牛': 'Leipzig',
    '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin', '那不勒斯': 'Naples', '罗马': 'Rome', '拉齐奥': 'Rome'
}

def get_match_weather(home_team, date_str):
    city = team_city_mapping.get(home_team, 'London') # 默认伦敦
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

def dixon_coles_tau(h, a, home_xg, away_xg, rho=-0.1):
    if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
    elif h == 0 and a == 1: return 1 + home_xg * rho
    elif h == 1 and a == 0: return 1 + away_xg * rho
    elif h == 1 and a == 1: return 1 - rho
    else: return 1.0

print("⏳ 读取每日多联赛赛程...")
if not os.path.exists('daily_matches.csv'):
    print("❌ 找不到 daily_matches.csv，请检查抓取步骤。")
    exit()

df_next_round = pd.read_csv('daily_matches.csv')
# 🌟 过滤掉没有赔率的比赛（三大赔率不全就跳过）
df_next_round = df_next_round[(df_next_round['odds_h'] > 1) & (df_next_round['odds_d'] > 1) & (df_next_round['odds_a'] > 1)].copy()

if df_next_round.empty:
    print("⚠️ 今日无带赔率的比赛，停止预测。")
    exit()

df_next_round['datetime_parsed'] = pd.to_datetime(df_next_round['datetime']).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)

try:
    df_standings = pd.read_csv('epl_standings.csv')
    team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
except: team_rank_dict = {}

injury_dict = {}
injury_impact = {}
try:
    fpl_resp = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15)
    if fpl_resp.status_code == 200:
        fpl_data = fpl_resp.json()
        teams_map = {t['id']: t['name'] for t in fpl_data['teams']}
        team_avg_points = {t['id']: t['strength_attack_home'] + t['strength_defence_home'] for t in fpl_data['teams']}
        for element in fpl_data['elements']:
            team_id = element['team']
            team_name_en = teams_map.get(team_id)
            # 简单映射一下 FPL 英文名到中文
            team_name_cn = team_mapping.get(team_name_en, team_name_en)
            
            # 补漏映射
            if team_name_en == 'Spurs': team_name_cn = '热刺'
            elif team_name_en == 'Man Utd': team_name_cn = '曼联'
            elif team_name_en == 'Man City': team_name_cn = '曼城'
            elif team_name_en == 'Newcastle': team_name_cn = '纽卡斯尔联'
            elif team_name_en == 'Nott\'m Forest': team_name_cn = '诺丁汉森林'
            elif team_name_en == 'West Ham': team_name_cn = '西汉姆联'
            elif team_name_en == 'Wolves': team_name_cn = '狼队'

            player_name = element['web_name']; news = element['news']
            chance = element.get('chance_of_playing_next_round', 100)
            if chance is None: chance = 0
            if element['status'] in ['d', 'i', 's', 'u'] or chance < 75:
                status_cn = {"d": "出战成疑", "i": "受伤", "s": "停赛", "u": "不可用"}.get(element['status'], "未知")
                prob_str = f" (出战概率{chance}%)" if chance is not None and chance > 0 else ""
                if team_name_cn not in injury_dict: injury_dict[team_name_cn] = []
                injury_dict[team_name_cn].append(f"{player_name}({status_cn}{prob_str}: {news})" if news else f"{player_name}({status_cn}{prob_str})")
                if element['total_points'] > 30:
                    if team_name_cn not in injury_impact: injury_impact[team_name_cn] = 0
                    injury_impact[team_name_cn] += (element['total_points'] / team_avg_points.get(team_id, 1)) * 0.05
except: pass

print("⏳ 正在加载 V31 模型及校准器...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(lambda x: team_mapping.get(x.replace(" and ", " & ").strip(), x))
df_hist['away_team_cn'] = df_hist['away_team'].apply(lambda x: team_mapping.get(x.replace(" and ", " & ").strip(), x))

model_home_goals = joblib.load('epl_v31_home_goals_model.pkl')
model_away_goals = joblib.load('epl_v31_away_goals_model.pkl')

try:
    calibrator_h = joblib.load('calibrator_h_v31.pkl')
    calibrator_d = joblib.load('calibrator_d_v31.pkl')
    calibrator_a = joblib.load('calibrator_a_v31.pkl')
    use_calibration = True
    print("✅ 成功加载 V31 概率校准器！")
except:
    use_calibration = False
    print("⚠️ 未找到校准器，使用原始概率。")

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

html_report = "<html><body><h2>⚽ 全球足球多联赛全自动预测系统 V8.0</h2>"
prediction_logs = []
img_buffers = []
odds_history_list = []

# 🌟 按联赛分组处理
for league_name in df_next_round['league'].unique():
    league_df = df_next_round[df_next_round['league'] == league_name]
    html_report += f"<h2 style='color:blue;'>🏆 {league_name}</h2>"
    
    for idx, (_, match) in enumerate(league_df.iterrows()):
        home_cn, away_cn = match['home_team'], match['away_team']
        match_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
        match_date_only = pd.to_datetime(match['datetime_parsed']).date()
        
        # 尝试获取历史数据，如果没有（比如西甲球队），则使用平均值
        h = team_stats.get(home_cn, {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]})
        a = team_stats.get(away_cn, {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]})
        
        h_avg_scored = np.mean(h['scored'][-5:]) if h['scored'] else league_avg_goals
        h_avg_conceded = np.mean(h['conceded'][-5:]) if h['conceded'] else league_avg_goals
        a_avg_scored = np.mean(a['scored'][-5:]) if a['scored'] else league_avg_goals
        a_avg_conceded = np.mean(a['conceded'][-5:]) if a['conceded'] else league_avg_goals
        
        h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
        a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
        
        # 恢复默认值
        h_home_attack, h_home_defense = h_attack, h_defense
        a_away_attack, a_away_defense = a_attack, a_defense
        
        h_win_rate = np.mean(h['points'][-5:]) if h['points'] else 0.5
        a_win_rate = np.mean(a['points'][-5:]) if a['points'] else 0.5
        h_form_trend = (np.mean(h['points'][-3:]) - np.mean(h['points'][-5:])) if len(h['points']) >= 5 else 0.0
        a_form_trend = (np.mean(a['points'][-3:]) - np.mean(a['points'][-5:])) if len(a['points']) >= 5 else 0.0

        h_inj_factor = 1 - injury_impact.get(home_cn, 0)
        a_inj_factor = 1 - injury_impact.get(away_cn, 0)

        # 市场概率
        imp_h = 1 / match['odds_h']; imp_d = 1 / match['odds_d']; imp_a = 1 / match['odds_a']
        total_imp = imp_h + imp_d + imp_a
        market_h, market_d, market_a = imp_h/total_imp, imp_d/total_imp, imp_a/total_imp

        feature_dict = {
            'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
            'home_attack_spec': h_home_attack, 'home_defense_spec': h_home_defense,
            'away_attack_spec': a_away_attack, 'away_defense_spec': a_away_defense,
            'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'win_rate_diff': h_win_rate - a_win_rate,
            'rest_days': 7, 'opp_rest_days': 7, 'is_home': 1,
            'home_rank': team_rank_dict.get(home_cn, 15), 'away_rank': team_rank_dict.get(away_cn, 15),
            'h_form_trend': h_form_trend, 'a_form_trend': a_form_trend,
            'prob_h_odds': market_h, 'prob_d_odds': market_d, 'prob_a_odds': market_a
        }
        X_pred = pd.DataFrame([feature_dict])
        home_xg, away_xg = max(0.1, model_home_goals.predict(X_pred)[0]), max(0.1, model_away_goals.predict(X_pred)[0])
        
        home_xg = home_xg * h_inj_factor
        away_xg = away_xg * a_inj_factor
        
        max_goals = 5
        prob_matrix = np.zeros((max_goals+1, max_goals+1))
        for hg in range(max_goals+1):
            for ag in range(max_goals+1):
                base_prob = poisson.pmf(hg, home_xg) * poisson.pmf(ag, away_xg)
                tau = dixon_coles_tau(hg, ag, home_xg, away_xg)
                prob_matrix[hg][ag] = base_prob * tau
                
        raw_prob_home_win = np.sum(np.tril(prob_matrix, -1))
        raw_prob_draw = np.sum(np.diag(prob_matrix))
        raw_prob_away_win = np.sum(np.triu(prob_matrix, 1))
        total_p = raw_prob_home_win + raw_prob_draw + raw_prob_away_win
        raw_prob_home_win /= total_p; raw_prob_draw /= total_p; raw_prob_away_win /= total_p
        
        if use_calibration:
            prob_home_win = calibrator_h.predict([raw_prob_home_win])[0]
            prob_draw = calibrator_d.predict([raw_prob_draw])[0]
            prob_away_win = calibrator_a.predict([raw_prob_away_win])[0]
            cal_total = prob_home_win + prob_draw + prob_away_win
            prob_home_win /= cal_total; prob_draw /= cal_total; prob_away_win /= cal_total
        else:
            prob_home_win = raw_prob_home_win; prob_draw = raw_prob_draw; prob_away_win = raw_prob_away_win
        
        probs = [prob_away_win, prob_draw, prob_home_win]
        pred_result = np.argmax(probs)
        recommend = "主胜" if pred_result == 2 else ("平局" if pred_result == 1 else "客胜")
        
        all_scores = [(f"{hg}-{ag}", prob_matrix[hg][ag]) for hg in range(max_goals+1) for ag in range(max_goals+1)]
        if recommend == "主胜":
            valid_scores = [s for s in all_scores if int(s[0].split('-')[0]) > int(s[0].split('-')[1])]
        elif recommend == "客胜":
            valid_scores = [s for s in all_scores if int(s[0].split('-')[0]) < int(s[0].split('-')[1])]
        else:
            valid_scores = [s for s in all_scores if int(s[0].split('-')[0]) == int(s[0].split('-')[1])]
        valid_scores.sort(key=lambda x: x[1], reverse=True)
        top3 = valid_scores[:3]

        odds_h = match['odds_h']
        odds_d = match['odds_d']
        odds_a = match['odds_a']
        
        kelly_h = (prob_home_win * odds_h - 1) / (odds_h - 1) if odds_h > 1.0 else 0.0
        kelly_d = (prob_draw * odds_d - 1) / (odds_d - 1) if odds_d > 1.0 else 0.0
        kelly_a = (prob_away_win * odds_a - 1) / (odds_a - 1) if odds_a > 1.0 else 0.0
        kelly_msg = f"最优下注比例：主胜 {max(0, kelly_h)*100:.1f}% | 平局 {max(0, kelly_d)*100:.1f}% | 客胜 {max(0, kelly_a)*100:.1f}%"

        weather = get_match_weather(home_cn, match_time)
        weather_str = weather['天气'] if isinstance(weather, dict) else weather
        
        home_injuries_str = '，'.join(injury_dict.get(home_cn, ["无"]))
        away_injuries_str = '，'.join(injury_dict.get(away_cn, ["无"]))

        prompt = f"""你是一位精通全球足球的资深数据分析专家，同时也是盘口大师。请基于以下数据，写一段精炼、口语化的赛前点评（不超过150字）：
        比赛：{home_cn} vs {away_cn} ({league_name})
        当前模型综合推荐：{recommend}
        进球期望：主队 {home_xg:.2f}，客队 {away_xg:.2f}。
        赔率倾向：主胜 {market_h*100:.1f}%，平局 {market_d*100:.1f}%，客胜 {market_a*100:.1f}%。
        {kelly_msg}
        伤停：{home_cn} [{home_injuries_str}]；{away_cn} [{away_injuries_str}]。
        
        **任务**：请结合阵型克制关系，重点从“机构诱盘心理”角度分析。**极其重要：你的分析必须支撑模型得出的“{recommend}”结论。**
        **历史经验库**：{knowledge_base}
        请综合以上信息分析，并以“推荐关注：XXX”结尾（XXX必须与模型综合推荐一致）。"""
        
        try:
            response = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
            expert_comment = response.choices[0].message.content.strip()
        except: expert_comment = "【AI深度分析暂时不可用】"
        
        prediction_logs.append({
            'date': match_date_only.strftime('%Y-%m-%d'),
            'league': league_name,
            'home_team': home_cn, 'away_team': away_cn,
            'predicted_result': recommend,
            'pred_prob_h': round(prob_home_win, 4), 'pred_prob_d': round(prob_draw, 4), 'pred_prob_a': round(prob_away_win, 4),
            'predicted_score': top3[0][0],
            'odds_h': odds_h, 'odds_d': odds_d, 'odds_a': odds_a,
            'weather': weather_str,
            'home_injuries': home_injuries_str,
            'away_injuries': away_injuries_str,
            'referee': "暂无"
        })

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        labels = ['主胜', '平局', '客胜']
        model_probs = [prob_home_win, prob_draw, prob_away_win]
        market_probs = [market_h, market_d, market_a]
        x = np.arange(len(labels)); width = 0.35
        ax1.bar(x - width/2, model_probs, width, label='V31 校准模型', color='royalblue')
        ax1.bar(x + width/2, market_probs, width, label='市场平均', color='gray', alpha=0.7)
        ax1.set_xticks(x); ax1.set_xticklabels(labels); ax1.set_ylabel('概率')
        ax1.set_title(f"{home_cn} vs {away_cn}"); ax1.legend()

        kelly_vals = [max(0, kelly_h), max(0, kelly_d), max(0, kelly_a)]
        ax2.bar(labels, kelly_vals, color=['green', 'orange', 'red'])
        ax2.set_ylabel('建议下注比例 (%)'); ax2.set_title(f"凯利下注建议")

        plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=100); buf.seek(0)
        img_buffers.append(buf); plt.close(fig)

        html_report += f"<hr><h3>{match_time} - {home_cn} vs {away_cn} [{league_name}]</h3>"
        html_report += f"<img src='cid:chart_{len(img_buffers)-1}' width='600'><br>"
        html_report += f"<p><b>⚠️ 天气：</b>{weather_str}</p>"
        html_report += f"<p><b>💰 凯利建议：</b>{kelly_msg}</p>"
        html_report += f"<p><b>🎯 模型预测：</b>主胜 {prob_home_win*100:.1f}% | 平局 {prob_draw*100:.1f}% | 客胜 {prob_away_win*100:.1f}% (比分推荐: {top3[0][0]})</p>"
        html_report += f"<p><b>🧠 AI战术点评：</b>{expert_comment}</p>"
        html_report += f"<p><b>💡 综合推荐：</b>{recommend}</p>"

html_report += "</body></html>"

log_df = pd.DataFrame(prediction_logs)
if os.path.exists('predictions_log.csv'):
    old_log = pd.read_csv('predictions_log.csv')
    for col in log_df.columns:
        if col not in old_log.columns: old_log[col] = np.nan
    log_df = pd.concat([old_log, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html_report)

send_rich_email("全球多联赛 V8.0 每日战报", html_report, img_buffers)
