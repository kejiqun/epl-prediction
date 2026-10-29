import pandas as pd
import numpy as np
import requests
import joblib
import os
import io
import json
import re
from scipy.stats import poisson, nbinom, norm
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

# 保证结果可复现
np.random.seed(42)

print("==================================================")
print("🚀 启动 V130.0 负二项分布与共识裁决引擎")
print("==================================================")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

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
        print("✅ 邮件发送成功！")
    except Exception as e: print(f"❌ 邮件失败: {e}")

def get_match_weather(home_team, date_str):
    city = {'阿森纳': 'London', '曼联': 'Manchester', '利物浦': 'Liverpool', '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '拜仁慕尼黑': 'Munich', '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin', '那不勒斯': 'Naples', '罗马': 'Rome'}.get(home_team, 'London')
    try:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            day = resp.json()['forecast']['forecastday'][0]['day']
            return day['condition']['text'], round(day['avgtemp_c'], 1)
    except: pass
    return "未知", 0

# 🌟 核心升级 1：负二项分布蒙特卡洛引擎 (防极端比分)
def negative_binomial_monte_carlo(home_xg, away_xg, simulations=10000):
    """
    使用负二项分布来模拟，解决泊松分布的过度离散问题（适合捕捉大比分冷门）。
    r 为离散参数，越小方差越大（越容易爆冷）。
    """
    r_param = 5.0  # 离散因子，可通过历史数据拟合优化
    
    # 生成服从负二项分布的随机数
    home_goals_sim = nbinom.rvs(r_param, r_param / (r_param + home_xg), size=simulations)
    away_goals_sim = nbinom.rvs(r_param, r_param / (r_param + away_xg), size=simulations)
    
    # 加入协方差相关性修正
    z = np.random.multivariate_normal([0, 0], [[1.0, 0.15], [0.15, 1.0]], simulations)
    home_goals_sim = np.clip(home_goals_sim + np.where(z[:,0] > 1.5, 1, 0), 0, 10)
    away_goals_sim = np.clip(away_goals_sim + np.where(z[:,1] > 1.5, 1, 0), 0, 10)

    home_wins = np.sum(home_goals_sim > away_goals_sim) / simulations
    draws = np.sum(home_goals_sim == away_goals_sim) / simulations
    away_wins = np.sum(home_goals_sim < away_goals_sim) / simulations
    
    score_counts = {}
    for h, a in zip(home_goals_sim, away_goals_sim):
        score_str = f"{int(h)}-{int(a)}"
        score_counts[score_str] = score_counts.get(score_str, 0) + 1
        
    sorted_scores = sorted(score_counts.items(), key=lambda x: x[1], reverse=True)
    score_probs = [(score, count / simulations) for score, count in sorted_scores]
    
    return home_wins, draws, away_wins, score_probs, home_goals_sim, away_goals_sim

def get_total_goals_recommendation_mc(home_goals_sim, away_goals_sim, tl_line=2.5):
    total_goals = home_goals_sim + away_goals_sim
    prob_over = np.sum(total_goals > tl_line) / len(total_goals)
    prob_under = np.sum(total_goals < tl_line) / len(total_goals)
    
    goal_counts = {}
    for g in total_goals:
        goal_counts[str(int(g))] = goal_counts.get(str(int(g)), 0) + 1
    sorted_goals = sorted(goal_counts.items(), key=lambda x: x[1], reverse=True)
    top2_goals = [f"{k}球" for k, v in sorted_goals[:2] if int(k) <= 7]
    
    return prob_over, prob_under, " / ".join(top2_goals)

# ================= 数据装载与特征构建 =================
bankroll = 10000.0
kelly_multiplier = 0.2
if os.path.exists('bankroll.csv'):
    try:
        df_bank = pd.read_csv('bankroll.csv')
        bankroll = df_bank.iloc[-1]['当前资金']
        recent = df_bank.tail(10)
        if '盈亏' in recent.columns:
            win_rate = len(recent[recent['盈亏'] > 0]) / len(recent)
            if win_rate < 0.4: kelly_multiplier = 0.1 
            elif win_rate > 0.6: kelly_multiplier = 0.3
    except: pass

if not os.path.exists('all_leagues_matches.csv'): exit()

df_auto = pd.DataFrame()
if os.path.exists('daily_matches.csv'):
    df_auto = pd.read_csv('daily_matches.csv')
    df_auto['主队'] = df_auto['主队'].apply(translate_team_name)
    df_auto['客队'] = df_auto['客队'].apply(translate_team_name)
    df_auto['datetime_parsed'] = pd.to_datetime(df_auto['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)

manual_odds_dict = {}
df_manual = pd.DataFrame()
if os.path.exists('manual_odds.csv'):
    try:
        df_manual_raw = pd.read_csv('manual_odds.csv')
        df_manual_raw['比赛时间_str'] = df_manual_raw['比赛日期'].astype(str).str.strip() + ' ' + df_manual_raw['比赛时间'].astype(str).str.strip()
        df_manual_raw['datetime_parsed'] = pd.to_datetime(df_manual_raw['比赛时间_str'])
        df_manual_raw['主队'] = df_manual_raw['主队'].apply(translate_team_name)
        df_manual_raw['客队'] = df_manual_raw['客队'].apply(translate_team_name)
        for _, r in df_manual_raw.iterrows():
            manual_odds_dict[(r['datetime_parsed'].strftime('%Y-%m-%d'), r['主队'], r['客队'])] = r
        df_manual['主队'] = df_manual_raw['主队']
        df_manual['客队'] = df_manual_raw['客队']
        df_manual['datetime_parsed'] = df_manual_raw['datetime_parsed']
        df_manual['联赛'] = '手动精选'
        df_manual['比赛时间'] = df_manual['datetime_parsed']
    except: pass

df_next_round = pd.concat([df_auto, df_manual]).drop_duplicates(subset=['主队', '客队', 'datetime_parsed'], keep='last')
df_next_round['match_date_str'] = df_next_round['datetime_parsed'].dt.strftime('%Y-%m-%d')

now_ts = pd.Timestamp.now()
end_window = now_ts + pd.Timedelta(hours=24)
df_next_round = df_next_round[(df_next_round['datetime_parsed'] > now_ts) & (df_next_round['datetime_parsed'] <= end_window)].sort_values('datetime_parsed')

if df_next_round.empty: exit()

real_odds_dict = {}
if os.path.exists('real_odds.csv'):
    for _, r in pd.read_csv('real_odds.csv').iterrows():
        try: real_odds_dict[(pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d'), translate_team_name(r['主队']), translate_team_name(r['客队']))] = r
        except: pass

ref_dict = {}
if os.path.exists('referee_stats.csv'):
    try:
        df_ref = pd.read_csv('referee_stats.csv')
        for _, r in df_ref.iterrows(): ref_dict[(r['主队'], r['客队'])] = {'name': r['主裁判']}
    except: pass

injury_dict, injury_impact_att, injury_impact_def = {}, {}, {}
try:
    fpl_data = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15).json()
    teams_map = {t['id']: translate_team_name(t['name']) for t in fpl_data['teams']}
    for e in fpl_data['elements']:
        if (e['status'] in ['d', 'i', 's', 'u'] or (e.get('chance_of_playing_next_round') or 100) < 75) and (e.get('now_cost', 0) >= 50 or e.get('total_points', 0) >= 20):
            t_name = teams_map.get(e['team'])
            if t_name:
                injury_dict.setdefault(t_name, []).append(f"{e['web_name']}")
                pos = e.get('element_type')
                cost_weight = e.get('now_cost', 50) / 100.0
                if pos in [3, 4]: injury_impact_att[t_name] = injury_impact_att.get(t_name, 0) + cost_weight * 0.15
                elif pos in [1, 2]: injury_impact_def[t_name] = injury_impact_def.get(t_name, 0) + cost_weight * 0.15
except: pass

print("⏳ 正在构建特征库与时间衰减模型...")
df_hist = pd.read_csv('all_leagues_matches.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)
df_hist = df_hist.sort_values('date')

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats, last_date = {}, {}
for _, row in df_hist.iterrows():
    h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [h, a]:
        if t not in team_stats: team_stats[t] = {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[], 'count': 0}
        if t not in last_date: last_date[t] = None
    team_stats[h]['count'] += 1; team_stats[a]['count'] += 1
    team_stats[h]['xg'].append(row['home_goals']); team_stats[h]['xga'].append(row['away_goals'])
    team_stats[a]['xg'].append(row['away_goals']); team_stats[a]['xga'].append(row['home_goals'])
    team_stats[h]['home_xg'].append(row['home_goals']); team_stats[h]['home_xga'].append(row['away_goals'])
    team_stats[a]['away_xg'].append(row['away_goals']); team_stats[a]['away_xga'].append(row['home_goals'])
    team_stats[h]['opp_elo'].append(1500); team_stats[a]['opp_elo'].append(1500)
    team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[h]['dates'].append(m_date); team_stats[a]['dates'].append(m_date)
    last_date[h] = m_date; last_date[a] = m_date

elo_dict = joblib.load('elo_dict.pkl') if os.path.exists('elo_dict.pkl') else {}
knowledge_base = open('knowledge.txt', 'r', encoding='utf-8').read() if os.path.exists('knowledge.txt') else ""

model_h_lgb = joblib.load('epl_v31_home_goals_model_lgb.pkl')
model_a_lgb = joblib.load('epl_v31_away_goals_model_lgb.pkl')
model_h_xgb = joblib.load('epl_v31_home_goals_model_xgb.pkl')
model_a_xgb = joblib.load('epl_v31_away_goals_model_xgb.pkl')

jczq_picks_list = []
prediction_logs = [] 
html_report_cards = ""
img_buffers = []

print("🚀 开始执行 V130.0 负二项分布与共识监控...")
for league in df_next_round['联赛'].unique():
    html_report_cards += f"""<div style="background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 10px 20px; border-radius: 8px; margin-top: 30px; margin-bottom: 20px;"><h2 style="margin: 0; font-size: 22px;">🏆 {league}</h2></div>"""
    
    for _, match in df_next_round[df_next_round['联赛'] == league].iterrows():
        h_cn, a_cn = match['主队'], match['客队']
        match_date_str = match['match_date_str']
        m_time = pd.to_datetime(match['datetime_parsed']).strftime('%m月%d日 %H:%M')
        m_date = pd.to_datetime(match['datetime_parsed']).date()
        
        if team_stats.get(h_cn, {'count': 0})['count'] < 3 or team_stats.get(a_cn, {'count': 0})['count'] < 3: 
            continue
            
        manual_row = manual_odds_dict.get((match_date_str, h_cn, a_cn))
        auto_row = real_odds_dict.get((match_date_str, h_cn, a_cn))
        use_odds = manual_row if manual_row is not None else auto_row
        odds_source = "手动体彩盘" if manual_row is not None else ("自动海外盘" if auto_row is not None else "无赔率")
        
        has_real = False
        if use_odds is not None:
            try:
                real_h, real_d, real_a = float(use_odds['主胜赔率']), float(use_odds['平局赔率']), float(use_odds['客胜赔率'])
                hc_line, hc_h_odd, hc_a_odd = float(use_odds.get('让球盘口', 0.0)), float(use_odds.get('主让胜赔率', 0.0)), float(use_odds.get('客受让胜赔率', 0.0))
                tl_line, over_odd, under_odd = float(use_odds.get('大小球盘口', 2.5)), float(use_odds.get('大球赔率', 0.0)), float(use_odds.get('小球赔率', 0.0))
                has_real = True
            except:
                real_h, real_d, real_a, hc_line, hc_h_odd, hc_a_odd, tl_line, over_odd, under_odd = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.5, 0.0, 0.0
        else:
            real_h, real_d, real_a, hc_line, hc_h_odd, hc_a_odd, tl_line, over_odd, under_odd = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.5, 0.0, 0.0

        h = team_stats.get(h_cn, {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]})
        a = team_stats.get(a_cn, {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]})
        
        h_rest = (pd.Timestamp(m_date) - last_date[h_cn]).days if h_cn in last_date else 7
        a_rest = (pd.Timestamp(m_date) - last_date[a_cn]).days if a_cn in last_date else 7
        rest_diff = h_rest - a_rest
        
        h_recent = sum(1 for d in h['dates'] if (pd.Timestamp(m_date) - d).days <= 14)
        a_recent = sum(1 for d in a['dates'] if (pd.Timestamp(m_date) - d).days <= 14)
        
        def get_decay_mean(arr, decay=0.7):
            if not arr: return league_avg_goals
            arr = np.array(arr)
            weights = np.array([decay ** (len(arr) - 1 - i) for i in range(len(arr))])
            weights = weights / np.sum(weights)
            return np.sum(arr * weights)

        h_xg = get_decay_mean(h['xg'][-5:]) if h['xg'] else league_avg_goals
        a_xg = get_decay_mean(a['xg'][-5:]) if a['xg'] else league_avg_goals
        h_xga = get_decay_mean(h['xga'][-5:]) if h['xga'] else league_avg_goals
        a_xga = get_decay_mean(a['xga'][-5:]) if a['xga'] else league_avg_goals
        
        h_h_xg = np.mean(h['home_xg'][-3:]) if h['home_xg'] else h_xg
        h_h_xga = np.mean(h['home_xga'][-3:]) if h['home_xga'] else h_xga
        a_a_xg = np.mean(a['away_xg'][-3:]) if a['away_xg'] else a_xg
        a_a_xga = np.mean(a['away_xga'][-3:]) if a['away_xga'] else a_xga
        
        h_sos = np.mean(h['opp_elo'][-5:]) if h['opp_elo'] else 1500
        a_sos = np.mean(a['opp_elo'][-5:]) if a['opp_elo'] else 1500
        h_elo = elo_dict.get(h_cn, 1500)
        a_elo = elo_dict.get(a_cn, 1500)
        
        feat = [
            h_elo, a_elo, h_elo - a_elo, h_sos, a_sos, 
            h_xg, a_xg, h_xga, a_xga, h_h_xg, h_h_xga, a_a_xg, a_a_xga, 
            rest_diff, h_recent, a_recent
        ]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
        
        # 🌟 核心升级 2：模型共识机制 (一致性检测)
        pred_h_lgb = model_h_lgb.predict(feat)[0]
        pred_h_xgb = model_h_xgb.predict(feat)[0]
        pred_a_lgb = model_a_lgb.predict(feat)[0]
        pred_a_xgb = model_a_xgb.predict(feat)[0]
        
        # 计算模型分歧度
        h_divergence = abs(pred_h_lgb - pred_h_xgb)
        a_divergence = abs(pred_a_lgb - pred_a_xgb)
        
        consensus_penalty = 1.0
        consensus_warning = ""
        if h_divergence > 0.4 or a_divergence > 0.4:
            consensus_penalty = 0.8 # 惩罚 xG 期望
            consensus_warning = "⚠️ 模型分歧度过高：LGB与XGB对比赛理解不一致，强制削减预期进球置信度。"

        pred_h_xg = max(0.1, (pred_h_lgb + pred_h_xgb) / 2.0) * consensus_penalty
        pred_a_xg = max(0.1, (pred_a_lgb + pred_a_xgb) / 2.0) * consensus_penalty
        
        h_att_pen = 1 - injury_impact_att.get(h_cn, 0)
        h_def_pen = 1 - injury_impact_def.get(h_cn, 0)
        a_att_pen = 1 - injury_impact_att.get(a_cn, 0)
        a_def_pen = 1 - injury_impact_def.get(a_cn, 0)
        
        home_xg = pred_h_xg * max(0.5, h_att_pen) + (pred_a_xg * (1 - max(0.5, a_def_pen)) * 0.2)
        away_xg = pred_a_xg * max(0.5, a_att_pen) + (pred_h_xg * (1 - max(0.5, h_def_pen)) * 0.2)
        
        w_text, w_temp = get_match_weather(h_cn, match_date_str)
        if "雨" in w_text or "雪" in w_text:
            home_xg *= 0.9; away_xg *= 0.9

        # 🌟 核心升级 3：盘口反推约束 (防止模型自嗨)
        reverse_warning = ""
        if has_real and pd.notna(tl_line) and tl_line > 0:
            model_total_xg = home_xg + away_xg
            if abs(model_total_xg - tl_line) > 1.0:
                reverse_warning = f"⚠️ 预期总进球({model_total_xg:.1f})与机构盘口({tl_line})偏离过大，已强制回归盘口均值。"
                # 强制拉回盘口附近
                scale_factor = tl_line / model_total_xg
                home_xg *= scale_factor
                away_xg *= scale_factor

        # 执行负二项分布模拟
        p_h, p_d, p_a, score_probs, h_sim, a_sim = negative_binomial_monte_carlo(home_xg, away_xg, simulations=10000)
        
        trap_warning = ""
        final_rec, bet_amt, split_msg = "观望", 0.0, ""
        odds_conflict = ""
        
        if has_real:
            margin = 1/real_h + 1/real_d + 1/real_a
            implied_h, implied_d, implied_a = (1/real_h)/margin, (1/real_d)/margin, (1/real_a)/margin
            
            if pd.notna(hc_line) and hc_line != 0:
                implied_ah_home = 0.5 + hc_line * 0.1
                if abs(implied_h - implied_ah_home) > 0.15:
                    odds_conflict = f"⚠️ 欧亚盘口存在矛盾：欧赔隐含概率({implied_h*100:.1f}%)与亚盘走势不符。"
            
            p_h, p_d, p_a = p_h * 0.6 + implied_h * 0.4, p_d * 0.6 + implied_d * 0.4, p_a * 0.6 + implied_a * 0.4
            p_h, p_d, p_a = p_h/(p_h+p_d+p_a), p_d/(p_h+p_d+p_a), p_a/(p_h+p_d+p_a)
            
            if p_h - implied_h > 0.12: trap_warning = "⚠️ 冷门警报：主胜概率异常，疑似诱盘。"
            elif p_a - implied_a > 0.12: trap_warning = "⚠️ 冷门警报：客胜概率异常，疑似诱盘。"

            predict_choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")
            
            if predict_choice == "平局" and (home_xg + away_xg) > 2.8:
                predict_choice = "主胜" if h_elo > a_elo else "客胜"

            oh, od, oa = real_h, real_d, real_a
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od-1)/(od-1), (p_a*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            
            if max_k > 0.02 and "冷门" not in trap_warning and not odds_conflict:
                b_choice = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (b_choice == "主胜" and p_h > 0.25) or (b_choice == "平局" and p_d > 0.25) or (b_choice == "客胜" and p_a > 0.25):
                    safe_k = min(max_k * kelly_multiplier, 0.05)
                    bet_amt, final_rec = bankroll * safe_k, b_choice
                    split_msg = f"推荐下注 {bet_amt:.2f}元"
                else: split_msg = "概率不足，空仓观望"
            else: 
                split_msg = "触及风控红线，放弃下注"
                
            if pd.notna(tl_line) and tl_line > 0:
                prob_over, prob_under, ou_msg = get_total_goals_recommendation_mc(h_sim, a_sim, tl_line)
                if prob_over * over_odd > 1.05: ou_rec = "大球"
                elif prob_under * under_odd > 1.05: ou_rec = "小球"
        else:
            final_rec = f"技术倾向：{predict_choice}"
            bet_amt = 0.0
            split_msg = "(无盘口)"
            oh, od, oa = 2.0, 3.3, 3.5

        top3 = score_probs[:3]
        top3_str = " | ".join([f"{s[0]} ({s[1]*100:.1f}%)" for s in top3])
        best_score = top3[0][0]
        _, _, total_goals_rec_str = get_total_goals_recommendation_mc(h_sim, a_sim, 2.5)

        if has_real and (bet_amt > 0 or "高价值" in locals().get('ou_rec', '')):
            jczq_picks_list.append({
                '比赛时间': m_time, '赛事': league, '对阵': f"{h_cn} vs {a_cn}",
                '推荐': final_rec, '金额': round(bet_amt, 2) if bet_amt > 0 else 0,
                '比分': best_score, '总进球': total_goals_rec_str, '大小球': locals().get('ou_rec', '观望')
            })

        # 🌟 核心升级 4：AI 裁判长机制 (一票否决)
        prompt_referee = f"""比赛：{h_cn} vs {a_cn}。模型倾向【{predict_choice}】。
        关键信息：{consensus_warning} {trap_warning} {odds_conflict} {reverse_warning}。
        伤停：主[{','.join(injury_dict.get(h_cn, ['无']))}] 客[{','.join(injury_dict.get(a_cn, ['无']))}]。
        作为裁判长，请用80字总结上述风险。如果风险极大，请在最后加上“【裁判长否决：建议放弃本场】”。否则，请以“推荐关注：{final_rec}”结尾。"""
        try: ai_comment = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt_referee}], stream=False).choices[0].message.content.strip()
        except: ai_comment = "解析失败"

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))
        fig.patch.set_facecolor('#f8f9fa')
        ax1.bar(['主胜', '平局', '客胜'], [p_h*100, p_d*100, p_a*100], color=['#4e79a7', '#f28e2b', '#e15759'], width=0.5)
        ax1.set_ylim(0, 100); ax1.set_title("负二项分布融合胜率", fontsize=12, fontweight='bold')
        for i, v in enumerate([p_h*100, p_d*100, p_a*100]): ax1.text(i, v + 2, f'{v:.1f}%', ha='center', fontweight='bold')
        ax2.barh(['客队', '主队'], [away_xg, home_xg], color=['#59a14f', '#e15759'], height=0.4)
        ax2.set_title("预期进球 (xG)", fontsize=12, fontweight='bold')
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); img_buffers.append(buf); plt.close(fig)

        prediction_logs.append({
            'date': m_date.strftime('%Y-%m-%d'), 'league': league, 'home_team': h_cn, 'away_team': a_cn,
            'predicted_result': final_rec, 'bet_amount': round(bet_amt, 2),
            'predicted_score': best_score, 'odds_h': oh, 'odds_d': od, 'odds_a': oa,
            'home_injuries': ','.join(injury_dict.get(h_cn, ['无'])), 'away_injuries': ','.join(injury_dict.get(a_cn, ['无']))
        })

        html_report_cards += f"""
        <div style="border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 25px; background-color: #ffffff; box-shadow: 0 4px 10px rgba(0,0,0,0.06);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; margin-bottom: 15px;">
                <h3 style="margin: 0; color: #2c3e50; font-size: 18px;">⏰ {m_time} <span style="color: #000; margin-left: 10px; font-size: 20px;">{h_cn} vs {a_cn}</span></h3>
                <span style="background-color: #e8f4fd; color: #1e3c72; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px;">{odds_source}</span>
            </div>
            <img src='cid:chart_{len(img_buffers)-1}' width='100%' style='border-radius: 6px; margin-bottom: 15px;'>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <div style="flex: 1; background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; border-radius: 4px;">
                    <span style="font-size: 13px; color: #856404; font-weight: bold; display: block; margin-bottom: 5px;">🎯 负二项首选比分</span>
                    <span style="font-size: 22px; color: #d9534f; font-weight: bold;">{best_score}</span>
                    <span style="font-size: 12px; color: #666; margin-left: 8px;">防冷: {top3_str}</span>
                </div>
                <div style="flex: 1; background-color: #e8f4fd; border-left: 4px solid #3498db; padding: 10px; border-radius: 4px;">
                    <span style="font-size: 13px; color: #2980b9; font-weight: bold; display: block; margin-bottom: 5px;">⚽ 总进球数</span>
                    <span style="font-size: 20px; color: #1e3c72; font-weight: bold;">{total_goals_rec_str}</span>
                </div>
            </div>
            {f"<div style='background-color: #fff3cd; color: #856404; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; font-weight: bold;'>{consensus_warning}</div>" if consensus_warning else ""}
            {f"<div style='background-color: #fff3cd; color: #856404; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; font-weight: bold;'>{reverse_warning}</div>" if reverse_warning else ""}
            {f"<div style='background-color: #f8d7da; color: #721c24; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; font-weight: bold;'>{trap_warning}</div>" if "冷门" in trap_warning else ""}
            {f"<div style='background-color: #fff3cd; color: #856404; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; font-weight: bold;'>{odds_conflict}</div>" if odds_conflict else ""}
            <div style="display: flex; flex-wrap: wrap; font-size: 13px; line-height: 1.8; color: #444; margin-bottom: 12px; background-color: #f8f9fa; padding: 10px; border-radius: 6px;">
                <div style="width: 50%;">💪 <b>Elo:</b> 主 {h_elo:.0f} / 客 {a_elo:.0f}</div>
                <div style="width: 50%;">🌤️ <b>天气:</b> {w_text} {w_temp}℃</div>
                <div style="width: 50%;">⏱️ <b>休息:</b> 主 {h_rest} 天 / 客 {a_rest} 天</div>
                <div style="width: 50%;">🧑‍⚖️ <b>裁判:</b> {ref_dict.get((h_cn, a_cn), {'name': '未公布'})['name']}</div>
                <div style="width: 100%; color: #d9534f; margin-top: 5px;"><b>🚨 伤停:</b> 主[{','.join(injury_dict.get(h_cn, ['无']))}] / 客[{','.join(injury_dict.get(a_cn, ['无']))}]</div>
            </div>
            <div style="padding: 12px; border: 1px dashed #ccc; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; background-color: #fafafa;">
                <div><span style="font-size: 15px;"><b>💡 预测结果：</b><span style="font-size: 22px; color: #d9534f; font-weight: bold; margin-right: 10px;">{predict_choice}</span></span></div>
            </div>
            <p style="margin-top: 15px; margin-bottom: 0; color: #555; font-size: 13px; line-height: 1.6;"><b>🧠 AI裁判长总结：</b>{ai_comment}</p>
        </div>
        """

