import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
import warnings
warnings.filterwarnings('ignore')

print("⏳ 正在加载最新历史数据，准备训练 V11 模型...")

# 1. 加载数据
df_hist = pd.read_csv('epl_matches_10y.csv')
df_standings = pd.read_csv('epl_standings.csv')

# 2. 特征工程（与之前 Jupyter 里的逻辑完全一致）
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)

team_mapping = {
    'Arsenal FC': '阿森纳', 'Arsenal': '阿森纳', 'Aston Villa FC': '阿斯顿维拉', 'Aston Villa': '阿斯顿维拉',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Brighton & Hove Albion FC': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西', 'Crystal Palace FC': '水晶宫', 'Crystal Palace': '水晶宫',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿', 'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Ipswich Town FC': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester City FC': '莱斯特城', 'Leicester City': '莱斯特城',
    'Liverpool FC': '利物浦', 'Liverpool': '利物浦', 'Manchester City FC': '曼城', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United FC': '曼联', 'Manchester United': '曼联', 'Man United': '曼联',
    'Newcastle United FC': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联', 'Nottingham Forest FC': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林',
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

df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
team_pts_dict = dict(zip(df_standings['球队'], df_standings['积分']))
team_avg_pts_dict = {k: v/30 for k, v in team_pts_dict.items()}

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats, last_match_date = {}, {}
features_list = []

for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[]}
        if t not in last_match_date: last_match_date[t] = None
    h_rest = min(max((date - last_match_date[home]).days if last_match_date[home] else 7, 2), 14)
    a_rest = min(max((date - last_match_date[away]).days if last_match_date[away] else 7, 2), 14)
    h_avg_scored = np.mean(team_stats[home]['scored'][-5:]) if len(team_stats[home]['scored']) > 0 else league_avg_goals
    h_avg_conceded = np.mean(team_stats[home]['conceded'][-5:]) if len(team_stats[home]['conceded']) > 0 else league_avg_goals
    a_avg_scored = np.mean(team_stats[away]['scored'][-5:]) if len(team_stats[away]['scored']) > 0 else league_avg_goals
    a_avg_conceded = np.mean(team_stats[away]['conceded'][-5:]) if len(team_stats[away]['conceded']) > 0 else league_avg_goals
    h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
    a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
    h_win_rate = np.mean(team_stats[home]['points'][-5:]) if len(team_stats[home]['points']) > 0 else 0.5
    a_win_rate = np.mean(team_stats[away]['points'][-5:]) if len(team_stats[away]['points']) > 0 else 0.5
    features_list.append({
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'rest_days': h_rest, 'opp_rest_days': a_rest,
        'is_home': 1, 'home_rank': team_rank_dict.get(home, 15), 'away_rank': team_rank_dict.get(away, 15),
        'home_avg_points': team_avg_pts_dict.get(home, 1.0), 'away_avg_points': team_avg_pts_dict.get(away, 1.0),
        'prob_h_odds': row.get('prob_h_odds', 0.33), 'prob_d_odds': row.get('prob_d_odds', 0.33), 'prob_a_odds': row.get('prob_a_odds', 0.33),
        'home_goals': row['home_goals'], 'away_goals': row['away_goals']
    })
    team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    last_match_date[home] = date; last_match_date[away] = date

df_model = pd.DataFrame(features_list)
feature_cols = ['attack', 'defense', 'opp_attack', 'opp_defense', 'win_rate', 'opp_win_rate', 'rest_days', 'opp_rest_days', 'is_home', 'home_rank', 'away_rank', 'home_avg_points', 'away_avg_points', 'prob_h_odds', 'prob_d_odds', 'prob_a_odds']
X = df_model[feature_cols].fillna(0.33)
y_home = df_model['home_goals']
y_away = df_model['away_goals']
y_result = np.where(y_home > y_away, 2, np.where(y_home == y_away, 1, 0))

# 3. 训练 V11 模型（更精简，避免文件过大）
print("⏳ 正在训练 V11 模型...")
model_home_v11 = xgb.XGBRegressor(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42)
model_away_v11 = xgb.XGBRegressor(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42)
model_home_v11.fit(X, y_home)
model_away_v11.fit(X, y_away)
model_result_v11 = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
model_result_v11.fit(X, y_result)

# 4. 保存模型（文件会非常小，轻松上传）
joblib.dump(model_home_v11, 'epl_v11_home_goals_model.pkl')
joblib.dump(model_away_v11, 'epl_v11_away_goals_model.pkl')
joblib.dump(model_result_v11, 'epl_v11_result_model.pkl')
print("✅ V11 模型训练完毕并保存！文件大小已优化，可以直接上传。")