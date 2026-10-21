import pandas as pd
import numpy as np
import lightgbm as lgb
import joblib
import os
from team_mapping import translate_team_name

def train_models():
    print("⏳ 开始训练 V19.0 多联赛高级模型...")
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file): return
        
    df = pd.read_csv(history_file)
    df['date'] = pd.to_datetime(df['date'])
    df['home_team_cn'] = df['home_team'].apply(translate_team_name)
    df['away_team_cn'] = df['away_team'].apply(translate_team_name)
    
    # 融合 xG 数据
    if os.path.exists('xg_data.csv'):
        df_xg = pd.read_csv('xg_data.csv')
        df_xg['date'] = pd.to_datetime(df_xg['date'])
        df = pd.merge(df, df_xg, on=['date', 'home_team_cn', 'away_team_cn'], how='left', suffixes=('', '_xg'))
    
    df = df.sort_values('date').reset_index(drop=True)
    league_avg_goals = (df['home_goals'].mean() + df['away_goals'].mean()) / 2
    
    features, labels_home, labels_away = [], [], []
    team_stats, last_date = {}, {}
    
    for idx, row in df.iterrows():
        home, away, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        for t in [home, away]:
            if t not in team_stats: team_stats[t] = {'xg':[], 'xga':[], 'pts':[], 'goals':[], 'conceded':[]}
        
        # 计算休息天数
        h_rest = (m_date - last_date[home]).days if home in last_date else 7
        a_rest = (m_date - last_date[away]).days if away in last_date else 7
        
        # 核心10大特征 (如果没有xG，用真实进球代替)
        h_xg_avg = np.mean(team_stats[home]['xg'][-5:]) if team_stats[home]['xg'] else league_avg_goals
        a_xg_avg = np.mean(team_stats[away]['xg'][-5:]) if team_stats[away]['xg'] else league_avg_goals
        h_xga_avg = np.mean(team_stats[home]['xga'][-5:]) if team_stats[home]['xga'] else league_avg_goals
        a_xga_avg = np.mean(team_stats[away]['xga'][-5:]) if team_stats[away]['xga'] else league_avg_goals
        
        h_pts = np.mean(team_stats[home]['pts'][-5:]) if team_stats[home]['pts'] else 1.0
        a_pts = np.mean(team_stats[away]['pts'][-5:]) if team_stats[away]['pts'] else 1.0
        
        row_feat = [
            h_xg_avg, a_xg_avg, h_xga_avg, a_xga_avg, 
            h_pts, a_pts, h_rest, a_rest, 
            h_xg_avg - a_xga_avg, a_xg_avg - h_xga_avg
        ]
        row_feat = np.clip(np.nan_to_num(row_feat, nan=0.0, posinf=5.0, neginf=0.0), -5.0, 5.0)
        
        features.append(row_feat)
        labels_home.append(row['home_goals'])
        labels_away.append(row['away_goals'])
        
        # 更新状态
        act_h_xg = row.get('home_xg', row['home_goals']) if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
        act_a_xg = row.get('away_xg', row['away_goals']) if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
        
        team_stats[home]['xg'].append(act_h_xg); team_stats[home]['xga'].append(act_a_xg)
        team_stats[home]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        team_stats[away]['xg'].append(act_a_xg); team_stats[away]['xga'].append(act_h_xg)
        team_stats[away]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        last_date[home] = m_date; last_date[away] = m_date

    X = np.array(features, dtype=np.float32)
    y_h = np.array(labels_home, dtype=np.float32)
    y_a = np.array(labels_away, dtype=np.float32)
    
    params = {'objective': 'regression', 'metric': 'rmse', 'verbose': -1}
    model_h = lgb.train(params, lgb.Dataset(X, label=y_h), num_boost_round=100)
    model_a = lgb.train(params, lgb.Dataset(X, label=y_a), num_boost_round=100)
    
    joblib.dump(model_h, 'epl_v31_home_goals_model.pkl')
    joblib.dump(model_a, 'epl_v31_away_goals_model.pkl')
    print("✅ V19.0 模型训练完成！核心特征：10个")

if __name__ == "__main__":
    train_models()
