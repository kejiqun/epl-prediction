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
    except Exception as e: print(f"❌ 邮件失败: {e}")

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
df_next_round['match_date_str'] = df_next_round['datetime_parsed'].dt.strftime('%Y-%m-%d')

now_ts = pd.Timestamp.now()
df_next_round = df_next_round[(df_next_round['datetime_parsed'] >= now_ts) & (df_next_round['datetime_parsed'] <= now_ts + pd.Timedelta(hours=72))]
if df_next_round.empty: exit()

real_odds_dict = {}
if os.path.exists('real_odds.csv'):
    df_odds = pd.read_csv('real_odds.csv')
    for _, r in df_odds.iterrows():
        try:
            api_date = pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d')
            real_odds_dict[(api_date, r['主队'], r['客队'])] = r
        except: pass

if os.path.exists('manual_odds.csv'):
    df_manual = pd.read_csv('manual_odds.csv')
    for _, r in df_manual.iterrows():
        try:
            manual_date = str(r['比赛日期']).strip()
            real_odds_dict[(manual_date, r['主队'], r['客队'])] = r
        except Exception as e:
            pass

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
        if t not in team_stats: team_stats[t] = {'xg':[], 'opp_elo':[], 'pts':[]}
        if t not in last_date: last_date[t] = None
    act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
    act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
    team_stats[h]['xg'].append(act_h_xg); team_stats[h]['opp_elo'].append(1500) 
    team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[a]['xg'].append(act_a_xg); team_stats[a]['opp_elo'].append(1500)
    team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    last_date[h] = m_date; last_date[a] = m_date

elo_dict = {}
if os.path.exists('elo_dict.pkl'): elo_dict = joblib.load('elo_dict.pkl')

knowledge_base = open('knowledge.txt', 'r', encoding='utf-8').read() if os.path.exists('knowledge.txt') else ""
model_h, model_a = joblib.load('epl_v31_home_goals_model.pkl'), joblib.load('epl_v31_away_goals_model.pkl')
calibrated_clf = joblib.load('epl_result_classifier.pkl')

# 🌟 新增：专门存放狙击清单的列表
jczq_picks_list = []
html_report, prediction_logs, img_buffers = "", [], []

