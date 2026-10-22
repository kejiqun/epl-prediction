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

print("⏳ 正在启动 V33.1 比分深度纠错复盘引擎...")
if not os.path.exists('predictions_log.csv'): 
    print("⚠️ 找不到预测日志，跳过复盘。")
    exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')

# 补齐缺失列
for c in ['actual_score', 'actual_result', 'is_win', 'profit', 'bet_amount', 'predicted_score', 'top3_scores']:
    if c not in df_log.columns: 
        df_log[c] = np.nan if 'amount' in c or 'profit' in c else ""

# 提取昨天的比赛
pending_review = df_log[(df_log['date'].dt.strftime('%Y-%m-%d') == yesterday) & (df_log['actual_score'].isna() | (df_log['actual_score'] == ""))].copy()

if pending_review.empty:
    print("✅ 昨天没有需要复盘的新比赛。")
    exit()

print(f"⏳ 找到 {len(pending_review)} 场待复盘比赛，正在抓取真实赛果...")

actual_results = {}
for league_name, config in LEAGUES.items():
    for i in range(1, 3):
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
score_analysis_data = [] # 专门收集比分差异的素材

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
                
                # 记录错题，用于后续AI分析
                wrong_matches.append({
                    '比赛': f"{row['home_team']} vs {row['away_team']}",
                    '预测赛果': row['predicted_result'], '实际赛果': actual_res,
                    '预测比分': pred_score, '实际比分': actual_score,
                    '预测Top3': pred_top3,
                    '伤停': f"主[{row.get('home_injuries', '无')}] 客[{row.get('away_injuries', '无')}]"
                })
        
        # 不管输赢，只要有比分预测，就进入比分误差分析池（用于让AI总结进球数差异）
        if pred_score != '未知' and pred_score != actual_score:
            score_analysis_data.append({
                '比赛': f"{row['home_team']} vs {row['away_team']}",
                '预期比分': pred_score,
                '实际比分': actual_score,
                '偏差类型': "进球数低估" if hg+ag > int(pred_score.split('-')[0])+int(pred_score.split('-')[1]) else "进球数高估"
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

if total_count == 0 and len(score_analysis_data) == 0:
    print("⚠️ 昨日比赛未产生有效复盘数据。")
    exit()

bankroll += total_profit
win_rate = (correct_count / total_count) * 100 if total_count > 0 else 0

# 更新资金库
new_bankroll_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(total_profit, 2)}])
if os.path.exists('bankroll.csv'):
    df_bank = pd.read_csv('bankroll.csv')
    df_bank = pd.concat([df_bank, new_bankroll_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_bankroll_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

# 🌟 核心升级：AI 深度比分纠错
ai_report = ""
if wrong_matches or len(score_analysis_data) > 3:
    print(f"🚨 发现赛果或比分误差，呼叫 AI 进行深度剖析...")
    prompt = f"""你是一位顶级足球量化总监。今天我们进行了一次复盘。
    
    【实盘错题本 (赛果买反了)】:
    {wrong_matches}
    
    【比分偏差池 (进球数预期不符)】:
    {score_analysis_data[:10]} # 限制长度防止token超限
    
    **任务要求**：
    1. 请剖析赛果失败的原因（是机构诱盘？红牌意外？还是战术克制？）。
    2. **极其重要**：请重点对比“预期比分”和“实际比分”，为什么进球数偏差这么大？是我方高估了进攻（比如预期2-1，实际0-0），还是低估了防守？
    3. 请输出 3 条以内极其深刻的【比分预测纠错铁律】，直接以 '-' 开头，方便我写入知识库。
    4. 保持冷酷、专业的语气。"""
    
    try:
        res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        ai_report = res.choices[0].message.content.strip()
        with open('knowledge.txt', 'a', encoding='utf-8') as f:
            f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 深度比分纠错 ---\n{ai_report}")
    except Exception as e: ai_report = f"AI 剖析失败: {e}"
else:
    ai_report = "完美！昨日无赛果错题，且比分预测与实际结果高度吻合，无需调整。"

# 生成精美 HTML 表格
df_review = pd.DataFrame(review_records)
if not df_review.empty:
    html_table = df_review.to_html(index=False, border=0, classes='review-table', justify='center')
else:
    html_table = "<p>昨日无实盘推荐结算。</p>"

css = """
<style>
    body { font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; }
    .container { max-width: 800px; margin: auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
    h1 { text-align: center; color: #2c3e50; border-bottom: 3px solid #e74c3c; padding-bottom: 15px; margin-bottom: 25px; }
    .stats-dashboard { display: flex; justify-content: space-around; background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 25px; border: 1px solid #e9ecef; }
    .stat-item { text-align: center; }
    .stat-value { font-size: 26px; font-weight: bold; color: #e74c3c; }
    .stat-label { font-size: 14px; color: #6c757d; margin-top: 5px; }
    .review-table { width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 14px; }
    .review-table th { background-color: #34495e; color: white; padding: 12px; text-align: center; }
    .review-table td { padding: 10px; border-bottom: 1px solid #dee2e6; text-align: center; }
    .review-table tr:hover { background-color: #f1f1f1; }
    .ai-box { background-color: #e8f4fd; border-left: 5px solid #3498db; padding: 20px; border-radius: 5px; font-size: 15px; line-height: 1.6; }
    .ai-box h3 { margin-top: 0; color: #2980b9; }
</style>
"""

html_content = f"""
<html><head>{css}</head>
<body>
<div class="container">
    <h1>💡 每日量化复盘与比分纠错战报</h1>
    
    <div class="stats-dashboard">
        <div class="stat-item">
            <div class="stat-value">{win_rate:.1f}%</div>
            <div class="stat-label">昨日赛果胜率 ({correct_count}/{total_count})</div>
        </div>
        <div class="stat-item">
            <div class="stat-value" style="color: {'#27ae60' if total_profit >= 0 else '#c0392b'};">{total_profit:+.2f}</div>
            <div class="stat-label">昨日盈亏 (元)</div>
        </div>
        <div class="stat-item">
            <div class="stat-value" style="color: #2c3e50;">{bankroll:.2f}</div>
            <div class="stat-label">当前总资金</div>
        </div>
    </div>

    <h3 style="color: #34495e;">⚔️ 昨日战况明细 (比分对比)</h3>
    {html_table}

    <div class="ai-box">
        <h3>🧠 AI 深度比分纠错 (已沉淀至经验库)</h3>
        <p>{ai_report.replace(chr(10), '<br>')}</p>
    </div>
    
    <div style="text-align: center; color: #aaa; font-size: 12px; margin-top: 30px;">
        <p>系统自动生成 · 职业量化风控</p>
    </div>
</div>
</body></html>
"""

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
send_email("💡 每日量化复盘与比分纠错战报", html_content)
print("✅ 复盘完毕！")
