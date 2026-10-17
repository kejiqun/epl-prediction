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
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def send_email(subject, content, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = EMAIL_SENDER
    message['To'] = receiver
    message['Subject'] = Header(subject, 'utf-8')
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], message.as_string())
        print("✅ 复盘邮件发送成功！")
    except Exception as e:
        print(f"❌ 复盘邮件发送失败: {e}")

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
    if isinstance(name, str):
        return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

print("⏳ 正在抓取真实赛果，准备进行宏观赛后复盘...")
try:
    now = datetime.now()
    season = now.year if now.month >= 7 else now.year - 1
    url = f"https://api.football-data.org/v4/competitions/PL/matches?season={season}&status=FINISHED"
    headers = {'X-Auth-Token': FOOTBALL_DATA_API_KEY}
    resp = requests.get(url, headers=headers, timeout=15)
    
    if resp.status_code == 200:
        data = resp.json()
        finished_matches = []
        seven_days_ago = datetime.now() - timedelta(days=7)
        
        for m in data.get('matches', []):
            match_date = pd.to_datetime(m['utcDate']).tz_localize(None)
            if match_date >= seven_days_ago:
                finished_matches.append({
                    'date': m['utcDate'][:10],
                    'home_team': m['homeTeam']['name'],
                    'away_team': m['awayTeam']['name'],
                    'home_goals': m['score']['fullTime']['home'],
                    'away_goals': m['score']['fullTime']['away']
                })
        
        df_finished = pd.DataFrame(finished_matches)
        print(f"✅ 成功获取近7天 {len(df_finished)} 场真实完赛数据。")
    else:
        print(f"❌ API 获取失败：{resp.status_code}")
        df_finished = pd.DataFrame()

    if not df_finished.empty:
        review_text = f"【近期赛果复盘】\n"
        for _, row in df_finished.iterrows():
            home = translate_team_name(row['home_team'])
            away = translate_team_name(row['away_team'])
            review_text += f"- {row['date']}：{home} {row['home_goals']}-{row['away_goals']} {away}\n"
            
        print(review_text)
        
        prompt = f"""你是一位资深英超数据分析师。以下是近期结束的英超真实赛果：
{review_text}
请基于这些赛果，完成两项任务：
1. 整体点评这一轮比赛的特点（不超过100字）。
2. 作为预测模型的设计者，请总结一条用于优化模型的具体建议。
请用中文回答。"""
        
        response = llm_client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False
        )
        review_comment = response.choices[0].message.content.strip()
        
        print("\n" + "="*60)
        print(f"🧠 DeepSeek 宏观复盘：\n{review_comment}")
        print("="*60)
        
        review_text += f"\n🧠 DeepSeek 宏观复盘与进化建议：\n{review_comment}\n"
        send_email("近期英超真实赛果宏观复盘", review_text)
        
        print("\n⏳ 正在将新赛果追加到历史数据库...")
        try:
            df_hist = pd.read_csv('epl_matches_10y.csv')
            df_updated = pd.concat([df_hist, df_finished[['date', 'home_team', 'away_team', 'home_goals', 'away_goals']]], ignore_index=True)
            df_updated.drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last', inplace=True)
            df_updated.to_csv('epl_matches_10y.csv', index=False, encoding='utf-8-sig')
            print(f"✅ 数据追加成功！历史数据库从 {len(df_hist)} 场增加到 {len(df_updated)} 场。")
        except Exception as e:
            print(f"❌ 数据追加失败：{e}")
            
    else:
        print("⚠️ 近期没有获取到已结束的比赛。")
except Exception as e:
    print(f"⚠️ 获取赛果或复盘失败: {e}")