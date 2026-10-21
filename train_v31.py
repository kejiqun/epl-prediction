import pandas as pd
import numpy as np
import lightgbm as lgb
import joblib
import os
from team_mapping import translate_team_name

def train_models():
    print("⏳ 开始训练 V23.0 高阶特征模型 (LightGBM)...")
    
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file): return
        
    df = pd.read_csv(history_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['home_team_cn'] = df['home_team'].apply(translate_team_name)
    df['away_team_cn'] = df['away_team'].apply(translate_team_name)
    
    # 融合 xG 数据
    if os.path.exists('xg_data.csv'):
        df_xg = pd.read_csv('xg_data.csv')
        df_xg['date'] = pd.to_datetime(df_xg['date'])
        df = pd.merge(df, df_xg, on=['date', 'home_team_cn', 'away_team_cn'], how='left', suffixes=('', '_xg'))
    
    league_avg_goals = (df['home_goals'].mean() + df['away_goals'].mean()) / 2
    
    features, labels_home, labels_away = [], [], []
    team_stats = {}
    
    for idx, row in df.iterrows():
        home, away = row['home_team_cn'], row['away_team_cn']
        for t in [home, away]:
            if t not in team_stats: 
                team_stats[t] = {
                    'xg':[], 'xga':[], 'pts':[], 
                    'home_xg':[], 'home_xga':[], 'home_pts':[],
                    'away_xg':[], 'away_xga':[], 'away_pts':[]
                }
        
        # 计算主队特征
        h_all_xg = np.mean(team_stats[home]['xg'][-5:]) if team_stats[home]['xg'] else league_avg_goals
        h_home_xg = np.mean(team_stats[home]['home_xg'][-5:]) if team_stats[home]['home_xg'] else league_avg_goals
        h_home_xga = np.mean(team_stats[home]['home_xga'][-5:]) if team_stats[home]['home_xga'] else league_avg_goals
        h_pts = np.mean(team_stats[home]['pts'][-5:]) if team_stats[home]['pts'] else 1.0
        
        # 计算客队特征
        a_all_xg = np.mean(team_stats[away]['xg'][-5:]) if team_stats[away]['xg'] else league_avg_goals
        a_away_xg = np.mean(team_stats[away]['away_xg'][-5:]) if team_stats[away]['away_xg'] else league_avg_goals
        a_away_xga = np.mean(team_stats[away]['away_xga'][-5:]) if team_stats[away]['away_xga'] else league_avg_goals
        a_pts = np.mean(team_stats[away]['pts'][-5:]) if team_stats[away]['pts'] else 1.0
        
        # 状态趋势 (近3场均分 - 近5场均分)
        h_trend = (np.mean(team_stats[home]['pts'][-3:]) - np.mean(team_stats[home]['pts'][-5:])) if len(team_stats[home]['pts']) >= 5 else 0
        a_trend = (np.mean(team_stats[away]['pts'][-3:]) - np.mean(team_stats[away]['pts'][-5:])) if len(team_stats[away]['pts']) >= 5 else 0
        
        # 构建 10 大核心特征
        feat = [
            h_all_xg, a_all_xg, h_home_xg, h_home_xga, a_away_xg, a_away_xga,
            h_pts, a_pts, h_trend, a_trend
        ]
        feat = np.clip(np.nan_to_num(feat, nan=0.0, posinf=5.0, neginf=0.0), -5.0, 5.0)
        
        features.append(feat)
        labels_home.append(row['home_goals'])
        labels_away.append(row['away_goals'])
        
        # 获取真实 xG (若无则用实际进球代替)
        act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
        act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
        
        # 更新主队数据
        team_stats[home]['xg'].append(act_h_xg); team_stats[home]['xga'].append(act_a_xg)
        team_stats[home]['home_xg'].append(act_h_xg); team_stats[home]['home_xga'].append(act_a_xg)
        h_win = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
        team_stats[home]['pts'].append(h_win); team_stats[home]['home_pts'].append(h_win)
        
        # 更新客队数据
        team_stats[away]['xg'].append(act_a_xg); team_stats[away]['xga'].append(act_h_xg)
        team_stats[away]['away_xg'].append(act_a_xg); team_stats[away]['away_xga'].append(act_h_xg)
        a_win = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
        team_stats[away]['pts'].append(a_win); team_stats[away]['away_pts'].append(a_win)

    X = np.array(features, dtype=np.float32)
    y_h = np.array(labels_home, dtype=np.float32)
    y_a = np.array(labels_away, dtype=np.float32)
    
    params = {'objective': 'regression', 'metric': 'rmse', 'verbose': -1}
    model_h = lgb.train(params, lgb.Dataset(X, label=y_h), num_boost_round=100)
    model_a = lgb.train(params, lgb.Dataset(X, label=y_a), num_boost_round=100)
    
    joblib.dump(model_h, 'epl_v31_home_goals_model.pkl')
    joblib.dump(model_a, 'epl_v31_away_goals_model.pkl')
    print("✅ V23.0 高阶特征模型训练完成！特征数量：10")

if __name__ == "__main__":
    train_models()
