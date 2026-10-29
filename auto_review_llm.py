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
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

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

print("⏳ 正在启动 V48.0 深度复盘引擎...")
if not os.path.exists('predictions_log.csv'): exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')

for c in ['actual_score', 'actual_result', 'is_win', 'profit', 'bet_amount', 'predicted_score', 'top3_scores']:
    if c not in df_log.columns: 
        df_log[c] = np.nan if 'amount' in c or 'profit' in c else ""

pending_review = df_log[(df_log['actual_score'].isna() | (df_log['actual_score'] == "")) & (df_log['date'].dt.strftime('%Y-%m-%d') <= yesterday)].copy()

if pending_review.empty:
    print("✅ 没有需要复盘的新比赛。")
    send_email("☕ 每日复盘通知 (今日无战事)", "<html><body><h2>今日无待复盘比赛</h2></body></html>")
    exit()

print(f"⏳ 找到 {len(pending_review)} 场待复盘比赛，正在通过 API-Football 抓取赛果...")

actual_results = {}
headers = {"x-apisports-key": API_FOOTBALL_KEY}
dates_to_query = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 6)]

for d_str in dates_to_query:
    try:
        url = f"https://v3.football.api-sports.io/fixtures?date={d_str}&status=FT"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            for fixture in resp.json().get('response', []):
                h_name = translate_team_name(fixture['teams']['home']['name'])
                a_name = translate_team_name(fixture['teams']['away']['name'])
                hg = fixture['goals']['home']
                ag = fixture['goals']['away']
                if hg is not None and ag is not None:
                    actual_results[(h_name, a_name)] = (hg, ag) # 🌟 核心修复：不再用日期匹配，直接用主客队名称做唯一键！
    except: continue

review_records = []
correct_count = 0
total_count = 0
total_profit = 0.0

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    res = actual_results.get((row['home_team'], row['away_team'])) # 精确匹配主客队
    
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
    print("⚠️ 扫描到了比赛，但 API 依然没查到赛果，可能比赛延期。")
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
    send_email("⏳ 每日复盘通知 (待结算)", "<html><body><h2>比赛尚未结算，系统将在明日重试。</h2></body></html>")
    exit()

bankroll = 10000.0
if os.path.exists('bankroll.csv'):
    try: bankroll = pd.read_csv('bankroll.csv').iloc[-1]['当前资金']
    except: pass
bankroll += total_profit
win_rate = (correct_count / total_count) * 100 if total_count > 0 else 0

new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

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
    <h1>💼 每日量化实盘复盘战报 (V48.0)</h1>
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
send_email("💼 每日量化实盘复盘战报 (V48.0)", html_content)
print("✅ 复盘完毕！")
