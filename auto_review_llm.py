import pandas as pd
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

print("⏳ 正在启动多联赛深度复盘引擎...")

if not os.path.exists('predictions_log.csv'):
    print("⚠️ 找不到 predictions_log.csv，跳过复盘。")
    exit()

# 1. 读取预测日志，找出过去 3 天需要复盘的比赛
df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
past_3_days = today - timedelta(days=3)

# 添加空列用于存放赛果（如果不存在的话）
if 'actual_score' not in df_log.columns: df_log['actual_score'] = ""
if 'actual_result' not in df_log.columns: df_log['actual_result'] = ""
if 'is_win' not in df_log.columns: df_log['is_win'] = ""

# 筛选出最近 3 天且尚未复盘的比赛
pending_review = df_log[(df_log['date'] >= past_3_days) & (df_log['actual_score'].isna() | (df_log['actual_score'] == ""))].copy()

if pending_review.empty:
    print("✅ 最近 3 天没有需要复盘的新比赛。")
    exit()

print(f"⏳ 找到 {len(pending_review)} 场待复盘比赛，正在抓取赛果...")

# 2. 循环各大联赛抓取赛果
actual_results = {} # 存储格式: {(date, home_cn, away_cn): (hg, ag)}

for league_name, config in LEAGUES.items():
    # 抓取过去 3 天的赛果
    for i in range(1, 4):
        date_str = (today - timedelta(days=i)).strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{config['espn_code']}/scoreboard?dates={date_str}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for event in data.get('events', []):
                    if event['status']['type']['state'] == 'post': # 已经完赛
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

# 3. 匹配赛果并计算对错
review_text_list = []
correct_count = 0
total_count = 0

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    h_cn = row['home_team']
    a_cn = row['away_team']
    pred_res = row['predicted_result']
    
    # 查找赛果
    res = actual_results.get((m_date, h_cn, a_cn))
    if res:
        hg, ag = res
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        is_win = "✅ 命中" if pred_res == actual_res else "❌ 错误"
        
        df_log.at[idx, 'actual_score'] = f"{hg}-{ag}"
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        
        total_count += 1
        if pred_res == actual_res: correct_count += 1
        
        review_text_list.append(f"比赛: {h_cn} vs {a_cn} [{row['league']}] | 预测: {pred_res} | 实际: {actual_res} ({hg}-{ag}) | 结果: {is_win}")

if total_count == 0:
    print("⚠️ 未能匹配到任何赛果（可能比赛还没踢完）。")
    exit()

# 4. 更新资金库 (简易版，假设每场按10块钱均注)
bankroll = 10000.0
if os.path.exists('bankroll.csv'):
    try:
        df_b = pd.read_csv('bankroll.csv')
        bankroll = df_b.iloc[-1]['当前资金']
    except: pass

win_rate = (correct_count / total_count) * 100
profit = (correct_count * 10 * 0.95) - ((total_count - correct_count) * 10) # 假设平均赔率1.95
bankroll += profit

# 5. AI 多联赛深度复盘
print("⏳ 正在呼叫 DeepSeek 进行多联赛深度复盘...")
knowledge_base = ""
if os.path.exists('knowledge.txt'):
    with open('knowledge.txt', 'r', encoding='utf-8') as f: knowledge_base = f.read()

prompt = f"""你是一位极其严苛的足球量化风控总监。今天我们跨多个联赛进行了预测，以下是刚刚结束的比赛结果：
{chr(10).join(review_text_list)}

当前总战绩：{correct_count} 胜 / {total_count} 场，本轮胜率 {win_rate:.1f}%。
【历史经验库】：
{knowledge_base}

**任务要求**：
1. 请分析这些预测错误的原因（特别是不同联赛的球风差异，比如德甲大球、意甲防守）。
2. 总结出 1-3 条可以直接写入代码或经验库的铁律。
3. 语气要犀利、专业。直接输出复盘报告，不要废话。"""

try:
    response = llm_client.chat.completions.create(
        model="deepseek-chat", 
        messages=[{"role": "user", "content": prompt}], 
        stream=False
    )
    review_report = response.choices[0].message.content.strip()
except Exception as e:
    review_report = f"AI复盘暂时不可用，报错: {e}"

# 6. 将新经验写入 knowledge.txt
with open('knowledge.txt', 'a', encoding='utf-8') as f:
    f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 复盘经验 ---\n")
    f.write(review_report)

# 7. 更新日志和资金，并发送邮件
df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

html_report = f"<html><body><h2>💡 多联赛深度复盘报告</h2>"
html_report += f"<h3>📊 本轮战绩：{correct_count} 胜 / {total_count} 场（胜率 {win_rate:.1f}%）</h3>"
html_report += f"<h3>💰 虚拟资金盈亏：{profit:+.2f} | 当前总资金：{bankroll:.2f}</h3>"
html_report += f"<hr><pre style='font-family: inherit; white-space: pre-wrap;'>{review_report}</pre></body></html>"

send_email("多联赛 V8.2 深度复盘报告", html_report)
print("✅ 复盘完毕！已生成报告并写入 knowledge.txt")