final_html = f"""<html><head><style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; }}
    .container {{ max-width: 900px; margin: auto; }}
    h1 {{ text-align: center; color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; }}
    .report-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden; }}
    .report-table th {{ background-color: #2c3e50; color: #ffffff; padding: 12px; text-align: center; }}
    .report-table td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: center; }}
</style></head><body><div class="container">
<h1>⚽ 今日竞彩全景预测与狙击清单 (V130.0 终极裁决版)</h1>
<h2 style='color: #e74c3c; border-bottom: 2px solid #e74c3c;'>🎯 Part 1: 今日竞彩狙击清单</h2>
"""
if jczq_picks_list:
    df_picks = pd.DataFrame(jczq_picks_list)
    df_picks.to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')
    final_html += f"<div style='background-color: #fff; padding: 20px; border-radius: 10px; border-top: 5px solid #f39c12;'>{df_picks.to_html(index=False, border=0, classes='report-table')}</div>"
else:
    final_html += "<div style='background-color: #fdf2f2; border-top: 5px solid #e74c3c; padding: 20px; text-align: center;'><h3 style='color: #c0392b;'>🛑 今日无高价值狙击目标</h3><p style='color: #c0392b;'>系统严格执行纪律：因无真实赔率或期望不足，拒绝强行出单。</p></div>"
    pd.DataFrame(columns=['比赛时间', '赛事', '对阵', '推荐', '金额', '比分', '总进球', '大小球']).to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')

final_html += "<h2 style='color: #2980b9; border-bottom: 2px solid #2980b9; margin-top: 40px;'>📊 Part 2: 今日全部比赛全景预测分析</h2>"
final_html += html_report_cards
final_html += "</div></body></html>"

log_df = pd.DataFrame(prediction_logs)
if not log_df.empty:
    if os.path.exists('predictions_log.csv'):
        old = pd.read_csv('predictions_log.csv')
        log_df = pd.concat([old, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
    log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

open('dashboard.html', 'w', encoding='utf-8').write(final_html)
send_rich_email("⚽ 今日竞彩全景预测与狙击清单 (V130.0 终极裁决版)", final_html, img_buffers)
