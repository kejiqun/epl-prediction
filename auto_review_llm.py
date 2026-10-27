import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime, timedelta
import warnings
from openai import OpenAI
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
import re
from config import LEAGUES
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def send_email(subject, html_content, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    msg = MIMEMultipart('alternative')
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, receiver, Header(subject, 'utf-8')
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
        print("✅ 复盘邮件发送成功！")
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

print("⏳ 正在启动 V46.0 全景复盘引擎...")
if not os.path.exists('predictions_log.csv'): exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')

for c in ['actual_score', 'actual_result', 'is_win', 'profit', 'bet_amount', 'predicted_score', 'top3_scores']:
    if c not in df_log.columns: 
        df_log[c] = np.nan if 'amount' in c or 'profit' in c else ""

# 寻找昨天及之前未结算的比赛
pending_review = df_log[(df_log['actual_score'].isna() | (df_log['actual_score'] == "")) & (df_log['date'].dt.strftime('%Y-%m-%d') <= yesterday)].copy()

if pending_review.empty:
    print("✅ 没有需要复盘的新比赛。")
    send_email("☕ 每日复盘通知 (今日无战事)", "<html><body><h2>今日无待复盘比赛</h2></body></html>")
    exit()

print(f"⏳ 找到 {len(pending_review)} 场待复盘比赛，正在抓取真实赛果...")

actual_results = {}
for league_name, config in LEAGUES.items():
    for i in range(1, 5):
        date_str = (today - timedelta(days=i)).strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={date_str}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                for event in resp.json().get('events', []):
                    if event['status']['type']['state'] == 'post':
                        comps = event.get('competitions', [])
                        if comps:
                            competitors = comps[0].get('competitors', [])
                            home = next((c for c in competitors if c['homeAway'] == 'home'), None)
                            away = next((c for c in competitors if c['homeAway'] == 'away'), None)
                            if home and away:
                                h_name = translate_team_name(home['team']['name'])
                                a_name = translate_team_name(away['team']['name'])
                                h_score = int(home.get('score', 0))
                                a_score = int(away.get('score', 0))
                                match_date_str = pd.to_datetime(event['date']).tz_convert('Asia/Shanghai').strftime('%Y-%m-%d')
                                actual_results[(match_date_str, h_name, a_name)] = (h_score, a_score)
        except: continue

bankroll = 10000.0
if os.path.exists('bankroll.csv'):
    try: bankroll = pd.read_csv('bankroll.csv').iloc[-1]['当前资金']
    except: pass

review_records = []
wrong_matches = []
correct_count = 0
total_count = 0
total_profit = 0.0
score_analysis_data = []

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    res = actual_results.get((m_date, row['home_team'], row['away_team']))
    
    if res:
        hg, ag = res
        actual_score = f"{hg}-{ag}"
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        pred_score = row.get('predicted_score', '未知')
        pred_top3 = row.get('top3_scores', '未知')
        
        bet = float(row.get('bet_amount', 0)) if pd.notna(row.get('bet_amount')) else 0.0
        profit = 0.0
        is_win = "观望"
        
        if bet > 0:
            total_count += 1
            if row['predicted_result'] == actual_res:
                correct_count += 1
                is_win = "✅ 命中"
                if row['predicted_result'] == "主胜": profit = bet * (float(row.get('odds_h', 2.0)) - 1)
                elif row['predicted_result'] == "平局": profit = bet * (float(row.get('odds_d', 3.3)) - 1)
                else: profit = bet * (float(row.get('odds_a', 3.5)) - 1)
            else:
                is_win = "❌ 失手"
                profit = -bet
                wrong_matches.append({
                    '比赛': f"{row['home_team']} vs {row['away_team']}",
                    '预测赛果': row['predicted_result'], '实际赛果': actual_res,
                    '预测比分': pred_score, '实际比分': actual_score,
                    '伤停': f"主[{row.get('home_injuries', '无')}] 客[{row.get('away_injuries', '无')}]"
                })
        
        if pred_score != '未知' and pred_score != actual_score:
            score_analysis_data.append({
                '比赛': f"{row['home_team']} vs {row['away_team']}",
                '预期比分': pred_score, '实际比分': actual_score,
            })
        
        total_profit += profit
        df_log.at[idx, 'actual_score'] = actual_score
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        df_log.at[idx, 'profit'] = round(profit, 2)
        
        review_records.append({
            '比赛日期': m_date, '赛事': row['league'], '对阵': f"{row['home_team']} vs {row['away_team']}",
            '预测赛果': row['predicted_result'], '实际赛果': actual_res, '赛果对比': is_win,
            '预测比分': pred_score, '实际比分': actual_score, '比分对比': "✅ 命中" if pred_score==actual_score else "❌ 失手",
            '财务情况': round(profit, 2)
        })

if total_count == 0 and len(score_analysis_data) == 0:
    print("⚠️ 扫描到了比赛，但暂无已结算赛果。")
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
    send_email("⏳ 每日复盘通知 (待结算)", "<html><body><h2>比赛尚未结算</h2></body></html>")
    exit()

bankroll += total_profit
win_rate = (correct_count / total_count) * 100 if total_count > 0 else 0

new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

# AI 生成总结
ai_report = ""
if wrong_matches or len(score_analysis_data) > 3:
    prompt = f"""顶级足球量化总监，以下是昨日预测失败或比分偏差的复盘：
    错题本: {wrong_matches}
    比分偏差: {score_analysis_data[:10]}
    请分析原因，输出3条深刻的【纠错铁律】。"""
    try:
        res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        ai_report = res.choices[0].message.content.strip()
        with open('knowledge.txt', 'a', encoding='utf-8') as f:
            f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 深度比分纠错 ---\n{ai_report}")
    except Exception as e: ai_report = f"AI 剖析失败: {e}"
else:
    ai_report = "完美！昨日无赛果错题，且比分预测与实际结果高度吻合，无需调整。"

# 组装复盘 HTML
html_table = pd.DataFrame(review_records).to_html(index=False, border=0, classes='report-table', justify='center')

css = """
<style>
    body { font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; }
    .container { max-width: 900px; margin: auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
    h1 { text-align: center; color: #2c3e50; border-bottom: 3px solid #e74c3c; padding-bottom: 15px; margin-bottom: 25px; }
    h2 { color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 10px; }
    .stats-dashboard { display: flex; justify-content: space-around; background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 25px; border: 1px solid #e9ecef; }
    .stat-item { text-align: center; }
    .stat-value { font-size: 26px; font-weight: bold; color: #e74c3c; }
    .stat-label { font-size: 14px; color: #6c757d; margin-top: 5px; }
    .report-table { width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px; }
    .report-table th { background-color: #2c3e50; color: white; padding: 12px; text-align: center; }
    .report-table td { padding: 10px; border-bottom: 1px solid #dee2e6; text-align: center; }
    .report-table tr:hover { background-color: #f1f1f1; }
    .ai-box { background-color: #e8f4fd; border-left: 5px solid #3498db; padding: 20px; border-radius: 5px; font-size: 15px; line-height: 1.6; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin-bottom: 15px; background: #fafafa; }
    .card-title { margin: 0 0 10px 0; color: #2c3e50; font-size: 16px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
</style>
"""

html_content = f"""
<html><head>{css}</head>
<body>
<div class="container">
    <h1>💼 每日量化实盘复盘战报 (V46.0)</h1>
    
    <div class="stats-dashboard">
        <div class="stat-item"><div class="stat-value">{win_rate:.1f}%</div><div class="stat-label">昨日胜率 ({correct_count}/{total_count})</div></div>
        <div class="stat-item"><div class="stat-value" style="color: {'#27ae60' if total_profit >= 0 else '#c0392b'};">{total_profit:+.2f}</div><div class="stat-label">昨日盈亏 (元)</div></div>
        <div class="stat-item"><div class="stat-value" style="color: #2c3e50;">{bankroll:.2f}</div><div class="stat-label">当前总资金</div></div>
    </div>

    <h2>Part 1: 预测与实盘对比清单</h2>
    {html_table}
"""

# Part 2: 比分卡片生成
html_content += "<h2>Part 2: 比分精细化复盘 (单场分析)</h2>"
for r in review_records:
    is_score_hit = r['比分对比'] == '✅ 命中'
    color = '#27ae60' if is_score_hit else '#c0392b'
    
    html_content += f"""
    <div class="card" style="border-left: 5px solid {color};">
        <h4 class="card-title">{r['赛事']} | {r['对阵']} ({r['比赛日期']})</h4>
        <p style="margin: 5px 0; font-size: 14px;"><b>赛果：</b>预测 <span style="color:blue;">{r['预测赛果']}</span> vs 实际 <span style="color:red;">{r['实际赛果']}</span> -> <b>{r['赛果对比']}</b></p>
        <p style="margin: 5px 0; font-size: 14px;"><b>比分：</b>预测 <span style="color:blue;">{r['预测比分']}</span> vs 实际 <span style="color:red;">{r['实际比分']}</span> -> <b>{r['比分对比']}</b></p>
        <p style="margin: 10px 0 0 0; font-size: 13px; color: #555;">
            🧠 <b>专家总结：</b> 
            {"预测精准！模型成功捕捉了双方攻防节奏，继续保持该特征权重。" if is_score_hit else "预测偏差。需反思是伤停高估、还是机构诱盘导致的数据失真？已记录入错题本并沉淀经验。"}
        </p>
    </div>
    """

html_content += f"""
    <div class="ai-box">
        <h3>🧠 AI 整体深度纠错 (已沉淀至经验库)</h3>
        <p>{ai_report.replace(chr(10), '<br>')}</p>
    </div>
</div>
</body></html>
"""

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
send_email("💼 每日量化实盘复盘战报 (V46.0)", html_content)
print("✅ 复盘完毕！")
