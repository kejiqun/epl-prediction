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

team_city_mapping = {
    '阿森纳': 'London', '切尔西': 'London', '热刺': 'London', '西汉姆联': 'London', '水晶宫': 'London', '富勒姆': 'London', '布伦特福德': 'London',
    '曼联': 'Manchester', '曼城': 'Manchester', '利物浦': 'Liverpool', '埃弗顿': 'Liverpool', '纽卡斯尔联': 'Newcastle', '阿斯顿维拉': 'Birmingham',
    '狼队': 'Wolverhampton', '布莱顿': 'Brighton', '诺丁汉森林': 'Nottingham', '莱斯特城': 'Leicester', '南安普顿': 'Southampton', '伯恩茅斯': 'Bournemouth',
    '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '马德里竞技': 'Madrid', '塞维利亚': 'Seville', '皇家贝蒂斯': 'Seville', '瓦伦西亚': 'Valencia',
    '拜仁慕尼黑': 'Munich', '多特蒙德': 'Dortmund', '勒沃库森': 'Leverkusen', '莱比锡红牛': 'Leipzig',
    '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin', '那不勒斯': 'Naples', '罗马': 'Rome', '拉齐奥': 'Rome'
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

def dixon_coles_tau(h, a, home_xg, away_xg, rho=-0.1):
    if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
    elif h == 0 and a == 1: return 1 + home_xg * rho
    elif h == 1 and a == 0: return 1 + away_xg * rho
    elif h == 1 and a == 1: return 1 - rho
    else: return 1.0

print("⏳ 正在读取虚拟资金账户...")
bankroll = 10000.0
if os.path.exists('bankroll.csv'):
    try:
        df_b = pd.read_csv('bankroll.csv')
        if not df_b.empty: bankroll = df_b.iloc[-1]['当前资金']
    except: pass
print(f"💰 当前账户资金: {bankroll:.2f} 元")

print("⏳ 读取每日多联赛赛程...")
if not os.path.exists('daily_matches.csv'): exit()

df_next_round = pd.read_csv('daily_matches.csv')
df_next_round['datetime_parsed'] = pd.to_datetime(df_next_round['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)

now_ts = pd.Timestamp.now()
df_next_round = df_next_round[(df_next_round['datetime_parsed'] >= now_ts) & (df_next_round['datetime_parsed'] <= now_ts + pd.Timedelta(hours=48))]

if df_next_round.empty:
    print("⚠️ 未来 48 小时内无比赛。")
    html_report = f"""<html><body><div style="text-align: center; padding: 50px;">
        <h2 style="color: #2c3e50;">🛡️ 今日休战</h2>
        <p style="color: #666; font-size: 16px;">未来 48 小时内没有需要预测的足球赛事。</p>
    </div></body></html>"""
    send_rich_email("🛡️ 多联赛每日战报 (今日休战)", html_report, [])
    exit()

try:
    df_standings = pd.read_csv('epl_standings.csv')
    team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
except: team_rank_dict = {}

injury_dict = {}; injury_impact = {}
try:
    fpl_resp = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15)
    if fpl_resp.status_code == 200:
        fpl_data = fpl_resp.json()
        teams_map = {t['id']: t['name'] for t in fpl_data['teams']}
        team_avg_points = {t['id']: t['strength_attack_home'] + t['strength_defence_home'] for t in fpl_data['teams']}
        for element in fpl_data['elements']:
            team_id = element['team']
            team_name_cn = translate_team_name(teams_map.get(team_id))
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
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

model_home_goals = joblib.load('epl_v31_home_goals_model.pkl')
model_away_goals = joblib.load('epl_v31_away_goals_model.pkl')

try:
    calibrator_h = joblib.load('calibrator_h_v31.pkl')
    calibrator_d = joblib.load('calibrator_d_v31.pkl')
    calibrator_a = joblib.load('calibrator_a_v31.pkl')
    use_calibration = True
except: use_calibration = False

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

html_report = "<html><body><h2>⚽ 全球足球多联赛全自动预测系统 V15.4 (优雅降级版)</h2>"
prediction_logs = []; img_buffers = []

for league_name in df_next_round['联赛'].unique():
    league_df = df_next_round[df_next_round['联赛'] == league_name]
    html_report += f"<h2 style='color:blue;'>🏆 {league_name}</h2>"
    
    for idx, (_, match) in enumerate(league_df.iterrows()):
        home_cn, away_cn = match['主队'], match['客队']
        match_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
        match_date_only = pd.to_datetime(match['datetime_parsed']).date()
        
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
        h_form_trend = (np.mean(h['points'][-3:]) - np.mean(h['points'][-5:])) if len(h['points']) >= 5 else 0.0
        a_form_trend = (np.mean(a['points'][-3:]) - np.mean(a['points'][-5:])) if len(a['points']) >= 5 else 0.0

        h_inj_factor = 1 - injury_impact.get(home_cn, 0)
        a_inj_factor = 1 - injury_impact.get(away_cn, 0)
        
        past_h2h = h2h_stats.get((home_cn, away_cn), [])[-3:]
        h2h_home_win_rate = sum(1 for hg, ag in past_h2h if hg > ag) / len(past_h2h) if past_h2h else 0.5

        real_odds_h = match.get('主胜赔率', 0.0)
        real_odds_d = match.get('平局赔率', 0.0)
        real_odds_a = match.get('客胜赔率', 0.0)
        
        has_real_odds = (pd.notna(real_odds_h) and real_odds_h > 1.0)
        
        if has_real_odds:
            odds_h, odds_d, odds_a = real_odds_h, real_odds_d, real_odds_a
        else:
            odds_h, odds_d, odds_a = 2.00, 3.30, 3.50

        imp_h = 1 / odds_h; imp_d = 1 / odds_d; imp_a = 1 / odds_a
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
        home_xg = home_xg * h_inj_factor; away_xg = away_xg * a_inj_factor
        
        max_goals = 6
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
        pred_result_idx = np.argmax(probs)
        predict_choice = "主胜" if pred_result_idx == 2 else ("平局" if pred_result_idx == 1 else "客胜")
        
        kelly_h = (prob_home_win * odds_h - 1) / (odds_h - 1)
        kelly_d = (prob_draw * odds_d - 1) / (odds_d - 1)
        kelly_a = (prob_away_win * odds_a - 1) / (odds_a - 1)
        
        max_kelly = 0; bet_choice = ""
        if kelly_h > 0.02 and prob_home_win > 0.25: max_kelly = kelly_h; bet_choice = "主胜"
        if kelly_d > max_kelly and prob_draw > 0.25: max_kelly = kelly_d; bet_choice = "平局"
        if kelly_a > max_kelly and prob_away_win > 0.25: max_kelly = kelly_a; bet_choice = "客胜"
            
        final_recommend = predict_choice
        split_logic = ""
        bet_amount = 0.0
        bet_info_msg = "模型认为无价值，建议空仓观望"
        
        if not has_real_odds:
            bet_info_msg = "⚠️ 无真实市场赔率"
            split_logic = f"🛑 <b>风控提示：</b>未抓取到真实赔率，无法计算价值。模型倾向：<b>{predict_choice}</b>，仅供观赛参考，<b>坚决禁止实盘下注</b>。"
            final_recommend = "观望"
            kelly_msg = "暂无真实赔率，无法计算凯利"
        else:
            kelly_msg = f"主胜 {max(0, kelly_h)*100:.1f}% | 平局 {max(0, kelly_d)*100:.1f}% | 客胜 {max(0, kelly_a)*100:.1f}%"
            if max_kelly > 0.02:
                safe_kelly = min(max_kelly * 0.5, 0.05)
                bet_amount = bankroll * safe_kelly
                final_recommend = bet_choice
                bet_info_msg = f"推荐下注 <b>{bet_amount:.2f}</b> 元 (占总资金 {safe_kelly*100:.1f}%)"
                if bet_choice != predict_choice:
                    split_logic = f"⚠️ <b>量化提示：</b>模型预测赛果为 <b>{predict_choice}</b>，但 <b>{bet_choice}</b> 的赔率提供了极高的价值，综合推荐去买 <b>{bet_choice}</b>。"
            else:
                if (kelly_a > 0.02 and prob_away_win <= 0.25) or (kelly_d > 0.02 and prob_draw <= 0.25) or (kelly_h > 0.02 and prob_home_win <= 0.25):
                    split_logic = f"🛑 <b>风控警告：</b>虽然某项赔率极高（凯利为正），但发生概率低于25%，属于“买彩票”行为，系统直接禁手。"
                else:
                    split_logic = f"⚠️ <b>量化提示：</b>模型预测赛果为 <b>{predict_choice}</b>，但赔率过低/无价值，建议观望。"

        all_scores = [(f"{hg}-{ag}", prob_matrix[hg][ag]) for hg in range(max_goals+1) for ag in range(max_goals+1)]
        all_scores.sort(key=lambda x: x[1], reverse=True)
        top3_scores_str = ", ".join([f"{s[0]}({s[1]*100:.1f}%)" for s in all_scores[:3]])

        handicap = match.get('让球盘口', 0.0)
        h_handicap_odd = match.get('主让胜赔率', 0.0)
        a_handicap_odd = match.get('客受让胜赔率', 0.0)
        
        total_line = match.get('大小球盘口', 2.5)
        over_odd = match.get('大球赔率', 0.0)
        under_odd = match.get('小球赔率', 0.0)
        
        has_real_ou = (pd.notna(total_line) and total_line > 0 and pd.notna(over_odd) and over_odd > 1.0)
        has_real_hc = (pd.notna(handicap) and handicap != 0 and pd.notna(h_handicap_odd) and h_handicap_odd > 1.0)
        
        if h_handicap_odd <= 1 or pd.isna(h_handicap_odd): h_handicap_odd = 1.90
        if a_handicap_odd <= 1 or pd.isna(a_handicap_odd): a_handicap_odd = 1.90
        if over_odd <= 1 or pd.isna(over_odd): over_odd = 1.90
        if under_odd <= 1 or pd.isna(under_odd): under_odd = 1.90
        if pd.isna(total_line) or total_line == 0: total_line = 2.5
        
        prob_over = sum(prob_matrix[hg][ag] for hg in range(max_goals+1) for ag in range(max_goals+1) if hg + ag > total_line)
        prob_under = sum(prob_matrix[hg][ag] for hg in range(max_goals+1) for ag in range(max_goals+1) if hg + ag < total_line)
        
        prob_handicap_home = sum(prob_matrix[hg][ag] for hg in range(max_goals+1) for ag in range(max_goals+1) if hg + handicap > ag)
        prob_handicap_away = sum(prob_matrix[hg][ag] for hg in range(max_goals+1) for ag in range(max_goals+1) if hg + handicap < ag)
        
        ou_recommend = "观望"
        ou_msg = f"盘口{total_line}，大球{prob_over*100:.1f}% / 小球{prob_under*100:.1f}%。"
        ou_bet_amount = 0.0
        
        if not has_real_ou:
            ou_msg += " (缺失真实赔率，仅供观赛)"
        else:
            ev_over = prob_over * over_odd
            ev_under = prob_under * under_odd
            if ev_over > 1.05 and ev_over > ev_under:
                ou_recommend = "大球"
                kelly_ou = (ev_over - 1) / (over_odd - 1)
                ou_bet_amount = bankroll * min(kelly_ou * 0.5, 0.05)
                ou_msg += f" 大球价值极高！(赔率{over_odd:.2f})"
            elif ev_under > 1.05 and ev_under > ev_over:
                ou_recommend = "小球"
                kelly_ou = (ev_under - 1) / (under_odd - 1)
                ou_bet_amount = bankroll * min(kelly_ou * 0.5, 0.05)
                ou_msg += f" 小球价值极高！(赔率{under_odd:.2f})"

        handicap_recommend = "观望"
        handicap_msg = f"主让{handicap}，主赢盘{prob_handicap_home*100:.1f}% / 客赢盘{prob_handicap_away*100:.1f}%。"
        hc_bet_amount = 0.0
        if not has_real_hc:
            handicap_msg += " (缺失真实赔率，仅供观赛)"
        else:
            ev_hc_home = prob_handicap_home * h_handicap_odd
            ev_hc_away = prob_handicap_away * a_handicap_odd
            if ev_hc_home > 1.05 and ev_hc_home > ev_hc_away:
                handicap_recommend = "主队赢盘"
                kelly_hc = (ev_hc_home - 1) / (h_handicap_odd - 1)
                hc_bet_amount = bankroll * min(kelly_hc * 0.5, 0.05)
                handicap_msg += f" 主赢盘具有价值！(赔率{h_handicap_odd:.2f})"
            elif ev_hc_away > 1.05 and ev_hc_away > ev_hc_home:
                handicap_recommend = "客队赢盘"
                kelly_hc = (ev_hc_away - 1) / (a_handicap_odd - 1)
                hc_bet_amount = bankroll * min(kelly_hc * 0.5, 0.05)
                handicap_msg += f" 客赢盘具有价值！(赔率{a_handicap_odd:.2f})"

        weather = get_match_weather(home_cn, match_time)
        weather_str = weather['天气'] if isinstance(weather, dict) else weather
        
        home_injuries_str = '，'.join(injury_dict.get(home_cn, ["无"]))
        away_injuries_str = '，'.join(injury_dict.get(away_cn, ["无"]))

        prompt = f"""你是一位精通全球足球的资深数据分析专家，同时也是盘口大师。请基于以下数据，写一段精炼、口语化的赛前点评（不超过150字）：
        比赛：{home_cn} vs {away_cn} ({league_name})
        赛果倾向：{predict_choice}，最终胜平负下注：{final_recommend}
        进球期望：主队 {home_xg:.2f}，客队 {away_xg:.2f}。
        大小球解析：{ou_msg} 推荐：{ou_recommend}
        让球解析：{handicap_msg} 推荐：{handicap_recommend}
        伤停：{home_cn} [{home_injuries_str}]；{away_cn} [{away_injuries_str}]。
        
        **任务**：重点从“机构诱盘心理”和“价值投注”角度分析。必须支撑大小球和让球的量化结论。
        请综合以上信息分析，并以“推荐关注：{final_recommend}，盘口倾向：{ou_recommend}/{handicap_recommend}”结尾。"""
        
        try:
            response = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
            expert_comment = response.choices[0].message.content.strip()
        except: expert_comment = "【AI深度分析暂时不可用】"
        
        prediction_logs.append({
            'date': match_date_only.strftime('%Y-%m-%d'), 'league': league_name,
            'home_team': home_cn, 'away_team': away_cn,
            'predicted_result': final_recommend,
            'bet_amount': round(bet_amount, 2),
            'pred_prob_h': round(prob_home_win, 4), 'pred_prob_d': round(prob_draw, 4), 'pred_prob_a': round(prob_away_win, 4),
            'predicted_score': all_scores[0][0],
            'model_home_xg': round(home_xg, 3), 'model_away_xg': round(away_xg, 3),
            'model_net_xg': round(home_xg - away_xg, 3), 'model_total_xg': round(home_xg + away_xg, 3),
            'handicap': handicap, 'total_line': total_line,
            'ou_recommend': ou_recommend, 'ou_bet_amount': round(ou_bet_amount, 2), 'over_odd': over_odd, 'under_odd': under_odd,
            'hc_recommend': handicap_recommend, 'hc_bet_amount': round(hc_bet_amount, 2), 'h_handicap_odd': h_handicap_odd, 'a_handicap_odd': a_handicap_odd,
            'odds_h': odds_h, 'odds_d': odds_d, 'odds_a': odds_a,
            'weather': weather_str, 'home_injuries': home_injuries_str, 'away_injuries': away_injuries_str
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
        
        # 🌟 核心美化：如果没赔率，右侧画提示框，绝不画大白板
        if not has_real_odds:
            ax2.text(0.5, 0.5, '暂未抓取到真实市场赔率\n禁止计算凯利指数', horizontalalignment='center', verticalalignment='center', fontsize=14, color='gray')
            ax2.set_xticks([]); ax2.set_yticks([])
        else:
            kelly_vals = [max(0, kelly_h), max(0, kelly_d), max(0, kelly_a)]
            ax2.bar(labels, kelly_vals, color=['green', 'orange', 'red'])
            ax2.set_ylabel('建议下注比例 (%)'); ax2.set_title(f"凯利下注建议")
            
        plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=100); buf.seek(0)
        img_buffers.append(buf); plt.close(fig)

        html_report += f"<hr><h3>{match_time} - {home_cn} vs {away_cn} [{league_name}]</h3>"
        html_report += f"<img src='cid:chart_{len(img_buffers)-1}' width='600'><br>"
        html_report += f"<p><b>⚖️ 亚盘让球：</b>{handicap_msg}</p>"
        html_report += f"<p><b>⚖️ 大小球：</b>{ou_msg}</p>"
        html_report += f"<p><b>⚔️ 历史交锋：</b>近3次交手，主队胜率 {h2h_home_win_rate*100:.1f}%</p>"
        html_report += f"<p><b>💰 胜平负凯利：</b>{kelly_msg}</p>"
        html_report += f"<p><b>🎯 赛果概率：</b>主胜 {prob_home_win*100:.1f}% | 平局 {prob_draw*100:.1f}% | 客胜 {prob_away_win*100:.1f}%</p>"
        html_report += f"<p><b>🔮 比分推荐 (Top 3)：</b>{top3_scores_str}</p>"
        
        html_report += f"""
        <div style='background-color:#f8f9fa; border:1px solid #ddd; padding:15px; border-radius:8px; margin-top:15px;'>
            <p style='margin:0; font-size:16px;'><b>💡 最终胜平负下注：</b><span style='font-size:22px;color:red;font-weight:bold;'>{final_recommend}</span></p>
            <p style='margin:5px 0 0 0; color:#333;'><b>💰 下注金额：</b>{bet_info_msg}</p>
            <p style='margin:5px 0 0 0; color:#d35400; font-size:14px;'>{split_logic}</p>
            <hr style='border:0;border-top:1px solid #eee;margin:10px 0;'>
            <p style='margin:0; font-size:16px;'><b>⚽ 大小球量化建议：</b><span style='font-size:22px;color:blue;font-weight:bold;'>{ou_recommend}</span></p>
            <p style='margin:0; font-size:16px;'><b>⚖️ 让球盘量化建议：</b><span style='font-size:22px;color:purple;font-weight:bold;'>{handicap_recommend}</span></p>
        </div>
        """
        html_report += f"<p style='margin-top:15px;'><b>🧠 AI战术点评：</b>{expert_comment}</p>"

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

send_rich_email("全球多联赛 V15.4 每日战报 (优雅降级版)", html_report, img_buffers)