# 先跑循环，计算数据并收集清单
for league in df_next_round['联赛'].unique():
    for _, match in df_next_round[df_next_round['联赛'] == league].iterrows():
        h_cn, a_cn = match['主队'], match['客队']
        match_date_str = match['match_date_str']
        m_time = pd.to_datetime(match['datetime_parsed']).strftime('%Y-%m-%d %H:%M')
        m_date = pd.to_datetime(match['datetime_parsed']).date()
        
        odds_row = real_odds_dict.get((match_date_str, h_cn, a_cn))
        
        if odds_row is not None:
            real_h, real_d, real_a = odds_row['主胜赔率'], odds_row['平局赔率'], odds_row['客胜赔率']
            hc_line, hc_h_odd, hc_a_odd = odds_row.get('让球盘口', 0.0), odds_row.get('主让胜赔率', 0.0), odds_row.get('客受让胜赔率', 0.0)
            tl_line, over_odd, under_odd = odds_row.get('大小球盘口', 2.5), odds_row.get('大球赔率', 0.0), odds_row.get('小球赔率', 0.0)
            has_real = True
        else:
            real_h, real_d, real_a = 0, 0, 0
            hc_line, hc_h_odd, hc_a_odd = 0.0, 0.0, 0.0
            tl_line, over_odd, under_odd = 2.5, 0.0, 0.0
            has_real = False

        h = team_stats.get(h_cn, {'xg':[], 'opp_elo':[], 'pts':[]})
        a = team_stats.get(a_cn, {'xg':[], 'opp_elo':[], 'pts':[]})
        h_rest = (pd.Timestamp(m_date) - last_date[h_cn]).days if h_cn in last_date else 7
        a_rest = (pd.Timestamp(m_date) - last_date[a_cn]).days if a_cn in last_date else 7
        rest_diff = h_rest - a_rest
        
        h_xg = np.mean(h['xg'][-5:]) if h['xg'] else league_avg_goals
        a_xg = np.mean(a['xg'][-5:]) if a['xg'] else league_avg_goals
        h_sos = np.mean(h['opp_elo'][-5:]) if h['opp_elo'] else 1500
        a_sos = np.mean(a['opp_elo'][-5:]) if a['opp_elo'] else 1500
        h_pts = np.mean(h['pts'][-5:]) if h['pts'] else 1.0
        a_pts = np.mean(a['pts'][-5:]) if a['pts'] else 1.0
        
        h_elo = elo_dict.get(h_cn, 1500)
        a_elo = elo_dict.get(a_cn, 1500)
        
        feat = [h_elo, a_elo, h_elo - a_elo, h_sos, a_sos, h_xg, a_xg, h_pts, a_pts, rest_diff]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
        
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
        ou_msg, hc_msg, ou_rec, hc_rec = "暂未抓取到真实盘口", "暂未抓取到真实盘口", "观望", "观望"
        
        if has_real:
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od-1)/(od-1), (p_a*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            if max_k > 0.02:
                b_choice = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (b_choice == "主胜" and p_h > 0.25) or (b_choice == "平局" and p_d > 0.25) or (b_choice == "客胜" and p_a > 0.25):
                    safe_k = min(max_k * 0.5, 0.05)
                    bet_amt, final_rec = bankroll * safe_k, b_choice
                    split_msg = f"推荐下注 {bet_amt:.2f}元"
                else:
                    split_msg = "概率不足，建议空仓观望"
            else:
                split_msg = "模型认为无正期望价值"

            if pd.notna(tl_line) and tl_line > 0:
                prob_over = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + j > tl_line)
                prob_under = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + j < tl_line)
                ou_msg = f"盘口 {tl_line}，模型大球概率 {prob_over*100:.1f}%。"
                if prob_over * over_odd > 1.05: ou_rec = "大球 (高价值)"
                elif prob_under * under_odd > 1.05: ou_rec = "小球 (高价值)"
                
            if pd.notna(hc_line) and hc_line != 0:
                prob_hc_home = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + hc_line > j)
                prob_hc_away = sum(prob_matrix[i][j] for i in range(7) for j in range(7) if i + hc_line < j)
                hc_msg = f"主队让 {hc_line} 球，模型主赢盘 {prob_hc_home*100:.1f}%。"
                if prob_hc_home * hc_h_odd > 1.05: hc_rec = "主队赢盘 (高价值)"
                elif prob_hc_away * hc_a_odd > 1.05: hc_rec = "客队赢盘 (高价值)"
        else:
            final_rec = f"技术倾向：{predict_choice}"
            split_msg = "(无真实盘口，禁止实盘)"

        # 🌟 如果触发了买入条件，记录进狙击清单
        if bet_amt > 0 or "高价值" in ou_rec or "高价值" in hc_rec:
            jczq_picks_list.append({
                '比赛时间': m_time,
                '赛事': league,
                '对阵': f"{h_cn} vs {a_cn}",
                '胜平负推荐': final_rec if bet_amt > 0 else "观望",
                '推荐金额': round(bet_amt, 2) if bet_amt > 0 else 0,
                '让球推荐': hc_rec,
                '大小球推荐': ou_rec
            })

        # 生成邮件内容（按原有逻辑）
        top_scores = sorted([(f"{i}-{j}", prob_matrix[i][j]) for i in range(7) for j in range(7)], key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join([f"{s[0]}({s[1]*100:.1f}%)" for s in top_scores])

        prompt = f"""资深专家，点评(150字内)：
        比赛：{h_cn} vs {a_cn}。倾向：{predict_choice}。伤停：{injury_info}。大小球/让球：{ou_msg} / {hc_msg}。AI理由：{ai_reason}
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
        html_report += f"<p><b>💪 Elo 实力：</b>{h_cn} {h_elo:.0f} vs {a_cn} {a_elo:.0f} (差值: {h_elo-a_elo:+.0f})</p>"
        html_report += f"<p><b>⏱️ 休息天数：</b>主队 {h_rest} 天 vs 客队 {a_rest} 天</p>"
        html_report += f"<p><b>🚨 核心伤停：</b>主队[{h_inj_str}] / 客队[{a_inj_str}]</p>"
        html_report += f"<p><b>⚖️ 亚盘让球：</b>{hc_msg} 推荐：<b>{hc_rec}</b></p>"
        html_report += f"<p><b>⚖️ 大小球：</b>{ou_msg} 推荐：<b>{ou_rec}</b></p>"
        html_report += f"<p><b>🎯 赛果概率：</b>主胜 {p_h*100:.1f}% | 平局 {p_d*100:.1f}% | 客胜 {p_a*100:.1f}%</p>"
        html_report += f"<div style='background-color:#f8f9fa; border:1px solid #ddd; padding:15px; margin-top:10px;'><p><b>💡 最终结论：</b><span style='font-size:22px;color:red;'>{final_rec}</span> {split_msg}</p></div>"
        html_report += f"<p><b>🧠 AI点评：</b>{ai_comment}</p>"

# 🌟 汇总最终邮件与清单文件
final_html = "<html><body><h2>⚽ V29.0 真实数据预测 (竞彩狙击版)</h2>"

# 如果清单里有货，就放在邮件最顶端
if jczq_picks_list:
    df_picks = pd.DataFrame(jczq_picks_list)
    df_picks.to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig') # 保存为 CSV 文件
    
    picks_html = df_picks.to_html(index=False, border=1, justify='center', classes='table table-striped')
    final_html += f"""
    <div style='background-color: #fff3cd; border: 2px solid #ffc107; padding: 20px; border-radius: 8px; margin-bottom: 20px;'>
        <h3 style='color: #856404; margin-top: 0;'>🎯 今日竞彩狙击清单 (仅限有高价值比赛)</h3>
        <p style='color: #856404;'>系统已为您过滤掉所有无效比赛，以下比赛经模型精算具有真实盈利空间。请按照此清单去彩票店挑选！</p>
        {picks_html}
    </div>
    """
else:
    final_html += """
    <div style='background-color: #f8d7da; border: 2px solid #f5c6cb; padding: 20px; border-radius: 8px; margin-bottom: 20px;'>
        <h3 style='color: #721c24; margin-top: 0;'>🛑 今日无狙击目标</h3>
        <p style='color: #721c24;'>系统扫描了今日所有比赛，因无赔率或凯利指标不足，模型未发现有高价值的投资机会。建议今日空仓观望，保存实力。</p>
    </div>
    """
    # 生成一个空的 CSV 防止后续报错
    pd.DataFrame(columns=['比赛时间', '赛事', '对阵', '胜平负推荐', '推荐金额', '让球推荐', '大小球推荐']).to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')

final_html += html_report + "</body></html>"

log_df = pd.DataFrame(prediction_logs)
if os.path.exists('predictions_log.csv'):
    old = pd.read_csv('predictions_log.csv')
    log_df = pd.concat([old, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

open('dashboard.html', 'w', encoding='utf-8').write(final_html)
send_rich_email("V29.0 每日战报与竞彩狙击清单", final_html, img_buffers)
