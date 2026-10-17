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
from espn_sports_api import Soccer

warnings.filterwarnings('ignore')

# ==================== 密钥配置 ====================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def send_email(subject, content, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = EMAIL_SENDER  # 修复 550 错误
    message['To'] = receiver
    message['Subject'] = Header(subject, 'utf-8')
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], message.as_string())
        print("✅ 复盘邮件发送成功！")
    except Exception as e:
        print(f"❌ 复盘邮件发送失败: {e}")

# 🌟 中英文球队对照字典
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
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂',
    'Burnley FC': '伯恩利', 'Burnley': '伯恩利', 'Sheffield United FC': '谢菲尔德联', 'Sheffield United': '谢菲尔德联',
    'Luton Town FC': '卢顿', 'Luton Town': '卢顿', 'Watford FC': '沃特福德', 'Watford': '沃特福德', 'Norwich City FC': '诺维奇', 'Norwich City': '诺维奇'
}
def translate_team_name(name):
    if isinstance(name, str):
        return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

print("⏳ 正在抓取真实赛果，准备进行宏观赛后复盘...")
try:
    epl = Soccer(league="epl")
    # 抓取过去 7 天的比赛结果
    today = datetime.now().date()
    start_date = today - timedelta(days=7)
    
    # 尝试从 ESPN 获取赛果
    finished_matches = epl.date_range(start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
    
    review_text = f"【近期赛果复盘】\n"
    valid_matches_count = 0
    
    for match in finished_matches:
        # 判断比赛是否已结束并包含比分
        if match.get('status') == 'FINISHED' or (match.get('home_goals') is not None and match.get('away_goals') is not None):
            match_date = match.get('date', '时间未知')[:10]
            home_team = translate_team_name(match.get('home_team', {}).get('name', '未知'))
            away_team = translate_team_name(match.get('away_team', {}).get('name', '未知'))
            hg = match.get('home_goals')
            ag = match.get('away_goals')
            
            # 🌟 强制打印日期和球队
            review_text += f"- {match_date}：{home_team} {hg}-{ag} {away_team}\n"
            valid_matches_count += 1
            
    if valid_matches_count > 0:
        print(review_text)
        prompt = f"""你是一位资深英超数据分析师。以下是近期结束的英超真实赛果：
{review_text}
请基于这些赛果，完成两项任务：
1. 整体点评这一轮比赛的特点（不超过100字）。
2. 作为预测模型的设计者，请从这些结果中总结出一条用于**优化下一版V12模型**的具体建议（例如：是否需要加大主场权重、是否应加强对保级队死守平局的预测等）。
请用中文回答，条理清晰。"""
        
        response = llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        review_comment = response.choices[0].message.content.strip()
        
        print("\n" + "="*60)
        print("🧠 DeepSeek 宏观复盘与进化建议：")
        print(review_comment)
        print("="*60)
        
        review_text += f"\n🧠 DeepSeek 宏观复盘与进化建议：\n{review_comment}\n"
        
        # 发送复盘邮件
        send_email("近期英超赛果宏观复盘", review_text)
        
        # ==================== 自动回写数据 ====================
        # 这里需要解析 match 并存入 csv，由于 ESPN 数据结构嵌套深，我们简化处理，
        # 实际运行中，建议你继续保持从 football-data 抓取 FINISHED 数据用于回写，
        # 或者自行添加针对 ESPN 数据的解析逻辑。这里为了演示，仅作打印。
        
    else:
        print("⚠️ 近期没有获取到已结束的比赛。")

except Exception as e:
    print(f"⚠️ 获取赛果或复盘失败: {e}")