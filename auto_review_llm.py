import pandas as pd
import numpy as np
import requests
import os
import json
import warnings
from datetime import datetime, timedelta
from openai import OpenAI
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')
print("==================================================")
print("🚀 启动 V51.0 投行级量化实盘复盘引擎")
print("==================================================")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

# ================= 1. 玄学与视觉主题匹配 =================
def get_wuxing_theme():
    base_date = datetime(1900, 1, 31)
    today = datetime.now()
    days_diff = (today - base_date).days
    tiangan = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
    dizhi = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
    gan_idx = days_diff % 10
    zhi_idx = days_diff % 12
    day_ganzhi = tiangan[gan_idx] + dizhi[zhi_idx]
    wuxing_map = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土', '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
    element = wuxing_map[tiangan[gan_idx]]
    themes = {
        '木': {'bg': '#f4f7f6', 'primary': '#2e7d32', 'grad1': '#1b5e20', 'grad2': '#4caf50', 'icon': '🌳'},
        '火': {'bg': '#fdf5f5', 'primary': '#c62828', 'grad1': '#b71c1c', 'grad2': '#ef5350', 'icon': '🔥'},
        '土': {'bg': '#faf8f5', 'primary': '#e65100', 'grad1': '#bf360c', 'grad2': '#ff9800', 'icon': '⛰️'},
        '金': {'bg': '#f8f9fa', 'primary': '#c0a060', 'grad1': '#37474f', 'grad2': '#607d8b', 'icon': '⚔️'},
        '水': {'bg': '#f0f4f8', 'primary': '#1565c0', 'grad1': '#0d47a1', 'grad2': '#42a5f5', 'icon': '🌊'}
    }
    return day_ganzhi, element, themes[element]

DAY_GANZHI, ELEMENT, THEME = get_wuxing_theme()

