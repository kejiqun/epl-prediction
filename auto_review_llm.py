import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime, timedelta
from openai import OpenAI
import warnings
import smtplib
from email.mime.text import MIMEText
from email.header import Header

warnings.filterwarnings('ignore')
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def send_email(subject, content, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = EMAIL_SENDER; message['To'] = receiver; message['Subject'] = Header(subject, 'utf-8')
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], message.as_string())
    except Exception as e: print(f"❌ 复盘邮件发送失败: {e}")

team_mapping = {
    'Arsenal FC': '阿森纳', 'Arsenal': '阿森纳', 'Aston Villa FC': '阿斯顿维拉', 'Aston Villa': '阿斯顿维拉',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Brighton & Hove Albion FC': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西', 'Crystal Palace FC': '水晶宫', 'Crystal Palace': '水晶宫',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿', 'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Ipswich Town FC': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester City FC': '莱斯特城', 'Leicester City': '莱斯特城',
    'Liverpool FC': '利物浦', 'Liverpool': '利物浦', 'Manchester City FC': '曼城', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United FC': '曼联', 'Manchester United': '曼联', 'Man United': '曼联',
    'Newcastle United FC': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联', 'Newcastle': '纽卡斯尔联',
    'Nottingham Forest FC': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林',
    'Southampton FC': '南安普顿', 'Southampton': '南安普顿', 'Tottenham Hotspur FC': '托特纳姆热刺', 'Tottenham Hotspur': '托特纳姆热刺',
    'West Ham United FC': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolverhampton Wanderers FC': '狼队', 'Wolverhampton Wanderers': '狼队',
    'Leeds United FC': '利兹联', 'Leeds United': '利兹联', 'Sunderland AFC': '桑德兰', 'Sunderland': '桑德兰',
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂'
}
def translate_team_name(name):
    if isinstance(name, str): return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

