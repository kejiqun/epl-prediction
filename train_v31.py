import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
from team_mapping import translate_team_name

def train_models():
    print("⏳ 开始训练 V31 多联赛通用模型...")
    
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file):
        print("❌ 找不到历史数据文件，训练中止。")
        return
        
    df = pd.read_csv(history_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['home_team_cn'] = df['home_team'].apply(translate_team_name)
    df['away_team_cn'] = df['away_team'].apply(translate_team_name)
    
    # 读取积分榜数据（用于 rank 特征）
    team_rank_dict = {}
    if os.path.exists('epl_standings.csv'):
        df_standings = pd.read_csv('epl_standings.csv')
        team_rank_dict = dict(zip(df_standings['球队'], df_standings['排名']))
    
    league_avg_goals = (df['home_goals'].mean() + df['away_goals'].mean()) / 2
    
    features = []
    labels_home = []
    labels_away = []
    
    team_stats = {}
    for idx, row in df.iterrows():
        home, away = row['home_team_cn'], row['away_team_cn']
        for t in [home, away]:
            if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]}
        
        h_avg_scored = np.mean(team_stats[home]['scored'][-5:]) if team_stats[home]['scored'] else league_avg_goals
        h_avg_conceded = np.mean(team_stats[home]['conceded'][-5:]) if team_stats[home]['conceded'] else league_avg_goals
        a_avg_scored = np.mean(team_stats[away]['scored'][-5:]) if team_stats[away]['scored'] else league_avg_goals
        a_avg_conceded = np.mean(team_stats[away]['conceded'][-5:]) if team_stats[away]['conceded'] else league_avg_goals
        
        h_home_scored = np.mean(team_stats[home]['home_scored'][-3:]) if team_stats[home]['home_scored'] else league_avg_goals
        h_home_conceded = np.mean(team_stats[home]['home_conceded'][-3:]) if team_stats[home]['home_conceded'] else league_avg_goals
        a_away_scored = np.mean(team_stats[away]['away_scored'][-3:]) if team_stats[away]['away_scored'] else league_avg_goals
        a_away_conceded = np.mean(team_stats[away]['away_conceded'][-3:]) if team_stats[away]['away_conceded'] else league_avg_goals

        h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
        a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals
        h_home_attack, h_home_defense = h_home_scored / league_avg_goals, h_home_conceded / league_avg_goals
        a_away_attack, a_away_defense = a_away_scored / league_avg_goals, a_away_conceded / league_avg_goals
        
        h_win_rate = np.mean(team_stats[home]['points'][-5:]) if team_stats[home]['points'] else 0.5
        a_win_rate = np.mean(team_stats[away]['points'][-5:]) if team_stats[away]['points'] else 0.5
        h_form_trend = (np.mean(team_stats[home]['points'][-3:]) - np.mean(team_stats[home]['points'][-5:])) if len(team_stats[home]['points']) >= 5 else 0.0
        a_form_trend = (np.mean(team_stats[away]['points'][-3:]) - np.mean(team_stats[away]['points'][-5:])) if len(team_stats[away]['points']) >= 5 else 0.0

        # 确保这里构建的字典顺序和 final_prediction.py 中完全一致！
        feature_dict = {
            'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
            'home_attack_spec': h_home_attack, 'home_defense_spec': h_home_defense,
            'away_attack_spec': a_away_attack, 'away_defense_spec': a_away_defense,
            'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'win_rate_diff': h_win_rate - a_win_rate,
            'rest_days': 7, 'opp_rest_days': 7, 'is_home': 1,
            'home_rank': team_rank_dict.get(home, 15), 'away_rank': team_rank_dict.get(away, 15),
            'h_form_trend': h_form_trend, 'a_form_trend': a_form_trend,
            'prob_h_odds': 0.4, 'prob_d_odds': 0.3, 'prob_a_odds': 0.3 # 历史训练没赔率，给个默认值
        }
        
        row_features = list(feature_dict.values())
        row_features = np.nan_to_num(row_features, nan=0.0, posinf=10.0, neginf=-10.0)
        row_features = np.clip(row_features, -10.0, 10.0)
        
        features.append(row_features)
        labels_home.append(row['home_goals'])
        labels_away.append(row['away_goals'])
        
        # 更新球队状态
        team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
        team_stats[home]['home_scored'].append(row['home_goals']); team_stats[home]['home_conceded'].append(row['away_goals'])
        team_stats[home]['points'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
        team_stats[away]['away_scored'].append(row['away_goals']); team_stats[away]['away_conceded'].append(row['home_goals'])
        team_stats[away]['points'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))

    X = np.array(features, dtype=np.float32)
    y_home = np.array(labels_home, dtype=np.float32)
    y_away = np.array(labels_away, dtype=np.float32)
    
    model_home = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, n_jobs=1)
    model_away = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, n_jobs=1)
    
    model_home.fit(X, y_home)
    model_away.fit(X, y_away)
    
    joblib.dump(model_home, 'epl_v31_home_goals_model.pkl')
    joblib.dump(model_away, 'epl_v31_away_goals_model.pkl')
    print("✅ 多联赛 XGBoost 模型训练完成并保存！特征数量：21")

if __name__ == "__main__":
    train_models()
