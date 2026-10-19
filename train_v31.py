import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import joblib
from sklearn.ensemble import RandomForestRegressor, StackingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split
from scipy.stats import poisson
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

print("⏳ V31 炼丹炉启动：删除伪特征，恢复主客场特异性，加入状态趋势...")
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

for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats:
            team_stats[t] = {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]}
        if t not in last_match_date:
            last_match_date[t] = None

    h_rest = min(max((date - last_match_date[home]).days if last_match_date[home] else 7, 2), 14)
    a_rest = min(max((date - last_match_date[away]).days if last_match_date[away] else 7, 2), 14)

    h_avg_scored = np.mean(team_stats[home]['scored'][-5:]) if team_stats[home]['scored'] else league_avg_goals
    h_avg_conceded = np.mean(team_stats[home]['conceded'][-5:]) if team_stats[home]['conceded'] else league_avg_goals
    a_avg_scored = np.mean(team_stats[away]['scored'][-5:]) if team_stats[away]['scored'] else league_avg_goals
    a_avg_conceded = np.mean(team_stats[away]['conceded'][-5:]) if team_stats[away]['conceded'] else league_avg_goals

    h_attack = h_avg_scored / league_avg_goals
    h_defense = h_avg_conceded / league_avg_goals
    a_attack = a_avg_scored / league_avg_goals
    a_defense = a_avg_conceded / league_avg_goals

    h_home_scored = np.mean(team_stats[home]['home_scored'][-3:]) if team_stats[home]['home_scored'] else league_avg_goals
    h_home_conceded = np.mean(team_stats[home]['home_conceded'][-3:]) if team_stats[home]['home_conceded'] else league_avg_goals
    a_away_scored = np.mean(team_stats[away]['away_scored'][-3:]) if team_stats[away]['away_scored'] else league_avg_goals
    a_away_conceded = np.mean(team_stats[away]['away_conceded'][-3:]) if team_stats[away]['away_conceded'] else league_avg_goals

    h_home_attack = h_home_scored / league_avg_goals
    h_home_defense = h_home_conceded / league_avg_goals
    a_away_attack = a_away_scored / league_avg_goals
    a_away_defense = a_away_conceded / league_avg_goals

    h_pts_series = team_stats[home]['points']
    a_pts_series = team_stats[away]['points']
    h_win_rate = np.mean(h_pts_series[-5:]) if h_pts_series else 0.5
    a_win_rate = np.mean(a_pts_series[-5:]) if a_pts_series else 0.5
    h_form_trend = (np.mean(h_pts_series[-3:]) - np.mean(h_pts_series[-5:])) if len(h_pts_series) >= 5 else 0.0
    a_form_trend = (np.mean(a_pts_series[-3:]) - np.mean(a_pts_series[-5:])) if len(a_pts_series) >= 5 else 0.0

    features_list.append({
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'home_attack_spec': h_home_attack, 'home_defense_spec': h_home_defense,
        'away_attack_spec': a_away_attack, 'away_defense_spec': a_away_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'win_rate_diff': h_win_rate - a_win_rate,
        'rest_days': h_rest, 'opp_rest_days': a_rest, 'is_home': 1,
        'home_rank': team_rank_dict.get(home, 15), 'away_rank': team_rank_dict.get(away, 15),
        'h_form_trend': h_form_trend, 'a_form_trend': a_form_trend,
        'prob_h_odds': row.get('prob_h_odds', 0.33), 'prob_d_odds': row.get('prob_d_odds', 0.33), 'prob_a_odds': row.get('prob_a_odds', 0.33),
        'home_goals': row['home_goals'], 'away_goals': row['away_goals']
    })

    team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
    team_stats[home]['home_scored'].append(row['home_goals']); team_stats[home]['home_conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)

    team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
    team_stats[away]['away_scored'].append(row['away_goals']); team_stats[away]['away_conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)

    last_match_date[home] = date; last_match_date[away] = date

df_model = pd.DataFrame(features_list).dropna(subset=['home_goals', 'away_goals'])

feature_cols = [
    'attack', 'defense', 'opp_attack', 'opp_defense',
    'home_attack_spec', 'home_defense_spec', 'away_attack_spec', 'away_defense_spec',
    'win_rate', 'opp_win_rate', 'win_rate_diff',
    'rest_days', 'opp_rest_days', 'is_home',
    'home_rank', 'away_rank',
    'h_form_trend', 'a_form_trend',
    'prob_h_odds', 'prob_d_odds', 'prob_a_odds'
]

X = df_model[feature_cols].fillna(0.33)
y_home = df_model['home_goals'].astype(int)
y_away = df_model['away_goals'].astype(int)

print(f"⏳ 样本量 {len(X)}，特征数 {len(feature_cols)}，构建 Stacking 融合模型...")
estimators = [
    ('xgb', xgb.XGBRegressor(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42)),
    ('lgbm', lgb.LGBMRegressor(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42, verbose=-1)),
    ('rf', RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)),
    ('mlp', MLPRegressor(hidden_layer_sizes=(50, 25), max_iter=500, random_state=42))
]
final_estimator = xgb.XGBRegressor(n_estimators=50, max_depth=3, random_state=42)

X_train, X_calib, y_home_train, y_home_calib, y_away_train, y_away_calib = train_test_split(
    X, y_home, y_away, test_size=0.2, random_state=42, shuffle=False
)

model_home_v31 = StackingRegressor(estimators=estimators, final_estimator=final_estimator, cv=3)
model_away_v31 = StackingRegressor(estimators=estimators, final_estimator=final_estimator, cv=3)

print("⏳ 训练基础模型...")
model_home_v31.fit(X_train, y_home_train)
model_away_v31.fit(X_train, y_away_train)

print("⏳ 拟合 Isotonic 校准器...")
calib_home_xg = model_home_v31.predict(X_calib)
calib_away_xg = model_away_v31.predict(X_calib)
raw_prob_h, raw_prob_d, raw_prob_a, true_res = [], [], [], []

for i in range(len(X_calib)):
    hg_exp, ag_exp = max(0.1, calib_home_xg[i]), max(0.1, calib_away_xg[i])
    prob_matrix = np.zeros((6, 6))
    for hg in range(6):
        for ag in range(6):
            prob_matrix[hg][ag] = poisson.pmf(hg, hg_exp) * poisson.pmf(ag, ag_exp)
    p_h = np.sum(np.tril(prob_matrix, -1)); p_d = np.sum(np.diag(prob_matrix)); p_a = np.sum(np.triu(prob_matrix, 1))
    total = p_h + p_d + p_a
    raw_prob_h.append(p_h / total); raw_prob_d.append(p_d / total); raw_prob_a.append(p_a / total)
    hg_real, ag_real = y_home_calib.iloc[i], y_away_calib.iloc[i]
    true_res.append(2 if hg_real > ag_real else (1 if hg_real == ag_real else 0))

calibrator_h = IsotonicRegression(out_of_bounds='clip').fit(raw_prob_h, [1 if r == 2 else 0 for r in true_res])
calibrator_d = IsotonicRegression(out_of_bounds='clip').fit(raw_prob_d, [1 if r == 1 else 0 for r in true_res])
calibrator_a = IsotonicRegression(out_of_bounds='clip').fit(raw_prob_a, [1 if r == 0 else 0 for r in true_res])

joblib.dump(calibrator_h, 'calibrator_h_v31.pkl')
joblib.dump(calibrator_d, 'calibrator_d_v31.pkl')
joblib.dump(calibrator_a, 'calibrator_a_v31.pkl')

print("⏳ 使用全量数据训练最终模型...")
model_home_v31.fit(X, y_home)
model_away_v31.fit(X, y_away)
joblib.dump(model_home_v31, 'epl_v31_home_goals_model.pkl')
joblib.dump(model_away_v31, 'epl_v31_away_goals_model.pkl')
print("✅ V31 模型与校准器训练完毕！")
