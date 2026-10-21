import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime, timedelta
import warnings
from openai import OpenAI
import re

from config import LEAGUES
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

print("⏳ 正在启动 V27.0 错题深度复盘引擎...")
if not os.path.exists('predictions_log.csv'): exit()

df_log = pd.read_csv('predictions_log.csv')
df_log['date'] = pd.to_datetime(df_log['date'])
today = datetime.now()
past_3_days = today - timedelta(days=3)

for c in ['actual_score', 'actual_result', 'is_win']:
    if c not in df_log.columns: df_log[c] = ""

pending_review = df_log[(df_log['date'] >= past_3_days) & (df_log['actual_score'].isna() | (df_log['actual_score'] == ""))].copy()

if pending_review.empty:
    print("✅ 最近 3 天没有需要复盘的新比赛。")
    exit()

actual_results = {}
for league_name, config in LEAGUES.items():
    for i in range(1, 4):
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

wrong_matches = []

for idx, row in pending_review.iterrows():
    m_date = row['date'].strftime('%Y-%m-%d')
    res = actual_results.get((m_date, row['home_team'], row['away_team']))
    
    if res:
        hg, ag = res
        actual_res = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
        is_win = "✅ 命中" if row['predicted_result'] == actual_res else "❌ 失手"
        
        df_log.at[idx, 'actual_score'] = f"{hg}-{ag}"
        df_log.at[idx, 'actual_result'] = actual_res
        df_log.at[idx, 'is_win'] = is_win
        
        # 只有“预测错误”且“非观望”的才会被提进错题本
        if row['predicted_result'] != actual_res and row['predicted_result'] != "观望":
            wrong_matches.append({
                '比赛': f"{row['home_team']} vs {row['away_team']}",
                '比分': f"{hg}-{ag}", '预测': row['predicted_result'], '实际': actual_res,
                '模型概率': f"主{row.get('pred_prob_h', 0)*100:.0f}% 平{row.get('pred_prob_d',0)*100:.0f}% 客{row.get('pred_prob_a',0)*100:.0f}%",
                '伤停': f"主[{row.get('home_injuries', '无')}] 客[{row.get('away_injuries', '无')}]"
            })

if wrong_matches:
    print(f"🚨 发现 {len(wrong_matches)} 场错题，呼叫 AI 提炼教训...")
    prompt = f"""你是一位顶级的足球量化风控总监。以下是近期系统预测失败（亏损）的比赛数据：
    {wrong_matches}
    
    当前我们的模型已经包含了：Elo实力、赛程强度、xG、伤停影响。
    请分析这些冷门/亏损的原因（比如：强队轮换？赔率过度诱导？伤停影响被低估？）。请输出 3 条极其深刻的【错题经验】，直接以 '-' 开头，方便我写入知识库。"""
    
    try:
        res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        review_report = res.choices[0].message.content.strip()
        
        with open('knowledge.txt', 'a', encoding='utf-8') as f:
            f.write(f"\n\n--- {datetime.now().strftime('%Y-%m-%d')} 错题深度归因 ---\n")
            f.write(review_report)
        print("✅ 错题经验已成功写入 knowledge.txt")
    except Exception as e:
        print(f"AI 剖析失败: {e}")
else:
    print("🎉 近期比赛预测全中（或者全都是观望），没有实盘错题需要分析。")

df_log.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')
print("✅ 复盘流程结束。")
