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

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
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
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, receiver, Header(subject, 'utf-8')
    msg_alt = MIMEMultipart('alternative'); msg.attach(msg_alt)
    msg_alt.attach(MIMEText(html_content, 'html', 'utf-8'))
    for i, buf in enumerate(img_buffers):
        img = MIMEImage(buf.getvalue()); img.add_header('Content-ID', f'<chart_{i}>'); msg.attach(img)
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

def get_match_weather(home_team, date_str):
    city = {'阿森纳': 'London', '曼联': 'Manchester', '利物浦': 'Liverpool', '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona'}.get(home_team, 'London')
    try:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            day = resp.json()['forecast']['forecastday'][0]['day']
            return day['condition']['text'], round(day['avgtemp_c'], 1)
    except: pass
    return "未知", 0

def dixon_coles_tau(h, a, home_xg, away_xg, rho=-0.1):
    if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
    elif h == 0 and a == 1: return 1 + home_xg * rho
    elif h == 1 and a == 0: return 1 + away_xg * rho
    elif h == 1 and a == 1: return 1 - rho
    return 1.0

def ai_adjust_probabilities(home_cn, away_cn, p_h, p_d, p_a, injury_info, odds_trend, knowledge, ref_info, coach_info):
    prompt = f"""你是一位量化风控总监。比赛：{home_cn} vs {away_cn}。
    基础概率：主胜 {p_h*100:.1f}%，平局 {p_d*100:.1f}%，客胜 {p_a*100:.1f}%。
    【伤停情报】: {injury_info}
    【盘口异动】: {odds_trend}
    裁判：{ref_info.get('name')}。教练风格：{coach_info.get('h_style')}/{coach_info.get('a_style')}。
    请根据【历史经验库】和盘口异动，判断是否需要微调概率。
    【经验库】：{knowledge}
    要求：必须输出严格的纯 JSON 格式，格式：{{"p_h": 0.45, "p_d": 0.30, "p_a": 0.25, "reason": "理由"}}"""
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
if os.path.exists('bankroll.csv'):
    try: bankroll = pd.read_csv('bankroll.csv').iloc[-1]['当前资金']
    except: pass

