#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime
from openai import OpenAI
import warnings
warnings.filterwarnings('ignore')

# ⚠️ 请配置你的密钥（这里保持你之前的设置，不用改）
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# 🌟 新增：中英文球队对照字典（覆盖常见英超球队及杯赛对手）
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

print("⏳ 正在抓取真实赛果，准备进行赛后复盘...")
now = datetime.now()
season = now.year if now.month >= 7 else now.year - 1
url = f"https://api.football-data.org/v4/competitions/PL/matches?season={season}"
headers = {'X-Auth-Token': FOOTBALL_DATA_API_KEY}

try:
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        finished_matches = []
        for m in data.get('matches', []):
            if m.get('status') == 'FINISHED':
                finished_matches.append({
                    'date': m['utcDate'][:10],
                    'home_team': m['homeTeam']['name'],
                    'away_team': m['awayTeam']['name'],
                    'home_goals': m['score']['fullTime']['home'],
                    'away_goals': m['score']['fullTime']['away']
                })
        df_finished = pd.DataFrame(finished_matches)
        print(f"✅ 成功获取 {len(df_finished)} 场真实完赛数据。")
    else:
        print(f"❌ API 获取失败：{resp.status_code}")
        df_finished = pd.DataFrame()
except Exception as e:
    print(f"❌ 请求出错：{e}")
    df_finished = pd.DataFrame()

if not df_finished.empty:
    # 这里为了演示，我们随机抽取一场已完赛的比赛让DeepSeek复盘
    latest_match = df_finished.iloc[-1]
    
    # 🌟 核心修复：将英文队名翻译为中文
    home = translate_team_name(latest_match['home_team'])
    away = translate_team_name(latest_match['away_team'])
    hg = latest_match['home_goals']
    ag = latest_match['away_goals']
    
    prompt = f"""你是一位资深英超数据分析师。上一轮比赛中，你的系统预测：{home} vs {away}。
    实际结果是：{home} {hg} - {ag} {away}。
    请用中文写一段150字以内的赛后感言，分析这场比赛的结果是否符合预期，并总结一条“经验教训”，以便优化未来的预测模型。"""
    
    try:
        response = llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        review_comment = response.choices[0].message.content.strip()
        print("\n" + "="*60)
        # 🌟 核心修复：打印时使用中文队名
        print(f"【赛后复盘报告】比赛：{home} {hg}-{ag} {away}")
        print("="*60)
        print(f"\n🧠 DeepSeek 复盘总结：\n{review_comment}")
        print("="*60)
    except Exception as e:
        print(f"❌ 复盘请求失败：{e}")

    # ==================== 自动回写数据 ====================
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
    print("⚠️ 暂无已结束的比赛可供复盘。")


# In[ ]:




