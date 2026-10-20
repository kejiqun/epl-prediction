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

print("⏳ 正在启动多联赛深度复盘引擎 (V8.3 量化风控版)...")

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
if 'profit' not in df_log.columns: df_log['profit'] = 0.0

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

# 🌟 资金管理：读取当前资金，采用平注限额或凯利
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
        
        # 计算单场盈亏（基于推荐赛果的真实赔率，假设下注资金 2%）
        bet_amount = bankroll * 0.02
        if pred_res == actual_res:
            correct_count += 1
            if pred_res == "主胜": profit = bet_amount * (row['odds_h'] - 1)
            elif pred_res == "平局": profit = bet_amount * (row['odds_d'] - 1)
            else: profit = bet_amount * (row['odds_a'] - 1)
        else:
            profit = -bet_amount
            
        total_profit += profit
        total_count += 1
        
        df_log.at[idx, 'actual_score'] = f"{hg}-{ag}"
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        df_log.at[idx, 'profit'] = round(profit, 2)
        
        # 收集用于 AI 分析的数据
        review_data.append({
            "联赛": row['league'], "比赛": f"{h_cn} vs {a_cn}",
            "预测": pred_res, "实际": actual_res, "比分": f"{hg}-{ag}",
            "模型概率": f"主{row['pred_prob_h']*100:.0f}% 平{row['pred_prob_d']*100:.0f}% 客{row['pred_prob_a']*100:.0f}%",
            "赔率": f"主{row['odds_h']} 平{row['odds_d']} 客{row['odds_a']}",
            "结果": is_win
        })

if total_count == 0:
    print("⚠️ 未能匹配到任何赛果（可能比赛还没踢完）。")
    exit()

bankroll += total_profit
win_rate = (correct_count / total_count) * 100

# 🌟 重构 Prompt：要求极其结构化、简练、图文并茂
print("⏳ 正在呼叫 DeepSeek 进行多维度结构化复盘...")
knowledge_base = ""
if os.path.exists('knowledge.txt'):
    with open('knowledge.txt', 'r', encoding='utf-8') as f: knowledge_base = f.read()

prompt = f"""你是一位顶级的足球量化风控总监。今天我们进行了跨联赛预测，以下是复盘数据：
{review_data}

当前资金：{bankroll:.2f}，本轮胜率：{win_rate:.1f}%。
【历史经验库】：{knowledge_base[:2000]}... (截取前部以避免超长)

**任务**：
请生成一份【极简、结构化、神清气爽】的复盘报告。
必须严格包含以下四个模块，多写短句，少写长段，直接输出 Markdown 格式（我会将其转为图文邮件）：

### 📊 一、 战场速览
（用一段话总结本轮表现，点出红黑榜：表现最好的联赛 vs 表现最差的联赛）

### 🚨 二、 典型错题本（核心）
（挑出 1-2 场最有代表性的错局，用以下格式）
* **比赛**：[主队] vs [客队]（[联赛]）
* **死因**：...（必须精准指出是：阵型克制？情报缺失？还是模型对特定赔率的盲区？）
* **相似情境防坑指南**：如果未来再出现“类似赔率 + 类似球队状态”，系统应该怎么做？

### 💡 三、 经验入库（直接写入知识库）
（请提炼 2 条极其精炼、可以直接作为特征工程或规则过滤的代码级经验。字数不超过 50 字/条，例如：“德甲客队让步大于0.5时，若情报缺失，强制拉高平局概率15%。”）

### 🎯 四、 下一步行动指令
（给开发者的 1 条修改建议，比如：“下次预测时，重点关注意甲主场龙球队的浅盘”）

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

# 将最精炼的经验写入 knowledge.txt (只提取第三部分)
with open('knowledge.txt', 'a', encoding='utf-8') as f:
    f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 复盘经验 ---\n")
    if "### 💡 三、 经验入库" in review_report_md:
        exp_section = review_report_md.split("### 💡 三、 经验入库")[1].split("###")[0]
        f.write(exp_section.strip())
    else:
        f.write(review_report_md)

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

# 🌟 重构 HTML 邮件：卡片式设计，极其清晰
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
    .content h3 {{ color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; margin-top: 30px; }}
    .content p {{ margin-bottom: 10px; }}
    .content ul, .content ol {{ padding-left: 20px; }}
    .content li {{ margin-bottom: 8px; }}
    .content blockquote {{ border-left: 4px solid #e74c3c; background: #fdf2f2; padding: 10px; margin: 0; color: #c0392b; font-weight: bold; }}
    .footer {{ text-align: center; color: #aaa; font-size: 12px; margin-top: 30px; }}
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
        {review_report_md.replace(chr(10), '<br>').replace('###', '<h3>').replace('* ', '• ')}
    </div>
    
    <div class="footer">
        <p>系统自动生成 · 职业量化分析</p>
    </div>
</div>
</body>
</html>
"""

send_email("💡 多联赛 V8.3 极简深度复盘报告", html_report)
print("✅ 复盘完毕！已生成图文报告并精简写入 knowledge.txt")
