import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import joblib
from sklearn.ensemble import RandomForestRegressor, StackingRegressor
from sklearn.neural_network import MLPRegressor
import os
import warnings
warnings.filterwarnings('ignore')

team_mapping = {
    'Arsenal FC': '阿森纳', 'Arsenal': '阿森纳', 'Aston Villa FC': '阿斯顿维拉', 'Aston Villa': '阿斯顿维拉',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Brighton & Hove Albion FC': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西', 'Crystal Palace FC': '水晶宫', 'Crystal Palace': '水晶宫',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿', 'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Ipswich Town FC': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester City FC': '莱斯特城', 'Leicester City': '莱斯特城',
    'Liverpool FC': '利物浦', 'Liverpool': '利物浦', 'Manchester City FC': '曼城', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United FC': '曼联', 'Manchester United': '曼联', 'Man United': '曼联', 'Man Utd': '曼联',
    'Newcastle United FC': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联', 'Newcastle': '纽卡斯尔联',
    'Nottingham Forest FC': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林',
    'Southampton FC': '南安普顿', 'Southampton': '南安普顿', 'Tottenham Hotspur FC': '托特纳姆热刺', 'Tottenham Hotspur': '托特纳姆热刺', 'Tottenham': '托特纳姆热刺',
    'West Ham United FC': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolverhampton Wanderers FC': '狼队', 'Wolverhampton Wanderers': '狼队', 'Wolves': '狼队',
    'Leeds United FC': '利兹联', 'Leeds United': '利兹联', 'Sunderland AFC': '桑德兰', 'Sunderland': '桑德兰',
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂'
}

def translate_team_name(name):
    if isinstance(name, str):
        return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

print("⏳ V28 炼丹炉启动，准备融合真实 xG 数据...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])

try:
    df_xg = pd.read_csv('epl_xg_data.csv')
    df_xg['date'] = pd.to_datetime(df_xg['date'])
    df_xg['home_team_cn'] = df_xg['home_team'].apply(translate_team_name)
    df_xg['away_team_cn'] = df_xg['away_team'].apply(translate_team_name)
    print("✅ 成功加载 xG 数据，将使用真实预期进球作为特征。")
    use_xg = True
except:
    print("⚠️ 无法加载 xG 数据，将降级使用传统进球数据。")
    use_xg = False

df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)
df_hist = df_hist.sort_values('date').reset_index(drop=True)

try:
    df_standings = pd.read_csv('epl_standings.csv')
    team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
except:
    team_rank_dict = {}

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats = {}
last_match_date = {}
features_list = []

