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

print("⏳ 正在启动 V47.0 深度复盘引擎...")
if not os.path.exists('predictions_log.csv'): exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')

for c in ['actual_score', 'actual_result', 'is_win', 'profit', 'bet_amount', 'predicted_score', 'top3_scores']:
    if c not in df_log.columns: 
        df_log[c] = np.nan if 'amount' in c or 'profit' in c else ""

pending_review = df_log[(df_log['actual_score'].isna() | (df_log['actual_score'] == "")) & (df_log['date'].dt.strftime('%Y-%m-%d') <= yesterday)].copy()

# 🌟 核心抢救：清理超过3天的死账
if not pending_review.empty:
    pending_review['days_diff'] = (today - pending_review['date']).dt.days
    expired_matches = pending_review[pending_review['days_diff'] > 3]
    if not expired_matches.empty:
        print(f"🧹 发现 {len(expired_matches)} 场比赛过期无赛果，强制作废。")
        for idx in expired_matches.index:
            df_log.at[idx, 'actual_score'] = "赛果丢失"
            df_log.at[idx, 'is_win'] = "作废"
            df_log.at[idx, 'profit'] = 0.0
        pending_review = pending_review[~pending_review.index.isin(expired_matches.index)]

if pending_review.empty:
    print("✅ 没有需要复盘的新比赛。")
    send_email("☕ 每日复盘通知 (今日无战事)", "<html><body><h2>今日无待复盘比赛</h2></body></html>")
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
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
correct_count = 0
total_count = 0
total_profit = 0.0

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    res = actual_results.get((m_date, row['home_team'], row['away_team']))
    
    if res:
        hg, ag = res
        actual_score = f"{hg}-{ag}"
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        pred_score = row.get('predicted_score', '未知')
        
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

if total_count == 0:
    print("⚠️ 扫描到了比赛，但暂无已结算赛果。")
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
    send_email("⏳ 每日复盘通知 (待结算)", "<html><body><h2>比赛尚未结算，系统将在明日重试。</h2></body></html>")
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

# 组装邮件（简化版，输出复盘表格）
html_table = pd.DataFrame(review_records).to_html(index=False, border=0, classes='report-table', justify='center')

html_content = f"""
<html><head><style>
    body {{ font-family: Arial; padding: 20px; color: #333; }}
    .container {{ max-width: 850px; margin: auto; background: #fff; padding: 30px; border-radius: 12px; }}
    h1 {{ text-align: center; color: #2c3e50; }}
    .stats-dashboard {{ display: flex; justify-content: space-around; background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 25px; }}
    .stat-item {{ text-align: center; }}
    .stat-value {{ font-size: 26px; font-weight: bold; color: #e74c3c; }}
    .report-table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px; }}
    .report-table th {{ background-color: #2c3e50; color: white; padding: 12px; text-align: center; }}
    .report-table td {{ padding: 10px; border-bottom: 1px solid #dee2e6; text-align: center; }}
</style></head>
<body>
<div class="container">
    <h1>💼 每日量化实盘复盘战报 (V47.0 强制清算版)</h1>
    <div class="stats-dashboard">
        <div class="stat-item"><div class="stat-value">{win_rate:.1f}%</div><div class="stat-label">胜率 ({correct_count}/{total_count})</div></div>
        <div class="stat-item"><div class="stat-value">{total_profit:+.2f}</div><div class="stat-label">盈亏 (元)</div></div>
        <div class="stat-item"><div class="stat-value">{bankroll:.2f}</div><div class="stat-label">当前资金</div></div>
    </div>
    <h3>⚔️ 战况明细</h3>
    {html_table}
</div>
</body></html>
"""

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
send_email("💼 每日量化实盘复盘战报 (V47.0 强制清算版)", html_content)
print("✅ 复盘完毕！")
