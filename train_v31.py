import pandas as pd
import numpy as np
import lightgbm as lgb
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
import joblib
import os
from team_mapping import translate_team_name

def calculate_elo(df):
    elo = {}
    for idx, row in df.iterrows():
        h, a = row['home_team_cn'], row['away_team_cn']
        if h not in elo: elo[h] = 1500
        if a not in elo: elo[a] = 1500
        exp_h = 1 / (1 + 10 ** ((elo[a] - (elo[h] + 100)) / 400))
        score_h = 1 if row['home_goals'] > row['away_goals'] else (0.5 if row['home_goals'] == row['away_goals'] else 0)
        elo[h] += 20 * (score_h - exp_h)
        elo[a] += 20 * ((1-score_h) - (1-exp_h))
        df.at[idx, 'home_elo'] = elo[h]
        df.at[idx, 'away_elo'] = elo[a]
    return df, elo

def train_models():
    print("⏳ 开始训练 V33.0 集成模型 (LGB + XGB)...")
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file): return
        
    df = pd.read_csv(history_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['home_team_cn'] = df['home_team'].apply(translate_team_name)
    df['away_team_cn'] = df['away_team'].apply(translate_team_name)
    
    df, final_elo = calculate_elo(df)
    joblib.dump(final_elo, 'elo_dict.pkl')
    
    if os.path.exists('xg_data.csv'):
        df_xg = pd.read_csv('xg_data.csv')
        df_xg['date'] = pd.to_datetime(df_xg['date'])
        df = pd.merge(df, df_xg, on=['date', 'home_team_cn', 'away_team_cn'], how='left', suffixes=('', '_xg'))
    
    league_avg_goals = (df['home_goals'].mean() + df['away_goals'].mean()) / 2
    features, labels_home, labels_away, labels_result = [], [], [], []
    team_stats, last_date = {}, {}
    
    for idx, row in df.iterrows():
        h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        for t in [h, a]:
            if t not in team_stats: team_stats[t] = {'xg':[], 'opp_elo':[], 'pts':[]}
            if t not in last_date: last_date[t] = None
        
        h_rest = (m_date - last_date[h]).days if last_date[h] else 7
        a_rest = (m_date - last_date[a]).days if last_date[a] else 7
        rest_diff = h_rest - a_rest

        h_xg = np.mean(team_stats[h]['xg'][-5:]) if team_stats[h]['xg'] else league_avg_goals
        a_xg = np.mean(team_stats[a]['xg'][-5:]) if team_stats[a]['xg'] else league_avg_goals
        h_sos = np.mean(team_stats[h]['opp_elo'][-5:]) if team_stats[h]['opp_elo'] else 1500
        a_sos = np.mean(team_stats[a]['opp_elo'][-5:]) if team_stats[a]['opp_elo'] else 1500
        h_pts = np.mean(team_stats[h]['pts'][-5:]) if team_stats[h]['pts'] else 1.0
        a_pts = np.mean(team_stats[a]['pts'][-5:]) if team_stats[a]['pts'] else 1.0
        
        feat = [row['home_elo'], row['away_elo'], row['home_elo'] - row['away_elo'], h_sos, a_sos, h_xg, a_xg, h_pts, a_pts, rest_diff]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000)
        features.append(feat)
        
        labels_home.append(row['home_goals'])
        labels_away.append(row['away_goals'])
        if row['home_goals'] > row['away_goals']: labels_result.append(2)
        elif row['home_goals'] == row['away_goals']: labels_result.append(1)
        else: labels_result.append(0)
        
        act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
        act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
        team_stats[h]['xg'].append(act_h_xg); team_stats[h]['opp_elo'].append(row['away_elo'])
        team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        team_stats[a]['xg'].append(act_a_xg); team_stats[a]['opp_elo'].append(row['home_elo'])
        team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        last_date[h] = m_date; last_date[a] = m_date

    X = np.array(features, dtype=np.float32)
    y_h = np.array(labels_home, dtype=np.float32)
    y_a = np.array(labels_away, dtype=np.float32)
    y_res = np.array(labels_result, dtype=np.int32)
    
    # 1. 训练 LightGBM
    params_reg = {'objective': 'regression', 'metric': 'rmse', 'verbose': -1}
    model_h_lgb = lgb.train(params_reg, lgb.Dataset(X, label=y_h), num_boost_round=100)
    model_a_lgb = lgb.train(params_reg, lgb.Dataset(X, label=y_a), num_boost_round=100)
    
    # 2. 训练 XGBoost
    model_h_xgb = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, n_jobs=1)
    model_a_xgb = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, n_jobs=1)
    model_h_xgb.fit(X, y_h)
    model_a_xgb.fit(X, y_a)
    
    # 3. 训练分类器 (胜平负)
    clf = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, verbose=-1)
    calibrated_clf = CalibratedClassifierCV(clf, method='isotonic', cv=3)
    calibrated_clf.fit(X, y_res)
    
    joblib.dump(model_h_lgb, 'epl_v31_home_goals_model_lgb.pkl')
    joblib.dump(model_a_lgb, 'epl_v31_away_goals_model_lgb.pkl')
    joblib.dump(model_h_xgb, 'epl_v31_home_goals_model_xgb.pkl')
    joblib.dump(model_a_xgb, 'epl_v31_away_goals_model_xgb.pkl')
    joblib.dump(calibrated_clf, 'epl_result_classifier.pkl')
    print("✅ V33.0 集成模型训练完成！(LGB + XGB)")

if __name__ == "__main__":
    train_models()
