import pandas as pd
import numpy as np
import requests
import joblib
import os
import io
import json
import re
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

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def send_rich_email(subject, html_content, img_buffers, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    msg = MIMEMultipart('related')
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, receiver, Header(subject, 'utf-8')
    msg_alt = MIMEMultipart('alternative'); msg.attach(msg_alt)
    msg_alt.attach(MIMEText(html_content, 'html', 'utf-8'))
    for i, buf in enumerate(img_buffers):
        img = MIMEImage(buf.getvalue()); img.add_header('Content-ID', f'<chart_{i}>'); msg.attach(img)
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
    except Exception as e: print(f"❌ 邮件失败: {e}")

def get_match_weather(home_team, date_str):
    city = {'阿森纳': 'London', '曼联': 'Manchester', '利物浦': 'Liverpool', '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '拜仁慕尼黑': 'Munich'}.get(home_team, 'London')
    try:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            day = resp.json()['forecast']['forecastday'][0]['day']
            return day['condition']['text'], round(day['avgtemp_c'], 1)
    except: pass
    return "未知", 0

def generate_score_matrix(home_xg, away_xg, max_goals=7, rho=-0.15):
    def dixon_coles_tau(h, a):
        if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
        elif h == 0 and a == 1: return 1 + home_xg * rho
        elif h == 1 and a == 0: return 1 + away_xg * rho
        elif h == 1 and a == 1: return 1 - rho
        return 1.0
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[i][j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg) * dixon_coles_tau(i, j)
    matrix = matrix / np.sum(matrix)
    scores = [(f"{i}-{j}", matrix[i][j]) for i in range(max_goals + 1) for j in range(max_goals + 1)]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores, matrix

def get_total_goals_recommendation(prob_matrix, max_goals=7):
    goal_probs = {}
    for total_g in range(8):
        prob = 0
        for hg in range(total_g + 1):
            ag = total_g - hg
            if hg <= 7 and ag <= 7:
                prob += prob_matrix[hg][ag]
        goal_probs[str(total_g)] = prob
        
    prob_7_plus = 0
    for hg in range(8):
        for ag in range(8):
            if hg + ag >= 7:
                prob_7_plus += prob_matrix[hg][ag]
    goal_probs['7+'] = prob_7_plus
    
    sorted_goals = sorted(goal_probs.items(), key=lambda x: x[1], reverse=True)
    top2_list = [f"{k}球" for k, v in sorted_goals[:2]]
    return " / ".join(top2_list), sorted_goals[0][0] + "球"

def ai_adjust_probabilities(home_cn, away_cn, p_h, p_d, p_a, injury_info, odds_trend, knowledge, ref_info, coach_info):
    prompt = f"""你是一位量化风控总监。比赛：{home_cn} vs {away_cn}。
    基础概率：主胜 {p_h*100:.1f}%，平局 {p_d*100:.1f}%，客胜 {p_a*100:.1f}%。
    【伤停情报】: {injury_info}；【盘口异动】: {odds_trend}；裁判：{ref_info.get('name')}。
    请根据【经验库】，输出严格 JSON 格式微调概率：{{"p_h": 0.45, "p_d": 0.30, "p_a": 0.25, "reason": "理由"}}
    【经验库】：{knowledge}"""
    try:
        res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        match = re.search(r'\{.*\}', res.choices[0].message.content.strip(), re.DOTALL)
        if match:
            d = json.loads(match.group(0))
            nh, nd, na = float(d.get('p_h', p_h)), float(d.get('p_d', p_d)), float(d.get('p_a', p_a))
            total = nh + nd + na
            return nh/total, nd/total, na/total, d.get('reason', 'AI微调完成')
    except: pass
    return p_h, p_d, p_a, "AI未干预"

bankroll = 10000.0
kelly_multiplier = 0.5
if os.path.exists('bankroll.csv'):
    try:
        df_bank = pd.read_csv('bankroll.csv')
        bankroll = df_bank.iloc[-1]['当前资金']
        recent = df_bank.tail(10)
        if '盈亏' in recent.columns:
            wins = len(recent[recent['盈亏'] > 0])
            win_rate = wins / len(recent)
            if win_rate < 0.4: kelly_multiplier = 0.2 
            elif win_rate > 0.6: kelly_multiplier = 0.7
    except: pass

if not os.path.exists('daily_matches.csv'): exit()
df_next_round = pd.read_csv('daily_matches.csv')
df_next_round['主队'] = df_next_round['主队'].apply(translate_team_name)
df_next_round['客队'] = df_next_round['客队'].apply(translate_team_name)
df_next_round['datetime_parsed'] = pd.to_datetime(df_next_round['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
df_next_round['match_date_str'] = df_next_round['datetime_parsed'].dt.strftime('%Y-%m-%d')

tomorrow = datetime.now() + timedelta(days=1)
start_of_tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
end_of_tomorrow = start_of_tomorrow + timedelta(days=1)
df_next_round = df_next_round[(df_next_round['datetime_parsed'] >= start_of_tomorrow) & (df_next_round['datetime_parsed'] < end_of_tomorrow)]
df_next_round = df_next_round.sort_values('datetime_parsed')
if df_next_round.empty:
    print("⚠️ 未来 72 小时内无比赛。")
    html_report = f"""<html><body><div style="text-align: center; padding: 50px;">
        <h2 style="color: #2c3e50;">🛡️ 今日休战</h2>
        <p style="color: #666; font-size: 16px;">系统扫描了所有赛程，未来 72 小时内没有需要预测的足球赛事。</p>
    </div></body></html>"""
    send_rich_email("🛡️ 多联赛每日战报 (今日休战)", html_report, [])
    exit()

real_odds_dict = {}
if os.path.exists('real_odds.csv'):
    for _, r in pd.read_csv('real_odds.csv').iterrows():
        try: real_odds_dict[(pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d'), r['主队'], r['客队'])] = r
        except: pass

manual_odds_dict = {}
if os.path.exists('manual_odds.csv'):
    for _, r in pd.read_csv('manual_odds.csv').iterrows():
        try: manual_odds_dict[(str(r['比赛日期']).strip(), r['主队'], r['客队'])] = r
        except: pass

ref_dict, coach_dict = {}, {}
if os.path.exists('referee_stats.csv'):
    try:
        df_ref = pd.read_csv('referee_stats.csv')
        for _, r in df_ref.iterrows(): 
            ref_dict[(r['主队'], r['客队'])] = {'name': r['主裁判'], 'yellow': r['场均黄牌'], 'penalty': r['场均点球']}
    except: pass
if os.path.exists('coach_stats.csv'):
    try:
        df_coach = pd.read_csv('coach_stats.csv')
        for _, r in df_coach.iterrows(): 
            coach_dict[r['球队']] = {'style': r['教练风格']}
    except: pass

injury_dict, injury_impact = {}, {}
try:
    fpl_data = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15).json()
    teams_map = {t['id']: translate_team_name(t['name']) for t in fpl_data['teams']}
    for e in fpl_data['elements']:
        if (e['status'] in ['d', 'i', 's', 'u'] or (e.get('chance_of_playing_next_round') or 100) < 75) and (e.get('now_cost', 0) >= 50 or e.get('total_points', 0) >= 20):
            t_name = teams_map.get(e['team'])
            if t_name:
                injury_dict.setdefault(t_name, []).append(f"{e['web_name']}")
                injury_impact[t_name] = injury_impact.get(t_name, 0) + ((e.get('now_cost', 50) / 100.0) * 0.7)
except: pass

history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
df_hist = pd.read_csv(history_file)
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)
if os.path.exists('xg_data.csv'):
    df_xg = pd.read_csv('xg_data.csv')
    df_xg['date'] = pd.to_datetime(df_xg['date'])
    df_hist = pd.merge(df_hist, df_xg, on=['date', 'home_team_cn', 'away_team_cn'], how='left', suffixes=('', '_xg'))

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats, last_date = {}, {}
for _, row in df_hist.iterrows():
    h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [h, a]:
        if t not in team_stats: 
            team_stats[t] = {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]}
        if t not in last_date: last_date[t] = None
        
    act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
    act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
    
    team_stats[h]['xg'].append(act_h_xg); team_stats[h]['xga'].append(act_a_xg)
    team_stats[a]['xg'].append(act_a_xg); team_stats[a]['xga'].append(act_h_xg)
    team_stats[h]['home_xg'].append(act_h_xg); team_stats[h]['home_xga'].append(act_a_xg)
    team_stats[a]['away_xg'].append(act_a_xg); team_stats[a]['away_xga'].append(act_h_xg)
    
    team_stats[h]['opp_elo'].append(1500); team_stats[a]['opp_elo'].append(1500)
    team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    
    team_stats[h]['dates'].append(m_date); team_stats[a]['dates'].append(m_date)
    last_date[h] = m_date; last_date[a] = m_date

elo_dict = {}
if os.path.exists('elo_dict.pkl'): elo_dict = joblib.load('elo_dict.pkl')

knowledge_base = open('knowledge.txt', 'r', encoding='utf-8').read() if os.path.exists('knowledge.txt') else ""

model_h_lgb = joblib.load('epl_v31_home_goals_model_lgb.pkl')
model_a_lgb = joblib.load('epl_v31_away_goals_model_lgb.pkl')
model_h_xgb = joblib.load('epl_v31_home_goals_model_xgb.pkl')
model_a_xgb = joblib.load('epl_v31_away_goals_model_xgb.pkl')
calibrated_clf = joblib.load('epl_result_classifier.pkl')

jczq_picks_list = []
html_report, prediction_logs, img_buffers = "", [], []

for league in df_next_round['联赛'].unique():
    html_report += f"""<div style="background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 10px 20px; border-radius: 8px; margin-top: 30px; margin-bottom: 20px;"><h2 style="margin: 0; font-size: 22px;">🏆 {league}</h2></div>"""
    for _, match in df_next_round[df_next_round['联赛'] == league].iterrows():
        h_cn, a_cn = match['主队'], match['客队']
        match_date_str = match['match_date_str']
        m_time = pd.to_datetime(match['datetime_parsed']).strftime('%m月%d日 %H:%M')
        m_date = pd.to_datetime(match['datetime_parsed']).date()
        
        odds_row = real_odds_dict.get((match_date_str, h_cn, a_cn))
        manual_row = manual_odds_dict.get((match_date_str, h_cn, a_cn))
        use_odds = manual_row if manual_row is not None else odds_row
        has_real = False
        
        if use_odds is not None:
            real_h, real_d, real_a = use_odds['主胜赔率'], use_odds['平局赔率'], use_odds['客胜赔率']
            hc_line, hc_h_odd, hc_a_odd = use_odds.get('让球盘口', 0.0), use_odds.get('主让胜赔率', 0.0), use_odds.get('客受让胜赔率', 0.0)
            tl_line, over_odd, under_odd = use_odds.get('大小球盘口', 2.5), use_odds.get('大球赔率', 0.0), use_odds.get('小球赔率', 0.0)
            has_real = True
            trap_warning = ""
            if manual_row is not None and odds_row is not None:
                diff_h = abs(manual_row['主胜赔率'] - odds_row['主胜赔率']) / odds_row['主胜赔率']
                if diff_h > 0.15: trap_warning = f"⚠️ <b>数据异常：</b>国内赔率({manual_row['主胜赔率']})与国外锐利盘({odds_row['主胜赔率']})差异达 {diff_h*100:.1f}%，疑似机构在设陷阱。"
        else:
            real_h, real_d, real_a = 0, 0, 0
            hc_line, hc_h_odd, hc_a_odd = 0.0, 0.0, 0.0
            tl_line, over_odd, under_odd = 2.5, 0.0, 0.0
            has_real = False
            trap_warning = ""

        h = team_stats.get(h_cn, {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]})
        a = team_stats.get(a_cn, {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]})
        h_rest = (pd.Timestamp(m_date) - last_date[h_cn]).days if h_cn in last_date else 7
        a_rest = (pd.Timestamp(m_date) - last_date[a_cn]).days if a_cn in last_date else 7
        rest_diff = h_rest - a_rest
        
        h_recent_matches = sum(1 for d in h['dates'] if (pd.Timestamp(m_date) - d).days <= 14)
        a_recent_matches = sum(1 for d in a['dates'] if (pd.Timestamp(m_date) - d).days <= 14)
        
        h_xg = np.mean(h['xg'][-5:]) if h['xg'] else league_avg_goals
        a_xg = np.mean(a['xg'][-5:]) if a['xg'] else league_avg_goals
        h_xga = np.mean(h['xga'][-5:]) if h['xga'] else league_avg_goals
        a_xga = np.mean(a['xga'][-5:]) if a['xga'] else league_avg_goals
        
        h_home_xg = np.mean(h['home_xg'][-3:]) if h['home_xg'] else h_xg
        h_home_xga = np.mean(h['home_xga'][-3:]) if h['home_xga'] else h_xga
        a_away_xg = np.mean(a['away_xg'][-3:]) if a['away_xg'] else a_xg
        a_away_xga = np.mean(a['away_xga'][-3:]) if a['away_xga'] else a_xga
        
        h_sos = np.mean(h['opp_elo'][-5:]) if h['opp_elo'] else 1500
        a_sos = np.mean(a['opp_elo'][-5:]) if a['opp_elo'] else 1500
        h_pts = np.mean(h['pts'][-5:]) if h['pts'] else 1.0
        a_pts = np.mean(a['pts'][-5:]) if a['pts'] else 1.0
        
        h_elo = elo_dict.get(h_cn, 1500)
        a_elo = elo_dict.get(a_cn, 1500)
        
        feat = [
            h_elo, a_elo, h_elo - a_elo, 
            h_sos, a_sos, h_xg, a_xg, h_xga, a_xga, 
            h_home_xg, h_home_xga, a_away_xg, a_away_xga, 
            rest_diff, h_recent_matches, a_recent_matches
        ]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
        
        pred_h_xg = max(0.1, (model_h_lgb.predict(feat)[0] + model_h_xgb.predict(feat)[0]) / 2.0)
        pred_a_xg = max(0.1, (model_a_lgb.predict(feat)[0] + model_a_xgb.predict(feat)[0]) / 2.0)
        
        h_impact = injury_impact.get(h_cn, 0)
        a_impact = injury_impact.get(a_cn, 0)
        home_xg = pred_h_xg * max(0.6, 1 - h_impact * 0.1) 
        away_xg = pred_a_xg * max(0.6, 1 - a_impact * 0.1)
        
        w_text, w_temp = get_match_weather(h_cn, match_date_str)
        if "雨" in w_text or "雪" in w_text:
            home_xg *= 0.9
            away_xg *= 0.9

        scores_list, prob_matrix = generate_score_matrix(home_xg, away_xg, max_goals=7, rho=-0.15)
        
        p_h, p_d, p_a = np.sum(np.tril(prob_matrix, -1)), np.sum(np.diag(prob_matrix)), np.sum(np.triu(prob_matrix, 1))
        total_p = p_h + p_d + p_a
        p_h, p_d, p_a = p_h/total_p, p_d/total_p, p_a/total_p
        
        ref_info = ref_dict.get((h_cn, a_cn), {'name': '未公布', 'yellow': 0, 'penalty': 0})
        h_coach = coach_dict.get(h_cn, {'style': '攻守平衡'})
        a_coach = coach_dict.get(a_cn, {'style': '攻守平衡'})
        coach_info = {'h_style': h_coach['style'], 'a_style': a_coach['style']}
        
        h_inj_str = ','.join(injury_dict.get(h_cn, ['无']))
        a_inj_str = ','.join(injury_dict.get(a_cn, ['无']))
        injury_info = f"主队伤停: {h_inj_str}; 客队伤停: {a_inj_str}"
        
        odds_trend = "暂无盘口轨迹数据"
        p_h, p_d, p_a, ai_reason = ai_adjust_probabilities(h_cn, a_cn, p_h, p_d, p_a, injury_info, odds_trend, knowledge_base, ref_info, coach_info)
        
        predict_choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")
        oh, od, oa = (real_h, real_d, real_a) if has_real else (2.0, 3.3, 3.5)
        
        final_rec, bet_amt, split_msg = "观望", 0.0, ""
        ou_msg, hc_msg, ou_rec, hc_rec = "未开出", "未开出", "观望", "观望"
        
        # 恢复展示的凯利指数
        kelly_msg = "暂无真实赔率"
        
        if has_real:
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od-1)/(od-1), (p_a*oa-1)/(oa-1)
            kelly_msg = f"主胜 {max(0, kh)*100:.1f}% | 平局 {max(0, kd)*100:.1f}% | 客胜 {max(0, ka)*100:.1f}%"
            
            max_k = max(kh, kd, ka)
            if max_k > 0.02:
                b_choice = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (b_choice == "主胜" and p_h > 0.25) or (b_choice == "平局" and p_d > 0.25) or (b_choice == "客胜" and p_a > 0.25):
                    safe_k = min(max_k * kelly_multiplier, 0.05)
                    bet_amt, final_rec = bankroll * safe_k, b_choice
                    split_msg = f"推荐下注 {bet_amt:.2f}元"
                else: split_msg = "概率不足，建议空仓观望"
            else: split_msg = "模型认为无正期望价值"

            if pd.notna(tl_line) and tl_line > 0:
                prob_over = sum(prob_matrix[i][j] for i in range(8) for j in range(8) if i + j > tl_line)
                prob_under = sum(prob_matrix[i][j] for i in range(8) for j in range(8) if i + j < tl_line)
                ou_msg = f"盘口{tl_line}，大球{prob_over*100:.1f}% / 小球{prob_under*100:.1f}%"
                if prob_over * over_odd > 1.05: ou_rec = "大球 (高价值)"
                elif prob_under * under_odd > 1.05: ou_rec = "小球 (高价值)"
                
            if pd.notna(hc_line) and hc_line != 0:
                prob_hc_home = sum(prob_matrix[i][j] for i in range(8) for j in range(8) if i + hc_line > j)
                prob_hc_away = sum(prob_matrix[i][j] for i in range(8) for j in range(8) if i + hc_line < j)
                hc_msg = f"主让{hc_line}，主赢盘{prob_hc_home*100:.1f}% / 客赢盘{prob_hc_away*100:.1f}%"
                if prob_hc_home * hc_h_odd > 1.05: hc_rec = "主队赢盘"
                elif prob_hc_away * hc_a_odd > 1.05: hc_rec = "客队赢盘"
        else:
            final_rec = f"技术倾向：{predict_choice}"
            split_msg = "(无真实盘口，仅供观赛)"

        valid_scores = [s for s in scores_list if s[1] > 0.012]
        top3 = valid_scores[:3]
        top3_str = " | ".join([f"<b>{s[0]}</b> ({s[1]*100:.1f}%)" for s in top3])
        best_score = top3[0][0]

        total_goals_rec_str, best_goal = get_total_goals_recommendation(prob_matrix)

        if bet_amt > 0 or "高价值" in ou_rec or "高价值" in hc_rec:
            jczq_picks_list.append({
                '比赛时间': m_time, '赛事': league, '对阵': f"{h_cn} vs {a_cn}",
                '推荐': final_rec if bet_amt > 0 else "观望", '金额': round(bet_amt, 2) if bet_amt > 0 else 0,
                '比分': best_score,
                '总进球': total_goals_rec_str,
                '让球': hc_rec, '大小球': ou_rec
            })

        venue = f"{h_cn}主场" 

        prompt = f"""资深专家，点评(150字内)：比赛：{h_cn} vs {a_cn}。倾向：{predict_choice}。伤停：{injury_info}。大小球/让球：{ou_msg} / {hc_msg}。AI理由：{ai_reason}。以“推荐关注：{final_rec}”结尾。"""
        try: ai_comment = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False).choices[0].message.content.strip()
        except: ai_comment = "AI解析失败"

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))
        fig.patch.set_facecolor('#f8f9fa')
        
        labels = ['主胜', '平局', '客胜']
        probs = [p_h*100, p_d*100, p_a*100]
        colors = ['#4e79a7', '#f28e2b', '#e15759']
        bars = ax1.bar(labels, probs, color=colors, width=0.5, edgecolor='white', linewidth=1)
        ax1.set_ylim(0, 100)
        ax1.set_title(f"{h_cn} vs {a_cn} - 赛果概率", fontsize=12, fontweight='bold', color='#333')
        for bar in bars:
            yval = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2, yval + 2, f'{yval:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
        ax1.tick_params(axis='both', labelsize=10)
        
        ax2.barh(['客队', '主队'], [away_xg, home_xg], color=['#59a14f', '#e15759'], height=0.4)
        ax2.set_xlim(0, max(home_xg, away_xg) + 1)
        ax2.set_title("预期进球 (xG)", fontsize=12, fontweight='bold', color='#333')
        ax2.text(home_xg + 0.1, 1, f'{home_xg:.2f}', va='center', fontsize=11, fontweight='bold')
        ax2.text(away_xg + 0.1, 0, f'{away_xg:.2f}', va='center', fontsize=11, fontweight='bold')
        ax2.tick_params(axis='both', labelsize=10)

        plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); img_buffers.append(buf); plt.close(fig)

        prediction_logs.append({
            'date': m_date.strftime('%Y-%m-%d'), 'league': league, 'home_team': h_cn, 'away_team': a_cn,
            'predicted_result': final_rec, 'bet_amount': round(bet_amt, 2),
            'pred_prob_h': round(p_h, 4), 'pred_prob_d': round(p_d, 4), 'pred_prob_a': round(p_a, 4),
            'predicted_score': best_score, 'top3_scores': top3_str.replace("<b>", "").replace("</b>", ""),
            'odds_h': oh, 'odds_d': od, 'odds_a': oa, 'home_injuries': h_inj_str, 'away_injuries': a_inj_str
        })

        # 🌟 全面恢复核心数据展示
        html_report += f"""
        <div style="border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 25px; background-color: #ffffff; box-shadow: 0 4px 10px rgba(0,0,0,0.06);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; margin-bottom: 15px;">
                <h3 style="margin: 0; color: #2c3e50; font-size: 18px;">⏰ {m_time} <span style="color: #000; margin-left: 10px; font-size: 20px;">{h_cn} vs {a_cn}</span></h3>
                <span style="background-color: #e8f4fd; color: #1e3c72; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px;">{venue}</span>
            </div>
            
            <img src='cid:chart_{len(img_buffers)-1}' width='100%' style='border-radius: 6px; margin-bottom: 15px;'>

            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <div style="flex: 1; background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; border-radius: 4px;">
                    <span style="font-size: 13px; color: #856404; font-weight: bold; display: block; margin-bottom: 5px;">🎯 首选比分</span>
                    <span style="font-size: 22px; color: #d9534f; font-weight: bold;">{best_score}</span>
                    <span style="font-size: 12px; color: #666; margin-left: 8px;">防冷: {top3_str}</span>
                </div>
                <div style="flex: 1; background-color: #e8f4fd; border-left: 4px solid #3498db; padding: 10px; border-radius: 4px;">
                    <span style="font-size: 13px; color: #2980b9; font-weight: bold; display: block; margin-bottom: 5px;">⚽ 总进球数</span>
                    <span style="font-size: 20px; color: #1e3c72; font-weight: bold;">{total_goals_rec_str}</span>
                </div>
            </div>

            {f"<div style='background-color: #f8d7da; color: #721c24; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; font-weight: bold;'>{trap_warning}</div>" if trap_warning else ""}

            <div style="display: flex; flex-wrap: wrap; font-size: 13px; line-height: 1.8; color: #444; margin-bottom: 12px; background-color: #f8f9fa; padding: 10px; border-radius: 6px;">
                <div style="width: 50%;">💪 <b>Elo:</b> 主 {h_elo:.0f} / 客 {a_elo:.0f}</div>
                <div style="width: 50%;">🌤️ <b>天气:</b> {w_text} {w_temp}℃</div>
                <div style="width: 50%;">⏱️ <b>休息:</b> 主 {h_rest} 天 / 客 {a_rest} 天</div>
                <div style="width: 50%;">🧑‍⚖️ <b>裁判:</b> {ref_info['name']}</div>
                <div style="width: 100%; color: #d9534f; margin-top: 5px;"><b>🚨 伤停:</b> 主[{h_inj_str}] / 客[{a_inj_str}]</div>
            </div>

            <div style="background-color: #fff; padding: 10px; border-radius: 6px; border: 1px solid #eee; font-size: 13px; margin-bottom: 12px;">
                <p style="margin: 0 0 5px 0;"><b>📊 核心数据 (近5场):</b> 主队 [进 {h_xg*5:.1f} / 失 {h_xga*5:.1f}] | 客队 [进 {a_xg*5:.1f} / 失 {a_xga*5:.1f}]</p>
                <p style="margin: 0;"><b>💰 凯利建议:</b> {kelly_msg}</p>
            </div>

            <div style="display: flex; justify-content: space-around; text-align: center; font-size: 13px; margin-bottom: 15px;">
                <div><span style="color: #666;">亚盘</span> <b style="color: #1e3c72;">{hc_rec} ({hc_msg})</b></div>
                <div><span style="color: #666;">大小球</span> <b style="color: #1e3c72;">{ou_rec} ({ou_msg})</b></div>
            </div>

            <div style="padding: 12px; border: 1px dashed #ccc; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; background-color: #fafafa;">
                <div>
                    <span style="font-size: 15px;"><b>💡 最终结论：</b><span style="font-size: 22px; color: #d9534f; font-weight: bold; margin-right: 10px;">{final_rec}</span></span>
                    <span style="font-size: 13px; color: #666;">{split_msg}</span>
                </div>
            </div>

            <p style="margin-top: 15px; margin-bottom: 0; color: #555; font-size: 13px; line-height: 1.6;"><b>🧠 AI点评：</b>{ai_comment}</p>
        </div>
        """