if not os.path.exists('daily_matches.csv'): exit()
df_next_round = pd.read_csv('daily_matches.csv')
df_next_round['主队'] = df_next_round['主队'].apply(translate_team_name)
df_next_round['客队'] = df_next_round['客队'].apply(translate_team_name)
df_next_round['datetime_parsed'] = pd.to_datetime(df_next_round['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
now_ts = pd.Timestamp.now()
df_next_round = df_next_round[(df_next_round['datetime_parsed'] >= now_ts) & (df_next_round['datetime_parsed'] <= now_ts + pd.Timedelta(hours=72))]
if df_next_round.empty: exit()

ref_dict, coach_dict = {}, {}
if os.path.exists('referee_stats.csv'):
    for _, r in pd.read_csv('referee_stats.csv').iterrows(): ref_dict[(r['home_team'], r['away_team'])] = {'name': r['referee'], 'yellow': r['avg_yellow_cards'], 'penalty': r['avg_penalties']}
if os.path.exists('coach_stats.csv'):
    for _, r in pd.read_csv('coach_stats.csv').iterrows(): coach_dict[r['team']] = {'style': r['coach_style']}

injury_dict, injury_impact = {}, {}
try:
    fpl_data = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15).json()
    teams_map = {t['id']: translate_team_name(t['name']) for t in fpl_data['teams']}
    for e in fpl_data['elements']:
        if (e['status'] in ['d', 'i', 's', 'u'] or (e.get('chance_of_playing_next_round') or 100) < 75) and (e.get('now_cost', 0) >= 50 or e.get('total_points', 0) >= 20):
            t_name = teams_map.get(e['team'])
            if t_name:
                injury_dict.setdefault(t_name, []).append(f"{e['web_name']}({e.get('element_type')})")
                pos_weight = 1.0 if e.get('element_type') == 4 else 0.7
                injury_impact[t_name] = injury_impact.get(t_name, 0) + ((e.get('now_cost', 50) / 100.0) * pos_weight)
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
    h, a, d = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [h, a]:
        if t not in team_stats: team_stats[t] = {'xg':[], 'xga':[], 'pts':[]}
    h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
    a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
    team_stats[h]['xg'].append(h_xg); team_stats[h]['xga'].append(a_xg)
    team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[a]['xg'].append(a_xg); team_stats[a]['xga'].append(h_xg)
    team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    last_date[h] = d; last_date[a] = d

knowledge_base = open('knowledge.txt', 'r', encoding='utf-8').read() if os.path.exists('knowledge.txt') else ""
model_h, model_a = joblib.load('epl_v31_home_goals_model.pkl'), joblib.load('epl_v31_away_goals_model.pkl')
html_report, prediction_logs, img_buffers = "<html><body><h2>⚽ V20.1 真实数据预测 (盘口防呆优化版)</h2>", [], []

for league in df_next_round['联赛'].unique():
    html_report += f"<h2 style='color:blue;'>🏆 {league}</h2>"
    for _, match in df_next_round[df_next_round['联赛'] == league].iterrows():
        h_cn, a_cn = match['主队'], match['客队']
        m_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
        m_date = pd.to_datetime(match['datetime_parsed']).date()
        
        h = team_stats.get(h_cn, {'xg':[], 'xga':[], 'pts':[]})
        a = team_stats.get(a_cn, {'xg':[], 'xga':[], 'pts':[]})
        h_rest = (pd.Timestamp(m_date) - last_date[h_cn]).days if h_cn in last_date else 7
        a_rest = (pd.Timestamp(m_date) - last_date[a_cn]).days if a_cn in last_date else 7
        
        h_xg_avg = np.mean(h['xg'][-5:]) if h['xg'] else league_avg_goals
        a_xg_avg = np.mean(a['xg'][-5:]) if a['xg'] else league_avg_goals
        h_xga_avg = np.mean(h['xga'][-5:]) if h['xga'] else league_avg_goals
        a_xga_avg = np.mean(a['xga'][-5:]) if a['xga'] else league_avg_goals
        h_pts = np.mean(h['pts'][-5:]) if h['pts'] else 1.0
        a_pts = np.mean(a['pts'][-5:]) if a['pts'] else 1.0
        
        feat = np.clip(np.nan_to_num([h_xg_avg, a_xg_avg, h_xga_avg, a_xga_avg, h_pts, a_pts, h_rest, a_rest, h_xg_avg - a_xga_avg, a_xg_avg - h_xga_avg], nan=0.0), -5.0, 5.0).reshape(1, -1)
        home_xg = max(0.1, model_h.predict(feat)[0])
        away_xg = max(0.1, model_a.predict(feat)[0])
        
        h_impact = injury_impact.get(h_cn, 0)
        a_impact = injury_impact.get(a_cn, 0)
        home_xg *= max(0.6, 1 - h_impact * 0.1) 
        away_xg *= max(0.6, 1 - a_impact * 0.1)
        
        prob_matrix = np.zeros((7, 7))
        for i in range(7):
            for j in range(7):
                prob_matrix[i][j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg) * dixon_coles_tau(i, j, home_xg, away_xg)
        
        p_h, p_d, p_a = np.sum(np.tril(prob_matrix, -1)), np.sum(np.diag(prob_matrix)), np.sum(np.triu(prob_matrix, 1))
        total_p = p_h + p_d + p_a
        p_h, p_d, p_a = p_h/total_p, p_d/total_p, p_a/total_p
        
        # 🌟 核心防呆：判空逻辑
        real_h, real_d, real_a = match.get('主胜赔率', 0), match.get('平局赔率', 0), match.get('客胜赔率', 0)
        hc_line, hc_h_odd, hc_a_odd = match.get('让球盘口', pd.NA), match.get('主让胜赔率', pd.NA), match.get('客受让胜赔率', pd.NA)
        tl_line, over_odd, under_odd = match.get('大小球盘口', pd.NA), match.get('大球赔率', pd.NA), match.get('小球赔率', pd.NA)
        
        has_real = (pd.notna(real_h) and real_h > 1.0)
        
        ou_msg = "暂未抓取到真实大小球盘口"
        hc_msg = "暂未抓取到真实让球盘口"
        ou_rec, hc_rec = "观望", "观望"
        
        # 只有当盘口是有效数字时，才进行概率计算
        if pd.notna(tl_line) and pd.notna(over_odd) and tl_line > 0:
            prob_over = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + j > tl_line)
            prob_under = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + j < tl_line)
            ou_msg = f"盘口 {tl_line}，模型大球概率 {prob_over*100:.1f}%，小球 {prob_under*100:.1f}%。"
            ev_over = prob_over * over_odd
            ev_under = prob_under * under_odd
            if ev_over > 1.05 and ev_over > ev_under: ou_rec = "大球 (高价值)"
            elif ev_under > 1.05 and ev_under > ev_over: ou_rec = "小球 (高价值)"
            
        if pd.notna(hc_line) and pd.notna(hc_h_odd):
            prob_hc_home = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + hc_line > j)
            prob_hc_away = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + hc_line < j)
            hc_msg = f"主队让 {hc_line} 球，模型主赢盘 {prob_hc_home*100:.1f}%，客赢盘 {prob_hc_away*100:.1f}%。"
            ev_hc_h = prob_hc_home * hc_h_odd
            ev_hc_a = prob_hc_away * hc_a_odd
            if ev_hc_h > 1.05 and ev_hc_h > ev_hc_a: hc_rec = "主队赢盘 (高价值)"
            elif ev_hc_a > 1.05 and ev_hc_a > ev_hc_h: hc_rec = "客队赢盘 (高价值)"

        ref_info = ref_dict.get((h_cn, a_cn), {'name': '未公布', 'yellow': 0, 'penalty': 0})
        h_coach = coach_dict.get(h_cn, {'style': '攻守平衡'})
        a_coach = coach_dict.get(a_cn, {'style': '攻守平衡'})
        coach_info = {'h_style': h_coach['style'], 'a_style': a_coach['style']}
        
        h_inj_str = ','.join(injury_dict.get(h_cn, ['无']))
        a_inj_str = ','.join(injury_dict.get(a_cn, ['无']))
        injury_info = f"主队伤停: {h_inj_str} (权重{h_impact:.1f}); 客队伤停: {a_inj_str} (权重{a_impact:.1f})"
        
        odds_trend = "暂未获取到盘口轨迹数据"
        p_h, p_d, p_a, ai_reason = ai_adjust_probabilities(h_cn, a_cn, p_h, p_d, p_a, injury_info, odds_trend, knowledge_base, ref_info, coach_info)
        
        predict_choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")
        oh, od, oa = (real_h, real_d, real_a) if has_real else (2.0, 3.3, 3.5)
        
        final_rec, bet_amt, split_msg = "观望", 0.0, ""
        if has_real:
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od-1)/(od-1), (p_a*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            if max_k > 0.02:
                b_choice = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (b_choice == "主胜" and p_h > 0.25) or (b_choice == "平局" and p_d > 0.25) or (b_choice == "客胜" and p_a > 0.25):
                    safe_k = min(max_k * 0.5, 0.05)
                    bet_amt, final_rec = bankroll * safe_k, b_choice
                    split_msg = f"推荐下注 {bet_amt:.2f}元"

        top_scores = sorted([(f"{i}-{j}", prob_matrix[i][j]) for i in range(7) for j in range(7)], key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join([f"{s[0]}({s[1]*100:.1f}%)" for s in top_scores])

        prompt = f"""资深专家，点评(150字内)：
        比赛：{h_cn} vs {a_cn}。倾向：{predict_choice}。
        伤停：{injury_info}
        大小球：{ou_msg}
        让球：{hc_msg}
        AI理由：{ai_reason}
        请结合机构心理，以“推荐关注：{final_rec}”结尾。"""
        try: ai_comment = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False).choices[0].message.content.strip()
        except: ai_comment = "AI解析失败"

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        ax1.bar(['主胜', '平局', '客胜'], [p_h, p_d, p_a], color=['royalblue', 'orange', 'gray'])
        ax1.set_title(f"{h_cn} vs {a_cn} 概率")
        ax2.bar(['主队xG', '客队xG'], [home_xg, away_xg], color=['red', 'blue'])
        ax2.set_title("真实预期进球(xG)")
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=100); buf.seek(0); img_buffers.append(buf); plt.close(fig)

        html_report += f"<hr><h3>{m_time} - {h_cn} vs {a_cn} [{league}]</h3>"
        html_report += f"<img src='cid:chart_{len(img_buffers)-1}' width='600'><br>"
        html_report += f"<p><b>🧑‍⚖️ 主裁信息：</b>{ref_info['name']} (场均黄牌{ref_info['yellow']}张)</p>"
        html_report += f"<p><b>🧠 教练风格：</b>{h_cn}[{h_coach['style']}] vs {a_cn}[{a_coach['style']}]</p>"
        html_report += f"<p><b>🚨 核心伤停：</b>主队[{h_inj_str}] / 客队[{a_inj_str}]</p>"
        html_report += f"<p><b>⚖️ 亚盘让球：</b>{hc_msg} 推荐：<b>{hc_rec}</b></p>"
        html_report += f"<p><b>⚖️ 大小球：</b>{ou_msg} 推荐：<b>{ou_rec}</b></p>"
        html_report += f"<p><b>🎯 赛果概率：</b>主胜 {p_h*100:.1f}% | 平局 {p_d*100:.1f}% | 客胜 {p_a*100:.1f}%</p>"
        html_report += f"<p><b>🧠 AI修正：</b><span style='color:#d35400;'>{ai_reason}</span></p>"
        html_report += f"<p><b>🔮 比分推荐：</b>{top3_str}</p>"
        html_report += f"<div style='background-color:#f8f9fa; border:1px solid #ddd; padding:15px; margin-top:10px;'><p><b>💡 最终下注：</b><span style='font-size:22px;color:red;'>{final_rec}</span> {split_msg}</p></div>"
        html_report += f"<p><b>🧠 AI点评：</b>{ai_comment}</p>"

html_report += "</body></html>"

log_df = pd.DataFrame(prediction_logs)
if os.path.exists('predictions_log.csv'):
    old = pd.read_csv('predictions_log.csv')
    log_df = pd.concat([old, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
open('dashboard.html', 'w', encoding='utf-8').write(html_report)
send_rich_email("V20.1 真实数据预测 (盘口防呆优化版)", html_report, img_buffers)
