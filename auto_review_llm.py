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

print("⏳ 正在启动 V25.0 深度复盘引擎 (错题剖析)...")
if not os.path.exists('predictions_log.csv'): exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
past_3_days = today - timedelta(days=3)

# 补齐缺失列
for c in ['actual_score', 'actual_result', 'is_win']:
    if c not in df_log.columns: df_log[c] = ""

# 获取需要复盘的记录（近3天，且尚未结算）
pending_review = df_log[(df_log['date'] >= past_3_days) & (df_log['actual_score'].isna() | (df_log['actual_score'] == ""))].copy()

if pending_review.empty:
    print("✅ 最近 3 天没有需要复盘的新比赛。")
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

wrong_matches = [] # 错题本

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    res = actual_results.get((m_date, row['home_team'], row['away_team']))
    
    if res:
        hg, ag = res
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        is_win = "✅ 命中" if row['predicted_result'] == actual_res else "❌ 失手"
        
        df_log.at[idx, 'actual_score'] = f"{hg}-{ag}"
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        
        # 如果预测错了（且不是观望），加入错题本
        if row['predicted_result'] != actual_res and row['predicted_result'] != "观望":
            wrong_matches.append({
                '联赛': row['league'], '比赛': f"{row['home_team']} vs {row['away_team']}",
                '实际比分': f"{hg}-{ag}", '预测赛果': row['predicted_result'], 
                '模型xG': f"主{row['model_home_xg']} 客{row['model_away_xg']}",
                '伤停': f"主[{row['home_injuries']}] 客[{row['away_injuries']}]"
            })

if not wrong_matches:
    print("🎉 完美！近期比赛全中，没有错题需要分析。")
    send_email("💡 完美复盘 (无错题)", "<html><body><h2>近期预测全中，无错题复盘。</h2></body></html>")
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
    exit()

print(f"🚨 发现 {len(wrong_matches)} 场错题，呼叫 AI 深度剖析...")

prompt = f"""你是一位顶级的足球量化风控总监。以下是近期系统预测失败（错题）的比赛数据：
{wrong_matches}

当前我们 V25.0 模型已经使用了：Elo评级、赛程强度、xG、伤停等数据。
但依然出现了亏损。请分析：这些冷门/失败的原因是什么？是机构诱导（赔率异常）、还是核心球员意外伤退、还是杯赛轮换？
请输出 3 条以内极其深刻、能够直接作为未来预测铁律的【错题经验】，直接以 '-' 开头输出，方便我写入知识库。"""

try:
    res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
    review_report = res.choices[0].message.content.strip()
    
    # 提取经验并追加到 knowledge.txt
    with open('knowledge.txt', 'a', encoding='utf-8') as f:
        f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 错题深度归因 ---\n")
        f.write(review_report)
    print("✅ 错题经验已成功提炼并写入 knowledge.txt")
    
except Exception as e:
    review_report = f"AI 剖析失败: {e}"

html_report = f"""
<html><body style="font-family: sans-serif; padding: 20px;">
    <h2>🚨 V25.0 错题深度归因复盘</h2>
    <div style="background: #f8d7da; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <h3>❌ 近期错题汇总</h3>
        {pd.DataFrame(wrong_matches).to_html(index=False)}
    </div>
    <div style="background: #d1ecf1; padding: 15px; border-radius: 8px;">
        <h3>🧠 AI 总监深度剖析 (已入库)</h3>
        <p style="white-space: pre-wrap;">{review_report}</p>
    </div>
</body></html>
"""

send_email("🚨 V25.0 错题深度归因报告", html_report)

# 保存最新日志
df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
