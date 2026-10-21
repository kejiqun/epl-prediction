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

def dixon_coles_tau(h, a, home_xg, away_xg, rho=-0.1):
    if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
    elif h == 0 and a == 1: return 1 + home_xg * rho
    elif h == 1 and a == 0: return 1 + away_xg * rho
    elif h == 1 and a == 1: return 1 - rho
    return 1.0

# 简化的 AI 修正，只调概率
def ai_adjust_probabilities(home_cn, away_cn, p_h, p_d, p_a, injury_info, knowledge):
    prompt = f"""你是一位量化风控总监。比赛：{home_cn} vs {away_cn}。
    融合模型概率：主胜 {p_h*100:.1f}%，平局 {p_d*100:.1f}%，客胜 {p_a*100:.1f}%。
    伤停情报：{injury_info}
    请根据经验库进行微调，输出纯JSON：{{"p_h": 0.45, "p_d": 0.30, "p_a": 0.25, "reason": "理由"}}
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

if not os.path.exists('daily_matches.csv'): exit()
df_next = pd.read_csv('daily_matches.csv')
df_next['主队'] = df_next['主队'].apply(translate_team_name)
df_next['客队'] = df_next['客队'].apply(translate_team_name)
df_next['datetime_parsed'] = pd.to_datetime(df_next['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
now_ts = pd.Timestamp.now()
df_next = df_next[(df_next['datetime_parsed'] >= now_ts) & (df_next['datetime_parsed'] <= now_ts + pd.Timedelta(hours=72))]
if df_next.empty: exit()

# 重新计算历史特征库（为了获取 Elo 和 SoS）
history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
df_hist = pd.read_csv(history_file)
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

elo, team_stats, league_avg_goals = {}, {}, 1.35
for _, row in df_hist.iterrows():
    h, a = row['home_team_cn'], row['away_team_cn']
    for t in [h, a]:
        if t not in team_stats: team_stats[t] = {'xg':[], 'xga':[], 'opp_elo':[], 'pts':[]}
        if t not in elo: elo[t] = 1500
        
    exp_h = 1 / (1 + 10 ** ((elo[a] - (elo[h] + 100)) / 400))
    exp_a = 1 - exp_h
    if row['home_goals'] > row['away_goals']: score_h, score_a = 1, 0
    elif row['home_goals'] < row['away_goals']: score_h, score_a = 0, 1
    else: score_h, score_a = 0.5, 0.5
    
    elo[h] += 20 * (score_h - exp_h); elo[a] += 20 * (score_a - exp_a)
    
    team_stats[h]['xg'].append(row['home_goals']); team_stats[h]['opp_elo'].append(elo[a])
    team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[a]['xg'].append(row['away_goals']); team_stats[a]['opp_elo'].append(elo[h])
    team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))

model_h = joblib.load('epl_v31_home_goals_model.pkl')
model_a = joblib.load('epl_v31_away_goals_model.pkl')
calibrated_clf = joblib.load('epl_result_classifier.pkl')

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

knowledge_base = open('knowledge.txt', 'r', encoding='utf-8').read() if os.path.exists('knowledge.txt') else ""
html_report, prediction_logs, img_buffers = "<html><body><h2>⚽ V25.0 终极数据预测 (Elo+SoS+模型校准)</h2>", [], []

for league in df_next['联赛'].unique():
    html_report += f"<h2 style='color:blue;'>🏆 {league}</h2>"
    for _, match in df_next[df_next['联赛'] == league].iterrows():
        h_cn, a_cn = match['主队'], match['客队']
        m_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
        
        # 获取历史状态
        h = team_stats.get(h_cn, {'xg':[], 'opp_elo':[], 'pts':[]})
        a = team_stats.get(a_cn, {'xg':[], 'opp_elo':[], 'pts':[]})
        
        h_xg = np.mean(h['xg'][-5:]) if h['xg'] else 1.35
        a_xg = np.mean(a['xg'][-5:]) if a['xg'] else 1.35
        h_sos = np.mean(h['opp_elo'][-5:]) if h['opp_elo'] else 1500
        a_sos = np.mean(a['opp_elo'][-5:]) if a['opp_elo'] else 1500
        h_pts = np.mean(h['pts'][-5:]) if h['pts'] else 1.0
        a_pts = np.mean(a['pts'][-5:]) if a['pts'] else 1.0
        
        h_elo = elo.get(h_cn, 1500)
        a_elo = elo.get(a_cn, 1500)
        
        # 构建特征向量
        feat = np.clip(np.nan_to_num([
            h_elo, a_elo, h_elo - a_elo, h_sos, a_sos, h_xg, a_xg, h_pts, a_pts
        ], nan=0.0), -1000, 3000).reshape(1, -1)
        
        # 1. 纯 xG 泊松模型算概率
        pred_h_xg = max(0.1, model_h.predict(feat)[0])
        pred_a_xg = max(0.1, model_a.predict(feat)[0])
        
        # 伤停惩罚
        pred_h_xg *= max(0.6, 1 - injury_impact.get(h_cn, 0) * 0.1)
        pred_a_xg *= max(0.6, 1 - injury_impact.get(a_cn, 0) * 0.1)
        
        prob_matrix = np.zeros((7, 7))
        for i in range(7):
            for j in range(7):
                prob_matrix[i][j] = poisson.pmf(i, pred_h_xg) * poisson.pmf(j, pred_a_xg) * dixon_coles_tau(i, j, pred_h_xg, pred_a_xg)
        
        p_h_poisson, p_d_poisson, p_a_poisson = np.sum(np.tril(prob_matrix, -1)), np.sum(np.diag(prob_matrix)), np.sum(np.triu(prob_matrix, 1))
        total_p = p_h_poisson + p_d_poisson + p_a_poisson
        p_h_poisson, p_d_poisson, p_a_poisson = p_h_poisson/total_p, p_d_poisson/total_p, p_a_poisson/total_p
        
        # 2. 分类模型校准后的概率
        clf_probs = calibrated_clf.predict_proba(feat)[0]
        # 注意：LGBMClassifier 的类别顺序可能是 [0(客胜), 1(平局), 2(主胜)]
        p_a_clf, p_d_clf, p_h_clf = clf_probs[0], clf_probs[1], clf_probs[2]
        
        # 3. 终极融合 (权重 50:50)
        p_h = (p_h_poisson + p_h_clf) / 2
        p_d = (p_d_poisson + p_d_clf) / 2
        p_a = (p_a_poisson + p_a_clf) / 2
        
        # 4. AI 经验最终修正
        h_inj_str = ','.join(injury_dict.get(h_cn, ['无']))
        a_inj_str = ','.join(injury_dict.get(a_cn, ['无']))
        injury_info = f"主队伤停: {h_inj_str}; 客队伤停: {a_inj_str}"
        
        p_h, p_d, p_a, ai_reason = ai_adjust_probabilities(h_cn, a_cn, p_h, p_d, p_a, injury_info, knowledge_base)
        predict_choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")

        # 盘口部分保持原样
        real_h, real_d, real_a = match.get('主胜赔率', 0), match.get('平局赔率', 0), match.get('客胜赔率', 0)
        has_real = (pd.notna(real_h) and real_h > 1.0)
        oh, od, oa = (real_h, real_d, real_a) if has_real else (2.0, 3.3, 3.5)
        
        final_rec, bet_amt, split_msg = "观望", 0.0, ""
        if has_real:
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od-1)/(od-1), (p_a*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            if max_k > 0.02:
                b_choice = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (b_choice == "主胜" and p_h > 0.3) or (b_choice == "平局" and p_d > 0.3) or (b_choice == "客胜" and p_a > 0.3):
                    safe_k = min(max_k * 0.5, 0.05)
                    bet_amt, final_rec = 10000 * safe_k, b_choice
                    split_msg = f"推荐下注 {bet_amt:.2f}元"
        else:
            final_rec = f"技术倾向：{predict_choice}"
            split_msg = "(无真实盘口，禁止实盘)"

        top_scores = sorted([(f"{i}-{j}", prob_matrix[i][j]) for i in range(7) for j in range(7)], key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join([f"{s[0]}({s[1]*100:.1f}%)" for s in top_scores])

        prompt = f"""资深专家，点评(150字内)：
        比赛：{h_cn} vs {a_cn}。
        主队: Elo {h_elo:.0f}，近5场对手均强{h_sos:.0f}。客队: Elo {a_elo:.0f}，近5场对手均强{a_sos:.0f}。
        伤停：{injury_info}
        技术倾向：{predict_choice}。AI理由：{ai_reason}
        请结合Elo实力差、赛程强度与盘口，以“推荐关注：{final_rec}”结尾。"""
        try: ai_comment = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False).choices[0].message.content.strip()
        except: ai_comment = "AI解析失败"

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        ax1.bar(['主胜', '平局', '客胜'], [p_h, p_d, p_a], color=['royalblue', 'orange', 'gray'])
        ax1.set_title(f"{h_cn} vs {a_cn} (融合概率)")
        ax2.bar(['主队xG', '客队xG'], [pred_h_xg, pred_a_xg], color=['red', 'blue'])
        ax2.set_title("预期进球(xG)")
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=100); buf.seek(0); img_buffers.append(buf); plt.close(fig)

        html_report += f"<hr><h3>{m_time} - {h_cn} vs {a_cn} [{league}]</h3>"
        html_report += f"<img src='cid:chart_{len(img_buffers)-1}' width='600'><br>"
        html_report += f"<p><b>💪 Elo 实力：</b>{h_cn} {h_elo:.0f} vs {a_cn} {a_elo:.0f} (差值: {h_elo-a_elo:+.0f})</p>"
        html_report += f"<p><b>📊 赛程强度：</b>主队近5场对手均强{h_sos:.0f} / 客队近5场对手均强{a_sos:.0f}</p>"
        html_report += f"<p><b>🚨 核心伤停：</b>主队[{h_inj_str}] / 客队[{a_inj_str}]</p>"
        html_report += f"<p><b>🎯 融合概率：</b>主胜 {p_h*100:.1f}% | 平局 {p_d*100:.1f}% | 客胜 {p_a*100:.1f}%</p>"
        html_report += f"<p><b>🧠 AI修正：</b><span style='color:#d35400;'>{ai_reason}</span></p>"
        html_report += f"<p><b>🔮 比分推荐：</b>{top3_str}</p>"
        html_report += f"<div style='background-color:#f8f9fa; border:1px solid #ddd; padding:15px; margin-top:10px;'><p><b>💡 最终结论：</b><span style='font-size:22px;color:red;'>{final_rec}</span> {split_msg}</p></div>"
        html_report += f"<p><b>🧠 AI点评：</b>{ai_comment}</p>"

html_report += "</body></html>"

log_df = pd.DataFrame(prediction_logs)
if os.path.exists('predictions_log.csv'):
    old = pd.read_csv('predictions_log.csv')
    log_df = pd.concat([old, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
open('dashboard.html', 'w', encoding='utf-8').write(html_report)
send_rich_email("V25.0 终极数据预测 (Elo+SoS+模型校准)", html_report, img_buffers)