for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: 
            team_stats[t] = {'scored_xg':[], 'conceded_xg':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]}
        if t not in last_match_date: 
            last_match_date[t] = None

    h_rest = min(max((date - last_match_date[home]).days if last_match_date[home] else 7, 2), 14)
    a_rest = min(max((date - last_match_date[away]).days if last_match_date[away] else 7, 2), 14)
    
    h_match_xg = row['home_goals']
    a_match_xg = row['away_goals']
    
    if use_xg:
        match_xg = df_xg[(df_xg['date'] == date) & (df_xg['home_team_cn'] == home) & (df_xg['away_team_cn'] == away)]
        if not match_xg.empty:
            h_match_xg = match_xg.iloc[0]['home_xg']
            a_match_xg = match_xg.iloc[0]['away_xg']

    h_avg_xg = np.mean(team_stats[home]['scored_xg'][-5:]) if len(team_stats[home]['scored_xg']) > 0 else league_avg_goals
    h_avg_conceded = np.mean(team_stats[home]['conceded_xg'][-5:]) if len(team_stats[home]['conceded_xg']) > 0 else league_avg_goals
    a_avg_xg = np.mean(team_stats[away]['scored_xg'][-5:]) if len(team_stats[away]['scored_xg']) > 0 else league_avg_goals
    a_avg_conceded = np.mean(team_stats[away]['conceded_xg'][-5:]) if len(team_stats[away]['conceded_xg']) > 0 else league_avg_goals

    # 基础攻击防守
    h_attack = h_avg_xg / league_avg_goals
    h_defense = h_avg_conceded / league_avg_goals
    a_attack = a_avg_xg / league_avg_goals
    a_defense = a_avg_conceded / league_avg_goals

    # 🌟 补齐：主客场特异性
    h_home_scored = np.mean(team_stats[home]['home_scored'][-3:]) if len(team_stats[home]['home_scored']) > 0 else league_avg_goals
    h_home_conceded = np.mean(team_stats[home]['home_conceded'][-3:]) if len(team_stats[home]['home_conceded']) > 0 else league_avg_goals
    a_away_scored = np.mean(team_stats[away]['away_scored'][-3:]) if len(team_stats[away]['away_scored']) > 0 else league_avg_goals
    a_away_conceded = np.mean(team_stats[away]['away_conceded'][-3:]) if len(team_stats[away]['away_conceded']) > 0 else league_avg_goals

    h_home_attack, h_home_defense = h_home_scored / league_avg_goals, h_home_conceded / league_avg_goals
    a_away_attack, a_away_defense = a_away_scored / league_avg_goals, a_away_conceded / league_avg_goals
    
    h_win_rate = np.mean(team_stats[home]['points'][-5:]) if len(team_stats[home]['points']) > 0 else 0.5
    a_win_rate = np.mean(team_stats[away]['points'][-5:]) if len(team_stats[away]['points']) > 0 else 0.5

    features_list.append({
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'home_attack_spec': h_home_attack, 'home_defense_spec': h_home_defense, 
        'away_attack_spec': a_away_attack, 'away_defense_spec': a_away_defense, # 🌟 补上这四个特征
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'win_rate_diff': h_win_rate - a_win_rate,
        'rest_days': h_rest, 'opp_rest_days': a_rest, 'is_home': 1, 
        'home_rank': team_rank_dict.get(home, 15), 'away_rank': team_rank_dict.get(away, 15),
        'prob_h_odds': row.get('prob_h_odds', 0.33), 'prob_d_odds': row.get('prob_d_odds', 0.33), 'prob_a_odds': row.get('prob_a_odds', 0.33),
        'home_goals': row['home_goals'], 'away_goals': row['away_goals']
    })
    
    team_stats[home]['scored_xg'].append(h_match_xg); team_stats[home]['conceded_xg'].append(a_match_xg)
    team_stats[home]['home_scored'].append(row['home_goals']); team_stats[home]['home_conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    
    team_stats[away]['scored_xg'].append(a_match_xg); team_stats[away]['conceded_xg'].append(h_match_xg)
    team_stats[away]['away_scored'].append(row['away_goals']); team_stats[away]['away_conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    
    last_match_date[home] = date; last_match_date[away] = date

df_model = pd.DataFrame(features_list).dropna(subset=['home_goals', 'away_goals'])

# 🌟 核心修复：将主客场特异性特征加入最终训练列表
feature_cols = [
    'attack', 'defense', 'opp_attack', 'opp_defense', 
    'home_attack_spec', 'home_defense_spec', 'away_attack_spec', 'away_defense_spec',
    'win_rate', 'opp_win_rate', 'win_rate_diff', 'rest_days', 'opp_rest_days', 
    'is_home', 'home_rank', 'away_rank', 'prob_h_odds', 'prob_d_odds', 'prob_a_odds'
]

X = df_model[feature_cols].fillna(0.33)
y_home = df_model['home_goals'].astype(int)
y_away = df_model['away_goals'].astype(int)

print("⏳ 正在构建 Stacking 融合模型...")
estimators = [
    ('xgb', xgb.XGBRegressor(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42)),
    ('lgbm', lgb.LGBMRegressor(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42, verbose=-1)),
    ('rf', RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)),
    ('mlp', MLPRegressor(hidden_layer_sizes=(50, 25), max_iter=500, random_state=42))
]
final_estimator = xgb.XGBRegressor(n_estimators=50, max_depth=3, random_state=42)

model_home_v28 = StackingRegressor(estimators=estimators, final_estimator=final_estimator, cv=3)
model_away_v28 = StackingRegressor(estimators=estimators, final_estimator=final_estimator, cv=3)

model_home_v28.fit(X, y_home)
model_away_v28.fit(X, y_away)

joblib.dump(model_home_v28, 'epl_v28_home_goals_model.pkl')
joblib.dump(model_away_v28, 'epl_v28_away_goals_model.pkl')
print("✅ V28 xG 融合模型训练完毕并保存！")