# ================= 2. 发送邮件 =================
def send_email(subject, html, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    msg = MIMEMultipart('alternative')
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, receiver, Header(subject, 'utf-8')
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
        print("✅ 复盘邮件发送成功！")
    except Exception as e: 
        print(f"❌ 邮件发送失败: {e}")

# ================= 3. 数据加载与赛果抓取 =================
if not os.path.exists('predictions_log.csv'):
    print("❌ 没有找到 predictions_log.csv，跳过复盘。")
    exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
yesterday_str = (today - timedelta(days=1)).strftime('%Y-%m-%d')

# 筛选出尚未结算的比赛（实际比分为空，且日期<=昨天）
pending = df_log[(df_log['actual_score'].isna()) & (df_log['date'].dt.strftime('%Y-%m-%d') <= yesterday_str)].copy()

if pending.empty:
    print("✅ 没有需要复盘的新比赛。")
    exit()

print(f"⏳ 发现 {len(pending)} 场比赛待结算，正在通过 API 抓取真实赛果...")

headers = {"x-apisports-key": API_FOOTBALL_KEY}
actual_results = {}
# 获取过去 5 天的赛果，防止时差问题
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
                    # 构建全局赛果字典，不依赖日期匹配
                    actual_results[(h_name, a_name)] = (hg, ag)
    except: 
        pass

# ================= 4. 盈亏计算与现金流汇总 =================
review_records = []
win_records_for_ai = []
loss_records_for_ai = []

total_count = 0
correct_count = 0
total_profit = 0.0
today_profit = 0.0

for idx, row in pending.iterrows():
    m_date_str = row['date'].strftime('%Y-%m-%d')
    res = actual_results.get((row['home_team'], row['away_team']))
    
    if res:
        hg, ag = res
        actual_score = f"{hg}-{ag}"
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        pred_res = row.get('predicted_result', '未知')
        pred_score = row.get('predicted_score', '未知')
        
        bet = float(row.get('bet_amount', 0)) if pd.notna(row.get('bet_amount')) else 0.0
        profit = 0.0
        is_win = "观望"
        
        if bet > 0:
            total_count += 1
            if pred_res == actual_res:
                correct_count += 1
                is_win = "✅ 命中"
                if pred_res == "主胜": profit = bet * (float(row.get('odds_h', 2.0)) - 1)
                elif pred_res == "平局": profit = bet * (float(row.get('odds_d', 3.3)) - 1)
                else: profit = bet * (float(row.get('odds_a', 3.5)) - 1)
                
                win_records_for_ai.append({
                    '比赛': f"{row['home_team']} vs {row['away_team']}", '预测': pred_res, '比分': pred_score, '实际': actual_score
                })
            else:
                is_win = "❌ 失手"
                profit = -bet
                
                loss_records_for_ai.append({
                    '比赛': f"{row['home_team']} vs {row['away_team']}", '预测': pred_res, '实际': actual_res,
                    '伤停': row.get('home_injuries', '') + " / " + row.get('away_injuries', '')
                })
        
        today_profit += profit
        total_profit += profit
        
        # 回写数据
        df_log.at[idx, 'actual_score'] = actual_score
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        df_log.at[idx, 'profit'] = round(profit, 2)
        
        review_records.append({
            '日期': m_date_str, '赛事': row['league'], '对阵': f"{row['home_team']} vs {row['away_team']}",
            '预测': pred_res, '实际': actual_res, '对比': is_win,
            '比分(预测/实际)': f"{pred_score} / {actual_score}",
            '金额': bet, '盈亏': round(profit, 2)
        })

# ================= 5. 资金库读写与财务仪表盘 =================
bankroll = 10000.0
if os.path.exists('bankroll.csv'):
    try: 
        df_bank = pd.read_csv('bankroll.csv')
        bankroll = df_bank.iloc[-1]['当前资金']
    except: 
        pass

bankroll += today_profit
new_row = pd.DataFrame([{'日期': today.strftime('%Y-%m-%d'), '当前资金': round(bankroll, 2), '盈亏': round(today_profit, 2)}])

if os.path.exists('bankroll.csv'):
    df_bank = pd.concat([df_bank, new_row]).drop_duplicates(subset=['日期'], keep='last')
else:
    df_bank = new_row
df_bank.to_csv('bankroll.csv', index=False, encoding='utf-8-sig')

# 计算月度汇总
df_bank['月份'] = pd.to_datetime(df_bank['日期']).dt.strftime('%Y-%m')
current_month = today.strftime('%Y-%m')
month_profit = df_bank[df_bank['月份'] == current_month]['盈亏'].sum()
win_rate = (correct_count / total_count * 100) if total_count > 0 else 0.0

# ================= 6. 双轨 AI 分析 =================
ai_win_analysis = "今日无预测正确的比赛。"
ai_loss_analysis = "今日防守完美，无预测错误的比赛。"

if llm_client:
    if win_records_for_ai:
        prompt_win = f"作为量化分析师，请用100字简要总结以下我们预测精准的比赛，提炼关键成功因素：{win_records_for_ai}"
        try:
            res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt_win}], stream=False)
            ai_win_analysis = res.choices[0].message.content.strip()
        except: pass

    if loss_records_for_ai:
        prompt_loss = f"作为首席风控官，请用150字详细剖析以下预测失败的比赛，深刻反思原因（如红牌、伤停影响、机构诱盘等），并给出纠错建议：{loss_records_for_ai}"
        try:
            res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt_loss}], stream=False)
            ai_loss_analysis = res.choices[0].message.content.strip()
            # 写入经验库
            with open('knowledge.txt', 'a', encoding='utf-8') as f:
                f.write(f"\n\n--- {today.strftime('%Y-%m-%d')} 亏损纠错 ---\n{ai_loss_analysis}")
        except: pass

# ================= 7. 组装顶级投行级 HTML 报表 =================
# 生成明细表格行
table_rows = ""
for r in review_records:
    color = "#27ae60" if r['盈亏'] > 0 else ("#c0392b" if r['盈亏'] < 0 else "#333")
    sign = "+" if r['盈亏'] > 0 else ""
    table_rows += f"""
    <tr style="border-bottom: 1px solid #eee;">
        <td style="padding: 12px;">{r['日期']}</td>
        <td style="padding: 12px;">{r['赛事']}</td>
        <td style="padding: 12px; font-weight: bold;">{r['对阵']}</td>
        <td style="padding: 12px; text-align: center;">{r['预测']}</td>
        <td style="padding: 12px; text-align: center;">{r['实际']}</td>
        <td style="padding: 12px; text-align: center;">{r['对比']}</td>
        <td style="padding: 12px; text-align: center; color: #666;">{r['比分(预测/实际)']}</td>
        <td style="padding: 12px; text-align: right;">{r['金额']:.2f}</td>
        <td style="padding: 12px; text-align: right; font-weight: bold; color: {color};">{sign}{r['盈亏']:.2f}</td>
    </tr>
    """