print("⏳ 正在抓取真实赛果，进行 V13 微观与宏观复盘...")
try:
    finished_matches = []
    seven_days_ago = datetime.now() - timedelta(days=7)
    for i in range(7):
        date_str = (seven_days_ago + timedelta(days=i)).strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={date_str}"
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
                            finished_matches.append({
                                'date': event['date'][:10],
                                'home_team': translate_team_name(home['team']['name']), 
                                'away_team': translate_team_name(away['team']['name']),
                                'home_goals': int(home.get('score', 0)), 
                                'away_goals': int(away.get('score', 0))
                            })
    
    df_finished = pd.DataFrame(finished_matches)

    if not df_finished.empty:
        match_details_text = ""
        # 🌟 V16 核心：虚拟实盘 ROI 追踪
        bankroll_file = 'bankroll.csv'
        if not os.path.exists(bankroll_file):
            pd.DataFrame([{'date': '2026-01-01', 'balance': 10000, 'pnl': 0, 'bet_count': 0}]).to_csv(bankroll_file, index=False)
            
        current_bankroll = pd.read_csv(bankroll_file).iloc[-1]
        balance = current_bankroll['balance']
        bet_count = current_bankroll['bet_count']
        weekly_pnl = 0
        
        if os.path.exists('predictions_log.csv'):
            log_df = pd.read_csv('predictions_log.csv')
            for _, row in df_finished.iterrows():
                pred_match = log_df[(log_df['date'] == row['date']) & 
                                    (log_df['home_team'] == row['home_team']) & 
                                    (log_df['away_team'] == row['away_team'])]
                if not pred_match.empty:
                    p = pred_match.iloc[-1]
                    actual_res = "主胜" if row['home_goals'] > row['away_goals'] else ("平局" if row['home_goals'] == row['away_goals'] else "客胜")
                    
                    # 检查凯利下注是否命中
                    odds_h = p.get('odds_h', 2.0)
                    odds_d = p.get('odds_d', 3.0)
                    odds_a = p.get('odds_a', 3.0)
                    
                    bet_amount = 0
                    payout = 0
                    
                    # 如果当时模型推荐了主胜且有凯利价值，模拟下注
                    if p['predicted_result'] == '主胜' and p['pred_prob_h'] > (1/odds_h):
                        bet_pct = (p['pred_prob_h'] * odds_h - 1) / (odds_h - 1)
                        bet_amount = balance * max(0, bet_pct) * 0.1 # 取10%分数凯利防破产
                        if actual_res == '主胜': payout = bet_amount * odds_h
                        else: payout = 0
                    elif p['predicted_result'] == '客胜' and p['pred_prob_a'] > (1/odds_a):
                        bet_pct = (p['pred_prob_a'] * odds_a - 1) / (odds_a - 1)
                        bet_amount = balance * max(0, bet_pct) * 0.1
                        if actual_res == '客胜': payout = bet_amount * odds_a
                        else: payout = 0
                        
                    if bet_amount > 0:
                        net_profit = payout - bet_amount
                        weekly_pnl += net_profit
                        bet_count += 1
                        match_details_text += f"- {row['home_team']} {row['home_goals']}-{row['away_goals']} {row['away_team']} | 实际: {actual_res} | 投注: {bet_amount:.0f} | 盈亏: {net_profit:.0f}\n"

        balance += weekly_pnl
        # 保存最新资金账户
        pd.DataFrame([{'date': datetime.now().strftime('%Y-%m-%d'), 'balance': balance, 'pnl': weekly_pnl, 'bet_count': bet_count}]).to_csv(bankroll_file, mode='a', header=False, index=False)

        review_text = f"【近期赛果复盘】\n"
        for _, row in df_finished.iterrows():
            review_text += f"- {row['date']}：{row['home_team']} {row['home_goals']}-{row['away_goals']} {row['away_team']}\n"
            
        prompt = f"""你是一位资深英超分析师。请基于以下真实赛果与预测对比，完成两项任务：
1. 微观归因：分析预测错误或正确的比赛，找出原因（不超过100字）。
2. 提炼一条优化经验，用“经验：”开头（不超过50字）。

【预测对比与虚拟盘口】：
{match_details_text if match_details_text else "暂无匹配的预测记录"}
"""
        
        response = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        review_comment = response.choices[0].message.content.strip()
        
        print("\n" + "="*60)
        print(f"🧠 DeepSeek V13 复盘：\n{review_comment}")
        print(f"💰 本周虚拟资金盈亏：{weekly_pnl:.2f} | 当前总资金：{balance:.2f}")
        print("="*60)
        
        if "经验：" in review_comment:
            new_knowledge = review_comment.split("经验：")[-1].strip()
            with open('knowledge.txt', 'a', encoding='utf-8') as f:
                f.write(f"- [{datetime.now().strftime('%Y-%m-%d')}] {new_knowledge}\n")
            print(f"✅ 已成功将新经验追加到 knowledge.txt 中！")
        
        send_email("近期英超 V16 复盘与资金报表", review_text + f"\n本周盈亏: {weekly_pnl:.2f} | 当前资金: {balance:.2f}\n" + review_comment)
        
        print("\n⏳ 正在将新赛果追加到历史数据库...")
        try:
            df_hist = pd.read_csv('epl_matches_10y.csv')
            df_finished['home_team_en'] = df_finished['home_team'].map({v: k for k, v in team_mapping.items()}).fillna(df_finished['home_team'])
            df_finished['away_team_en'] = df_finished['away_team'].map({v: k for k, v in team_mapping.items()}).fillna(df_finished['away_team'])
            new_data = df_finished[['date', 'home_team_en', 'away_team_en', 'home_goals', 'away_goals']].copy()
            new_data.columns = ['date', 'home_team', 'away_team', 'home_goals', 'away_goals']
            df_updated = pd.concat([df_hist, new_data], ignore_index=True)
            df_updated.drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last', inplace=True)
            df_updated.to_csv('epl_matches_10y.csv', index=False, encoding='utf-8-sig')
            print(f"✅ 数据追加成功！")
        except Exception as e: print(f"❌ 数据追加失败：{e}")
            
except Exception as e:
    print(f"⚠️ 获取赛果或复盘失败: {e}")