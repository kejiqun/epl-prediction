import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
from sklearn.model_selection import train_test_split
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
    
    league_avg_goals = (df['home_goals'].mean() + df['away_goals'].mean()) / 2
    
    # 构造特征
    features = []
    labels_home = []
    labels_away = []
    
    team_stats = {}
    for idx, row in df.iterrows():
        home, away = row['home_team_cn'], row['away_team_cn']
        for t in [home, away]:
            if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[]}
        
        # 特征：近5场平均进球/失球，胜率等 (极其简化的特征，原版应该更丰富)
        h_scored = np.mean(team_stats[home]['scored'][-5:]) if team_stats[home]['scored'] else league_avg_goals
        h_conceded = np.mean(team_stats[home]['conceded'][-5:]) if team_stats[home]['conceded'] else league_avg_goals
        a_scored = np.mean(team_stats[away]['scored'][-5:]) if team_stats[away]['scored'] else league_avg_goals
        a_conceded = np.mean(team_stats[away]['conceded'][-5:]) if team_stats[away]['conceded'] else league_avg_goals
        
        h_pts = np.mean(team_stats[home]['points'][-5:]) if team_stats[home]['points'] else 1.0
        a_pts = np.mean(team_stats[away]['points'][-5:]) if team_stats[away]['points'] else 1.0
        
        features.append([
            h_scored / league_avg_goals, h_conceded / league_avg_goals, 
            a_scored / league_avg_goals, a_conceded / league_avg_goals,
            h_pts, a_pts
        ])
        labels_home.append(row['home_goals'])
        labels_away.append(row['away_goals'])
        
        # 更新统计数据
        team_stats[home]['scored'].append(row['home_goals'])
        team_stats[home]['conceded'].append(row['away_goals'])
        team_stats[home]['points'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        team_stats[away]['scored'].append(row['away_goals'])
        team_stats[away]['conceded'].append(row['home_goals'])
        team_stats[away]['points'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))

    X = np.array(features)
    y_home = np.array(labels_home)
    y_away = np.array(labels_away)
    
    # 训练
    model_home = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3)
    model_away = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3)
    
    model_home.fit(X, y_home)
    model_away.fit(X, y_away)
    
    joblib.dump(model_home, 'epl_v31_home_goals_model.pkl')
    joblib.dump(model_away, 'epl_v31_away_goals_model.pkl')
    print("✅ 多联赛 XGBoost 模型训练完成并保存！")

if __name__ == "__main__":
    train_models()
