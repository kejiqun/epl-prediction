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
        print("✅ 邮件发送成功！")
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

# ================= 核心：强制知识库提纯函数 =================
def distill_knowledge_base():
    if not os.path.exists('knowledge.txt'):
        return False
    
    with open('knowledge.txt', 'r', encoding='utf-8') as f:
        current_knowledge = f.read()
        
    if len(current_knowledge) < 500:
        print("✅ 知识库很小，无需提纯。")
        return False
        
    print(f"⏳ 触发大脑提纯！当前字数: {len(current_knowledge)}，正在压缩...")
    
    distill_prompt = f"""你是一位顶级的足球量化风控总监。现在你需要提取你大脑中的经验，请将以下冗长的历史经验库，提炼成不超过 8 条核心铁律。
要求：
1. 分类清晰（如：情报缺失类、赔率异常类、联赛风格类）。
2. 语言极其精炼，直击要害。
3. 直接输出提炼后的结果，不要任何废话。
经验内容：
{current_knowledge[:8000]}"""

    try:
        dist_resp = llm_client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": distill_prompt}], stream=False
        )
        distilled_text = dist_resp.choices[0].message.content.strip()
        
        # 备份旧文件
        backup_name = f'knowledge_backup_{datetime.now().strftime("%Y%m%d_%H%M")}.txt'
        os.rename('knowledge.txt', backup_name)
        
        # 写入新文件
        with open('knowledge.txt', 'w', encoding='utf-8') as f:
            f.write(f"--- 知识库提纯于 {datetime.now().strftime('%Y-%m-%d')} ---\n")
            f.write(distilled_text)
        print(f"✅ 提纯完成！已生成备份: {backup_name}")
        return True
    except Exception as e:
        print(f"⚠️ 提纯失败，保留原文件: {e}")
        return False
# ========================================================

print("⏳ 正在启动多联赛深度复盘引擎...")

# 每次运行，先强制执行一次知识库提纯检查（不管有没有比赛）
distill_knowledge_base()

if not os.path.exists('predictions_log.csv'):
    print("⚠️ 找不到 predictions_log.csv，跳过复盘。")
    exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
past_3_days = today - timedelta(days=3)

if 'actual_score' not in df_log.columns: df_log['actual_score'] = ""
if 'actual_result' not in df_log.columns: df_log['actual_result'] = ""
if 'is_win' not in df_log.columns: df_log['is_win'] = ""
if 'bet_amount' not in df_log.columns: df_log['bet_amount'] = 0.0
if 'profit' not in df_log.columns: df_log['profit'] = 0.0

pending_review = df_log[(df_log['date'] >= past_3_days) & (df_log['actual_score'].isna() | (df_log['actual_score'] == ""))].copy()

if pending_review.empty:
    print("✅ 最近 3 天没有需要复盘的新比赛。")
    html_report = f"""
    <html><body><div style="text-align: center; padding: 50px;">
        <h2 style="color: #2c3e50;">💡 今日复盘完成</h2>
        <p style="color: #666; font-size: 16px;">最近 3 天内没有需要复盘的新比赛，或者比赛尚未结束。</p>
        <p style="color: #27ae60; font-weight: bold;">（已触发日常知识库清理）</p>
    </div></body></html>"""
    send_email("💡 多联赛每日复盘报告", html_report)
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
            profit = 0.0
            
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
    print("⚠️ 未能匹配到任何赛果。")
    exit()

bankroll += total_profit
win_rate = (correct_count / total_count) * 100

print("⏳ 正在呼叫 DeepSeek 进行多维度结构化复盘...")
knowledge_base = ""
if os.path.exists('knowledge.txt'):
    with open('knowledge.txt', 'r', encoding='utf-8') as f: knowledge_base = f.read()

prompt = f"""你是一位顶级的足球量化风控总监。今天我们进行了跨联赛预测，以下是复盘数据：
{review_data}

当前资金：{bankroll:.2f}，本轮胜率：{win_rate:.1f}%。
【历史经验库】：{knowledge_base[:2000]}...

**任务**：
请生成一份【极简、结构化、神清气爽】的复盘报告。
必须严格包含以下三个模块，多写短句，少写长段，直接输出 Markdown 格式：

### 📊 一、 战场速览
### 🚨 二、 典型错题本
### 💡 三、 经验入库
- [规则1] ...
- [规则2] ...

请保持冷酷、专业、直接的风格。"""

try:
    response = llm_client.chat.completions.create(
        model="deepseek-chat", 
        messages=[{"role": "user", "content": prompt}], 
        stream=False
    )
    review_report_md = response.choices[0].message.content.strip()
except Exception as e:
    review_report_md = f"AI复盘暂时不可用，报错: {e}"

exp_matches = re.search(r'###\s*💡\s*三、\s*经验入库.*?\n(.*?)(?:\n###|\Z)', review_report_md, re.DOTALL)
if exp_matches:
    clean_exp = exp_matches.group(1).strip()
    with open('knowledge.txt', 'a', encoding='utf-8') as f:
        f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 新增经验 ---\n")
        f.write(clean_exp)
else:
    with open('knowledge.txt', 'a', encoding='utf-8') as f:
        f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 新增经验 ---\n{review_report_md}")

# 复盘完后，如果新增了经验，再次检查是否需要提纯
distill_knowledge_base()

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

html_content = review_report_md.replace('\n', '<br>').replace('###', '<h3 style="color:#2c3e50;border-left:4px solid #3498db;padding-left:10px;">').replace('- ', '• ')

html_report = f"""
<html>
<head>
<style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; background-color: #f9f9f9; padding: 20px; }}
    .container {{ max-width: 800px; margin: auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.05); }}
    .header {{ text-align: center; border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 20px; }}
    .stats-dashboard {{ display: flex; justify-content: space-around; background: #f0f8ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
    .stat-item {{ text-align: center; }}
    .stat-value {{ font-size: 24px; font-weight: bold; color: #0056b3; }}
    .stat-label {{ font-size: 14px; color: #666; }}
    .content {{ padding: 10px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h2>💡 足球量化多联赛深度复盘</h2>
        <p>{today.strftime('%Y-%m-%d')}</p>
    </div>
    
    <div class="stats-dashboard">
        <div class="stat-item">
            <div class="stat-value">{win_rate:.1f}%</div>
            <div class="stat-label">本轮胜率 ({correct_count}/{total_count})</div>
        </div>
        <div class="stat-item">
            <div class="stat-value" style="color: {'#27ae60' if total_profit >= 0 else '#c0392b'};">{total_profit:+.2f}</div>
            <div class="stat-label">盈亏变动</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{bankroll:.2f}</div>
            <div class="stat-label">当前资金</div>
        </div>
    </div>

    <div class="content">
        {html_content}
    </div>
    
    <div class="footer" style="text-align: center; color: #aaa; font-size: 12px; margin-top: 30px;">
        <p>系统自动生成 · 职业量化分析</p>
    </div>
</div>
</body>
</html>
"""

send_email("💡 多联赛深度复盘报告 (提纯完成)", html_report)
print("✅ 复盘与提纯检查完毕！")