final_html = """
<html>
<head>
<style>
    body { font-family: 'Helvetica Neue', Helvetica, Arial, 'Microsoft YaHei', sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; }
    .container { max-width: 900px; margin: auto; }
    .header { text-align: center; margin-bottom: 30px; }
    .header h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; font-size: 28px; margin: 0; }
    .report-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden; }
    .report-table th { background-color: #2c3e50; color: #ffffff; font-weight: bold; padding: 12px 10px; text-align: center; border-bottom: 2px solid #1a252f; }
    .report-table td { padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: center; color: #333; }
    .report-table tr:nth-child(even) { background-color: #f8f9fa; }
    .report-table tr:hover { background-color: #e8f4fd; }
    .section-title { text-align: center; color: #d35400; font-size: 20px; margin-top: 0; margin-bottom: 10px; border-bottom: 2px solid #f39c12; display: inline-block; padding-bottom: 5px; }
</style>
</head>
<body>
<div class="container">
"""

final_html += "<h1>⚽ 明日赛事量化预测 (V44.0 极客进击版)</h1>"

if jczq_picks_list:
    df_picks = pd.DataFrame(jczq_picks_list)
    df_picks.to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')
    picks_html = df_picks.to_html(index=False, border=0, classes='report-table', justify='center', escape=False)
    picks_html = picks_html.replace('<td>推荐</td>', '<th>推荐</th>')
    
    final_html += f"""
    <div style='background-color: #fff; padding: 20px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); border-top: 5px solid #f39c12;'>
        <div style="text-align: center; margin-bottom: 15px;">
            <h3 class='section-title'>🎯 今日竞彩狙击清单</h3>
        </div>
        {picks_html}
    </div>
    """
else:
    final_html += """
    <div style='background-color: #fdf2f2; border-top: 5px solid #e74c3c; padding: 20px; border-radius: 10px; margin-bottom: 30px; text-align: center; box-shadow: 0 4px 10px rgba(0,0,0,0.05);'>
        <h3 style='color: #c0392b; margin-top: 0; font-size: 20px;'>🛑 今日无狙击目标</h3>
        <p style='color: #c0392b; font-size: 14px;'>系统扫描了所有明日比赛，因无赔率或期望价值不足，建议空仓观望。</p>
    </div>
    """
    pd.DataFrame(columns=['比赛时间', '赛事', '对阵', '推荐', '金额', '比分', '总进球', '让球', '大小球']).to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')

final_html += html_report
final_html += "</div></body></html>"

log_df = pd.DataFrame(prediction_logs)
if os.path.exists('predictions_log.csv'):
    old = pd.read_csv('predictions_log.csv')
    log_df = pd.concat([old, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

open('dashboard.html', 'w', encoding='utf-8').write(final_html)
send_rich_email("V44.0 明日赛事量化预测 (极客进击版)", final_html, img_buffers)
