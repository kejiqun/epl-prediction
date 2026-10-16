#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime
from openai import OpenAI
import warnings
warnings.filterwarnings('ignore')

# ⚠️ 请配置你的密钥
import os
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

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
    # 在实际操作中，你需要将系统预测的结果与这里抓到的真实结果进行比对
    latest_match = df_finished.iloc[-1]
    home = latest_match['home_team']
    away = latest_match['away_team']
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
        print(f"【赛后复盘报告】比赛：{home} {hg}-{ag} {away}")
        print("="*60)
        print(f"\n🧠 DeepSeek 复盘总结：\n{review_comment}")
        print("="*60)
    except Exception as e:
        print(f"❌ 复盘请求失败：{e}")
else:
    print("⚠️ 暂无已结束的比赛可供复盘。")


# In[ ]:




