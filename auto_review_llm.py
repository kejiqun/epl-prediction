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
    msg['From'] = EMAIL_SENDER; msg['To'] = receiver; msg['Subject'] = Header(subject, 'utf-8')
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
        print("✅ 复盘邮件发送成功！")
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

print("⏳ 正在启动多联赛深度复盘引擎 (V9.0 资金结算版)...")

if not os.path.exists('predictions_log.csv'):
    print("⚠️ 找不到 predictions_log.csv，跳过复盘。")
    exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
past_3_days = today - timedelta(days=3)

# 确保列存在
if 'actual_score' not in df_log.columns: df_log['actual_score'] = ""
if 'actual_result' not in df_log.columns: df_log['actual_result'] = ""
if 'is_win' not in df_log.columns: df_log['is_win'] = ""
if 'bet_amount' not in df_log.columns: df_log['bet_amount'] = 0.0
if 'profit' not in df_log.columns: df_log['profit'] = 0.0

pending_review = df_log[(df_log['date'] >= past_3_days) & (df_log['actual_score'].isna() | (df_log['actual_score'] == ""))].copy()

if pending_review.empty:
    print("✅ 最近 3 天没有需要复盘的新比赛。")
    # 发送无比赛空邮件
    html_report = f"""
    <html><body><div style="text-align: center; padding: 50px;">
        <h2 style="color: #2c3e50;">💡 今日复盘完成</h2>
        <p style="color: #666; font-size: 16px;">最近 3 天内没有需要复盘的新比赛，或者比赛尚未结束。系统正在静候下一轮战报。</p>
    </div></body></html>"""
    send_email("💡 多联赛 V9.0 极简深度复盘报告", html_report)
    exit()

print(f"⏳ 找到 {len(pending_review)} 场待复盘比赛，正在抓取赛果...")

actual_results = {}
for league_name, config in LEAGUES.items():
    for i in range(1, 4):
        date_str = (today - timedelta(days=i)).strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={date_str}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for event in data.get('events', []):
                    if event['status']['type']['state'] == 'post':
                        competitions = event.get('competitions', [])
                        if competitions:
                            competitors = competitions[0].get('competitors', [])
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
    try:
        df_b = pd.read_csv('bankroll.csv')
        if not df_b.empty: bankroll = df_b.iloc[-1]['当前资金']
    except: pass

review_data = []
correct_count = 0
total_count = 0
total_profit = 0.0

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    h_cn = row['home_team']
    a_cn = row['away_team']
    pred_res = row['predicted_result']
    
    res = actual_results.get((m_date, h_cn, a_cn))
    if res:
        hg, ag = res
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        is_win = "✅ 命中" if pred_res == actual_res else "❌ 失手"
        
        # 🌟 核心结算逻辑：严格按照当时下注的金额和赔率结算
        bet = row['bet_amount']
        if bet > 0:
            if pred_res == actual_res:
                correct_count += 1
                if pred_res == "主胜": profit = bet * (row['odds_h'] - 1)
                elif pred_res == "平局": profit = bet * (row['odds_d'] - 1)
                else: profit = bet * (row['odds_a'] - 1)
            else:
                profit = -bet
        else:
            profit = 0.0 # 空仓观望，不盈不亏
            
        total_profit += profit
        total_count += 1
        
        df_log.at[idx, 'actual_score'] = f"{hg}-{ag}"
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        df_log.at[idx, 'profit'] = round(profit, 2)
        
        review_data.append({
            "联赛": row['league'], "比赛": f"{h_cn} vs {a_cn}",
            "推荐": pred_res, "实际": actual_res, "比分": f"{hg}-{ag}",
            "下注额": bet, "盈亏": round(profit, 2), "结果": is_win
        })

if total_count == 0:
    print("⚠️ 未能匹配到任何赛果（可能比赛还没踢完）。")
    exit()

bankroll += total_profit
win_rate = (correct_count / total_count) * 100

# ... 后面 AI 复盘和写 knowledge.txt 的代码保持不变 ...

# 保存新的资金记录
new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

# ... 发送邮件逻辑保持不变 ...
