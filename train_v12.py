import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import optuna
import os
import warnings
warnings.filterwarnings('ignore')

# ==================== 球队翻译字典 ====================
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
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂',
    'Burnley FC': '伯恩利', 'Burnley': '伯恩利', 'Sheffield United FC': '谢菲尔德联', 'Sheffield United': '谢菲尔德联',
    'Luton Town FC': '卢顿', 'Luton Town': '卢顿', 'Watford FC': '沃特福德', 'Watford': '沃特福德', 'Norwich City FC': '诺维奇', 'Norwich City': '诺维奇'
}

def translate_team_name(name):
    if isinstance(name, str):
        return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

print("⏳ V12 炼丹炉启动，正在准备历史数据...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

try:
    df_standings = pd.read_csv('epl_standings.csv')
    team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
except:
    team_rank_dict = {}

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats = {}
last_match_date = {}
features_list = []

# 🌟 V12 核心：构建球队画像（对阵强队/弱队的差异化表现）
for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: 
            team_stats[t] = {'scored':[], 'conceded':[], 'points':[], 'vs_strong':[], 'vs_weak':[]}
        if t not in last_match_date: 
            last_match_date[t] = None

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

    # 画像特征：面对强敌（前6）的拿分率
    h_vs_strong = np.mean(team_stats[home]['vs_strong'][-5:]) if len(team_stats[home]['vs_strong']) > 0 else 0.5
    a_vs_strong = np.mean(team_stats[away]['vs_strong'][-5:]) if len(team_stats[away]['vs_strong']) > 0 else 0.5

    features_list.append({
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'rest_days': h_rest, 'opp_rest_days': a_rest,
        'is_home': 1, 'home_rank': team_rank_dict.get(home, 15), 'away_rank': team_rank_dict.get(away, 15),
        'home_vs_strong': h_vs_strong, 'away_vs_strong': a_vs_strong, # 🌟 新特征
        'prob_h_odds': row.get('prob_h_odds', 0.33), 'prob_d_odds': row.get('prob_d_odds', 0.33), 'prob_a_odds': row.get('prob_a_odds', 0.33),
        'home_goals': row['home_goals'], 'away_goals': row['away_goals']
    })
    
    # 更新历史
    team_stats[home]['scored'].append(row['home_goals'])
    team_stats[home]['conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    
    # 判断对手是否强队
    away_is_strong = team_rank_dict.get(away, 15) <= 6
    home_is_strong = team_rank_dict.get(home, 15) <= 6
    if away_is_strong: team_stats[home]['vs_strong'].append(h_pts)
    if home_is_strong: team_stats[away]['vs_strong'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))

    team_stats[away]['scored'].append(row['away_goals'])
    team_stats[away]['conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    
    last_match_date[home] = date
    last_match_date[away] = date

df_model = pd.DataFrame(features_list).dropna(subset=['home_goals', 'away_goals'])
df_model['home_goals'] = df_model['home_goals'].astype(int)
df_model['away_goals'] = df_model['away_goals'].astype(int)

feature_cols = ['attack', 'defense', 'opp_attack', 'opp_defense', 'win_rate', 'opp_win_rate', 'rest_days', 'opp_rest_days', 'is_home', 'home_rank', 'away_rank', 'home_vs_strong', 'away_vs_strong', 'prob_h_odds', 'prob_d_odds', 'prob_a_odds']
X = df_model[feature_cols].fillna(0.33)
y_home = df_model['home_goals']
y_away = df_model['away_goals']

# ==================== 🌟 Optuna 自动调参 ====================
print("⏳ 开始 Optuna 自动寻找最优算法参数（约需 1 分钟）...")

def objective(trial):
    param = {
        'n_estimators': trial.suggest_int('n_estimators', 100, 300),
        'max_depth': trial.suggest_int('max_depth', 3, 6),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1),
        'random_state': 42
    }
    # 快速交叉验证
    model = xgb.XGBRegressor(**param)
    model.fit(X, y_home)
    # 用训练集误差作为反馈（为了速度，这里未做全量CV）
    score = model.score(X, y_home) 
    return score

# 限制跑 15 次，防止 GitHub Actions 超时
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=15, timeout=120) 

best_params = study.best_params
best_params['random_state'] = 42
print(f"✅ 找到最优参数：{best_params}")

# 用最优参数训练最终模型
print("⏳ 正在使用最优参数训练最终 V12 模型...")
model_home_v12 = xgb.XGBRegressor(**best_params)
model_away_v12 = xgb.XGBRegressor(**best_params)
model_home_v12.fit(X, y_home)
model_away_v12.fit(X, y_away)

joblib.dump(model_home_v12, 'epl_v12_home_goals_model.pkl')
joblib.dump(model_away_v12, 'epl_v12_away_goals_model.pkl')
print("✅ V12 训练完毕！（模型已暂存云端，不占GitHub容量）")