html = f"""
<html>
<body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: {THEME['bg']}; padding: 20px; color: #333;">
<div style="max-width: 950px; margin: auto;">

    <!-- 顶部标题 -->
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: {THEME['primary']}; margin: 0; font-size: 26px; letter-spacing: 1px;">🏛️ 每日量化实盘复盘晨报</h1>
        <p style="color: #666; font-size: 14px; margin-top: 10px; background: #fff; display: inline-block; padding: 6px 15px; border-radius: 20px; border: 1px solid #ddd;">
            日期：{today.strftime('%Y-%m-%d')} | 农历：<b>{DAY_GANZHI}</b>日 (属{ELEMENT})
        </p>
    </div>

    <!-- 卡片一：财务现金流量表 -->
    <div style="background: #fff; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 25px; border-top: 5px solid {THEME['primary']};">
        <div style="padding: 20px; border-bottom: 1px solid #eee;">
            <h2 style="margin: 0; color: #2c3e50; font-size: 18px;">📊 核心财务数据 (Financial Summary)</h2>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 25px; text-align: center;">
            <div>
                <div style="font-size: 13px; color: #666; margin-bottom: 5px;">当日盈亏</div>
                <div style="font-size: 24px; font-weight: bold; color: {'#27ae60' if today_profit >= 0 else '#c0392b'};">
                    {'+' if today_profit >= 0 else ''}{today_profit:.2f}
                </div>
            </div>
            <div>
                <div style="font-size: 13px; color: #666; margin-bottom: 5px;">月度累计盈亏</div>
                <div style="font-size: 24px; font-weight: bold; color: {'#27ae60' if month_profit >= 0 else '#c0392b'};">
                    {'+' if month_profit >= 0 else ''}{month_profit:.2f}
                </div>
            </div>
            <div>
                <div style="font-size: 13px; color: #666; margin-bottom: 5px;">当日胜率</div>
                <div style="font-size: 24px; font-weight: bold; color: {THEME['primary']};">
                    {win_rate:.1f}%
                </div>
            </div>
            <div>
                <div style="font-size: 13px; color: #666; margin-bottom: 5px;">当前总资金</div>
                <div style="font-size: 24px; font-weight: bold; color: #2c3e50;">
                    {bankroll:.2f}
                </div>
            </div>
        </div>
    </div>

    <!-- 卡片二：实盘流水明细 -->
    <div style="background: #fff; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 25px;">
        <div style="padding: 20px; border-bottom: 1px solid #eee;">
            <h2 style="margin: 0; color: #2c3e50; font-size: 18px;">📑 实盘交易明细 (Trade Blotter)</h2>
        </div>
        <div style="padding: 20px; overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #2c3e50; color: white;">
                        <th style="padding: 12px; text-align: left;">日期</th>
                        <th style="padding: 12px; text-align: left;">赛事</th>
                        <th style="padding: 12px; text-align: left;">对阵</th>
                        <th style="padding: 12px;">预测</th>
                        <th style="padding: 12px;">实际</th>
                        <th style="padding: 12px;">对比</th>
                        <th style="padding: 12px;">比分(预/实)</th>
                        <th style="padding: 12px; text-align: right;">本金</th>
                        <th style="padding: 12px; text-align: right;">盈亏</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>

    <!-- 卡片三：AI 归因分析 -->
    <div style="background: #fff; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 25px;">
        <div style="padding: 20px; border-bottom: 1px solid #eee;">
            <h2 style="margin: 0; color: #2c3e50; font-size: 18px;">🧠 AI 投研归因复盘 (CIO's Note)</h2>
        </div>
        <div style="padding: 25px;">
            <!-- 盈利归因 -->
            <div style="background: #f0fdf4; border-left: 4px solid #27ae60; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 10px 0; color: #27ae60; font-size: 15px;">✅ 盈利归因与经验沉淀 (Wins)</h3>
                <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #333;">{ai_win_analysis}</p>
            </div>
            
            <!-- 亏损纠错 -->
            <div style="background: #fef2f2; border-left: 4px solid #c0392b; padding: 15px; border-radius: 6px;">
                <h3 style="margin: 0 0 10px 0; color: #c0392b; font-size: 15px;">❌ 亏损深度剖析与查漏补缺 (Losses)</h3>
                <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #333;">{ai_loss_analysis}</p>
            </div>
        </div>
    </div>

    <!-- 页脚 -->
    <div style="text-align: center; color: #888; font-size: 12px; margin-top: 30px;">
        <p>由 DeepSeek V51.0 量化决策引擎自动生成</p>
    </div>

</div>
</body>
</html>
"""

# ================= 8. 保存并发送 =================
df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
send_email(f"🏛️ 每日量化实盘复盘晨报 ({DAY_GANZHI}日·{ELEMENT})", html)
print("✅ 复盘完毕！")
