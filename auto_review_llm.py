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

print("⏳ 正在启动 V44.1 深度复盘引擎...")
if not os.path.exists('predictions_log.csv'): 
    print("⚠️ 找不到预测日志，跳过复盘。")
    exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
today_str = today.strftime('%Y-%m-%d')

for c in ['actual_score', 'actual_result', 'is_win', 'profit', 'bet_amount', 'predicted_score', 'top3_scores']:
    if c not in df_log.columns: 
        df_log[c] = np.nan if 'amount' in c or 'profit' in c else ""

# 找出所有还没结算的比赛，且日期在今天之前（包含今天）
pending_review = df_log[(df_log['actual_score'].isna() | (df_log['actual_score'] == "")) & (df_log['date'].dt.strftime('%Y-%m-%d') <= today_str)].copy()

# 🌟 核心修复：清理超过3天的垃圾数据
if not pending_review.empty:
    pending_review['days_diff'] = (today - pending_review['date']).dt.days
    # 把超过3天的垃圾数据标记为“赛果丢失”
    expired_matches = pending_review[pending_review['days_diff'] > 3]
    if not expired_matches.empty:
        print(f"🧹 发现 {len(expired_matches)} 场比赛已过期(>3天)无赛果，自动作废。")
        for idx in expired_matches.index:
            df_log.at[idx, 'actual_score'] = "赛果丢失"
            df_log.at[idx, 'is_win'] = "作废"
            df_log.at[idx, 'profit'] = 0.0
        # 从待结算池中剔除这些过期数据
        pending_review = pending_review[~pending_review.index.isin(expired_matches.index)]

if pending_review.empty:
    print("✅ 没有需要复盘的新比赛。")
    html_report = f"""
    <html><body style="font-family: sans-serif; padding: 30px; text-align: center; background-color: #f4f7f6;">
        <h2 style="color: #2c3e50;">☕ 今日复盘完成</h2>
        <p style="color: #7f8c8d; font-size: 16px;">系统扫描了预测记录，目前没有已经完赛但尚未结算的比赛。</p>
        <p style="color: #7f8c8d; font-size: 14px;">资金账户安全，静待下一轮战斗。</p>
    </div></body></html>
    """
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig') # 必须保存清理后的日志
    send_email("☕ 每日复盘通知 (今日无战事)", html_report)
    exit()

print(f"⏳ 找到 {len(pending_review)} 场待复盘比赛，正在抓取真实赛果...")

actual_results = {}
for league_name, config in LEAGUES.items():
    for i in range(1, 6):
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
                    '预测Top3': pred_top3,
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
            '对阵': f"{row['home_team']} vs {row['away_team']}",
            '预测比分': pred_score,
            '实际比分': actual_score,
            '推荐赛果': row['predicted_result'],
            '命中状态': is_win,
            '盈亏': round(profit, 2)
        })

if total_count == 0:
    print("⚠️ 扫描到了比赛，但暂无已结算赛果，可能比赛还没踢完。")
    html_report = f"""
    <html><body style="font-family: sans-serif; padding: 30px; text-align: center; background-color: #f4f7f6;">
        <h2 style="color: #2c3e50;">⏳ 比赛尚未结算</h2>
        <p style="color: #7f8c8d; font-size: 16px;">系统扫描到了 {len(pending_review)} 场比赛，但在外部数据源中暂未查到最终赛果，可能比赛还没踢完，或者数据源有延迟。</p>
        <p style="color: #7f8c8d; font-size: 14px;">系统会在下次定时任务中自动重试结算。</p>
    </div></body></html>
    """
    df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig') # 保存日志
    send_email("⏳ 每日复盘通知 (待结算)", html_report)
    exit()

bankroll += total_profit
win_rate = (correct_count / total_count) * 100 if total_count > 0 else 0

new_bankroll_row = pd.DataFrame([{'日期': today_str, '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

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

html_table = pd.DataFrame(review_records).to_html(index=False, border=0, classes='report-table', justify='center')

css = """
<style>
    body { font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; }
    .container { max-width: 850px; margin: auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
    h1 { text-align: center; color: #2c3e50; border-bottom: 3px solid #e74c3c; padding-bottom: 15px; margin-bottom: 25px; }
    .stats-dashboard { display: flex; justify-content: space-around; background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 25px; border: 1px solid #e9ecef; }
    .stat-item { text-align: center; }
    .stat-value { font-size: 26px; font-weight: bold; color: #e74c3c; }
    .stat-label { font-size: 14px; color: #6c757d; margin-top: 5px; }
    .report-table { width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 14px; }
    .report-table th { background-color: #2c3e50; color: white; padding: 12px; text-align: center; }
    .report-table td { padding: 10px; border-bottom: 1px solid #dee2e6; text-align: center; }
    .report-table tr:hover { background-color: #f1f1f1; }
    .ai-box { background-color: #e8f4fd; border-left: 5px solid #3498db; padding: 20px; border-radius: 5px; font-size: 15px; line-height: 1.6; }
    .ai-box h3 { margin-top: 0; color: #2980b9; }
</style>
"""

html_content = f"""
<html><head>{css}</head>
<body>
<div class="container">
    <h1>💼 每日量化实盘财报与纠错战报</h1>
    
    <div class="stats-dashboard">
        <div class="stat-item">
            <div class="stat-value">{win_rate:.1f}%</div>
            <div class="stat-label">昨日胜率 ({correct_count}/{total_count})</div>
        </div>
        <div class="stat-item">
            <div class="stat-value" style="color: {'#27ae60' if total_profit >= 0 else '#c0392b'};">{total_profit:+.2f}</div>
            <div class="stat-label">昨日盈亏 (元)</div>
        </div>
        <div class="stat-item">
            <div class="stat-value" style="color: #2c3e50;">{bankroll:.2f}</div>
            <div class="stat-label">当前总资金</div>
        </div>
        <div class="stat-item">
            <div class="stat-value" style="color: #2980b9;">{((bankroll-10000)/10000)*100:+.2f}%</div>
            <div class="stat-label">累计 ROI</div>
        </div>
    </div>

    <h3 style="color: #34495e;">⚔️ 战况明细</h3>
    {html_table}

    <div class="ai-box">
        <h3>🧠 AI 深度纠错 (已沉淀至经验库)</h3>
        <p>{ai_report.replace(chr(10), '<br>')}</p>
    </div>
    
    <div style="text-align: center; color: #aaa; font-size: 12px; margin-top: 30px;">
        <p>系统自动生成 · 职业量化风控</p>
    </div>
</div>
</body></html>
"""

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
send_email("💼 每日量化实盘财报与纠错战报", html_content)
print("✅ 复盘完毕！")
