import pandas as pd
import numpy as np
import joblib
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import poisson
import warnings
import lightgbm as lgb
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

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

def generate_score_matrix(home_xg, away_xg, max_goals=7, rho=-0.15):
    def dixon_coles_tau(h, a):
        if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
        elif h == 0 and a == 1: return 1 + home_xg * rho
        elif h == 1 and a == 0: return 1 + away_xg * rho
        elif h == 1 and a == 1: return 1 - rho
        return 1.0
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[i][j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg) * dixon_coles_tau(i, j)
    matrix = matrix / np.sum(matrix)
    scores = [(f"{i}-{j}", matrix[i][j]) for i in range(max_goals + 1) for j in range(max_goals + 1)]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores, matrix

def run_backtest():
    print("⏳ 启动时光机回测系统 (V45.0 盲测版)...")
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file): return
        
    df = pd.read_csv(history_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['home_team_cn'] = df['home_team'].apply(translate_team_name)
    df['away_team_cn'] = df['away_team'].apply(translate_team_name)
    
    df = df.dropna(subset=['home_goals', 'away_goals'])
    
    if os.path.exists('xg_data.csv'):
        df_xg = pd.read_csv('xg_data.csv')
        df_xg['date'] = pd.to_datetime(df_xg['date'])
        df = pd.merge(df, df_xg, on=['date', 'home_team_cn', 'away_team_cn'], how='left', suffixes=('', '_xg'))
    
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()
    
    print(f"📊 数据切分：训练集 {len(train_df)} 场，测试集 {len(test_df)} 场")
    
    train_df, final_elo = calculate_elo(train_df)
    league_avg_goals = (train_df['home_goals'].mean() + train_df['away_goals'].mean()) / 2
    
    features, labels_home, labels_away, labels_result = [], [], [], []
    team_stats, last_date = {}, {}
    
    for idx, row in train_df.iterrows():
        h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        for t in [h, a]:
            if t not in team_stats: 
                team_stats[t] = {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]}
            if t not in last_date: last_date[t] = None
        
        h_rest = (m_date - last_date[h]).days if last_date[h] else 7
        a_rest = (m_date - last_date[a]).days if last_date[a] else 7
        rest_diff = h_rest - a_rest
        
        h_recent_matches = sum(1 for d in team_stats[h]['dates'] if (m_date - d).days <= 14)
        a_recent_matches = sum(1 for d in team_stats[a]['dates'] if (m_date - d).days <= 14)

        h_xg = np.mean(team_stats[h]['xg'][-5:]) if team_stats[h]['xg'] else league_avg_goals
        a_xg = np.mean(team_stats[a]['xg'][-5:]) if team_stats[a]['xg'] else league_avg_goals
        h_xga = np.mean(team_stats[h]['xga'][-5:]) if team_stats[h]['xga'] else league_avg_goals
        a_xga = np.mean(team_stats[a]['xga'][-5:]) if team_stats[a]['xga'] else league_avg_goals
        
        h_home_xg = np.mean(team_stats[h]['home_xg'][-3:]) if team_stats[h]['home_xg'] else h_xg
        h_home_xga = np.mean(team_stats[h]['home_xga'][-3:]) if team_stats[h]['home_xga'] else h_xga
        a_away_xg = np.mean(team_stats[a]['away_xg'][-3:]) if team_stats[a]['away_xg'] else a_xg
        a_away_xga = np.mean(team_stats[a]['away_xga'][-3:]) if team_stats[a]['away_xga'] else a_xga
        
        h_sos = np.mean(team_stats[h]['opp_elo'][-5:]) if team_stats[h]['opp_elo'] else 1500
        a_sos = np.mean(team_stats[a]['opp_elo'][-5:]) if team_stats[a]['opp_elo'] else 1500
        h_pts = np.mean(team_stats[h]['pts'][-5:]) if team_stats[h]['pts'] else 1.0
        a_pts = np.mean(team_stats[a]['pts'][-5:]) if team_stats[a]['pts'] else 1.0
        
        feat = [
            row['home_elo'], row['away_elo'], row['home_elo'] - row['away_elo'], 
            h_sos, a_sos, h_xg, a_xg, h_xga, a_xga, 
            h_home_xg, h_home_xga, a_away_xg, a_away_xga, 
            rest_diff, h_recent_matches, a_recent_matches
        ]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000)
        features.append(feat)
        
        h_goals = row['home_goals']
        a_goals = row['away_goals']
        labels_home.append(float(h_goals))
        labels_away.append(float(a_goals))
        
        if h_goals > a_goals: labels_result.append(2)
        elif h_goals == a_goals: labels_result.append(1)
        else: labels_result.append(0)
        
        act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else h_goals
        act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else a_goals
        
        team_stats[h]['xg'].append(act_h_xg); team_stats[h]['xga'].append(act_a_xg)
        team_stats[a]['xg'].append(act_a_xg); team_stats[a]['xga'].append(act_h_xg)
        team_stats[h]['home_xg'].append(act_h_xg); team_stats[h]['home_xga'].append(act_a_xg)
        team_stats[a]['away_xg'].append(act_a_xg); team_stats[a]['away_xga'].append(act_h_xg)
        
        team_stats[h]['opp_elo'].append(row['away_elo']); team_stats[a]['opp_elo'].append(row['home_elo'])
        team_stats[h]['pts'].append(3 if h_goals > a_goals else (1 if h_goals == a_goals else 0))
        team_stats[a]['pts'].append(3 if a_goals > h_goals else (1 if h_goals == a_goals else 0))
        team_stats[h]['dates'].append(m_date); team_stats[a]['dates'].append(m_date)
        last_date[h] = m_date; last_date[a] = m_date

    X_train = np.array(features, dtype=np.float32)
    y_h_train = np.nan_to_num(np.array(labels_home, dtype=np.float32), nan=0.0, posinf=10.0, neginf=0.0)
    y_a_train = np.nan_to_num(np.array(labels_away, dtype=np.float32), nan=0.0, posinf=10.0, neginf=0.0)
    y_res_train = np.array(labels_result, dtype=np.int32)
    
    params_reg = {'objective': 'regression', 'metric': 'rmse', 'verbose': -1}
    model_h_lgb = lgb.train(params_reg, lgb.Dataset(X_train, label=y_h_train), num_boost_round=100)
    model_a_lgb = lgb.train(params_reg, lgb.Dataset(X_train, label=y_a_train), num_boost_round=100)
    
    model_h_xgb = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, n_jobs=1, tree_method='exact')
    model_a_xgb = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, n_jobs=1, tree_method='exact')
    model_h_xgb.fit(X_train, y_h_train)
    model_a_xgb.fit(X_train, y_a_train)
    
    clf = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42, verbose=-1)
    calibrated_clf = CalibratedClassifierCV(clf, method='isotonic', cv=3)
    calibrated_clf.fit(X_train, y_res_train)

    print("⏳ 正在模拟未来实战预测...")
    bankroll = 10000.0
    bet_amount = 100.0 
    records = []
    
    total_predicted = 0
    top1_hits = 0
    top3_hits = 0

    for idx, row in test_df.iterrows():
        h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        
        for t in [h, a]:
            if t not in team_stats: 
                team_stats[t] = {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]}
            if t not in last_date: last_date[t] = None
            
        h_rest = (m_date - last_date[h]).days if last_date[h] else 7
        a_rest = (m_date - last_date[a]).days if last_date[a] else 7
        rest_diff = h_rest - a_rest
        
        h_recent_matches = sum(1 for d in team_stats[h]['dates'] if (m_date - d).days <= 14)
        a_recent_matches = sum(1 for d in team_stats[a]['dates'] if (m_date - d).days <= 14)
        
        h_xg = np.mean(team_stats[h]['xg'][-5:]) if team_stats[h]['xg'] else league_avg_goals
        a_xg = np.mean(team_stats[a]['xg'][-5:]) if team_stats[a]['xg'] else league_avg_goals
        h_xga = np.mean(team_stats[h]['xga'][-5:]) if team_stats[h]['xga'] else league_avg_goals
        a_xga = np.mean(team_stats[a]['xga'][-5:]) if team_stats[a]['xga'] else league_avg_goals
        
        h_home_xg = np.mean(team_stats[h]['home_xg'][-3:]) if team_stats[h]['home_xg'] else h_xg
        h_home_xga = np.mean(team_stats[h]['home_xga'][-3:]) if team_stats[h]['home_xga'] else h_xga
        a_away_xg = np.mean(team_stats[a]['away_xg'][-3:]) if team_stats[a]['away_xg'] else a_xg
        a_away_xga = np.mean(team_stats[a]['away_xga'][-3:]) if team_stats[a]['away_xga'] else a_xga
        
        h_sos = np.mean(team_stats[h]['opp_elo'][-5:]) if team_stats[h]['opp_elo'] else 1500
        a_sos = np.mean(team_stats[a]['opp_elo'][-5:]) if team_stats[a]['opp_elo'] else 1500
        h_pts = np.mean(team_stats[h]['pts'][-5:]) if team_stats[h]['pts'] else 1.0
        a_pts = np.mean(team_stats[a]['pts'][-5:]) if team_stats[a]['pts'] else 1.0
        
        h_elo = final_elo.get(h, 1500)
        a_elo = final_elo.get(a, 1500)
        
        feat = [
            h_elo, a_elo, h_elo - a_elo, 
            h_sos, a_sos, h_xg, a_xg, h_xga, a_xga, 
            h_home_xg, h_home_xga, a_away_xg, a_away_xga, 
            rest_diff, h_recent_matches, a_recent_matches
        ]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
        
        pred_h_xg = max(0.1, (model_h_lgb.predict(feat)[0] + model_h_xgb.predict(feat)[0]) / 2.0)
        pred_a_xg = max(0.1, (model_a_lgb.predict(feat)[0] + model_a_xgb.predict(feat)[0]) / 2.0)
        
        scores_list, prob_matrix = generate_score_matrix(pred_h_xg, pred_a_xg)
        
        valid_scores = [s for s in scores_list if s[1] > 0.012]
        pred_top1 = valid_scores[0][0]
        pred_top3 = [s[0] for s in valid_scores[:3]]
        
        actual_score = f"{int(row['home_goals'])}-{int(row['away_goals'])}"
        total_predicted += 1
        
        if actual_score == pred_top1: top1_hits += 1
        if actual_score in pred_top3: top3_hits += 1
            
        clf_probs = calibrated_clf.predict_proba(feat)[0]
        p_a_clf, p_d_clf, p_h_clf = clf_probs[0], clf_probs[1], clf_probs[2]
        
        max_p = max(p_h_clf, p_d_clf, p_a_clf)
        bet_choice = ""
        
        if max_p > 0.55: 
            if max_p == p_h_clf: bet_choice = "主胜"
            elif max_p == p_d_clf: bet_choice = "平局"
            else: bet_choice = "客胜"
            
        if bet_choice == "平局" and (pred_h_xg + pred_a_xg) > 2.8:
            bet_choice = "" # 强制平局熔断
            
        if bet_choice:
            actual_res = "主胜" if row['home_goals'] > row['away_goals'] else ("平局" if row['home_goals'] == row['away_goals'] else "客胜")
            sim_odds = 2.0 
            if bet_choice == actual_res: profit = bet_amount * (sim_odds - 1)
            else: profit = -bet_amount
            bankroll += profit
            records.append({'date': m_date.strftime('%Y-%m-%d'), 'profit': profit, 'bankroll': bankroll})
            
        act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
        act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
        
        team_stats[h]['xg'].append(act_h_xg); team_stats[h]['xga'].append(act_a_xg)
        team_stats[a]['xg'].append(act_a_xg); team_stats[a]['xga'].append(act_h_xg)
        team_stats[h]['home_xg'].append(act_h_xg); team_stats[h]['home_xga'].append(act_a_xg)
        team_stats[a]['away_xg'].append(act_a_xg); team_stats[a]['away_xga'].append(act_h_xg)
        
        team_stats[h]['opp_elo'].append(a_elo); team_stats[a]['opp_elo'].append(h_elo)
        team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        team_stats[h]['dates'].append(m_date); team_stats[a]['dates'].append(m_date)
        last_date[h] = m_date; last_date[a] = m_date

    total_bets = len(records)
    win_rate = 0.0
    roi = 0.0
    total_profit = 0.0
    
    if total_bets > 0:
        df_rec = pd.DataFrame(records)
        win_bets = len(df_rec[df_rec['profit'] > 0])
        win_rate = (win_bets / total_bets) * 100
        total_profit = df_rec['profit'].sum()
        roi = (total_profit / (total_bets * bet_amount)) * 100
        
        plt.figure(figsize=(10, 5))
        plt.plot(range(len(df_rec)), df_rec['bankroll'], marker='', color='gold', linewidth=2, label='资金曲线')
        plt.axhline(y=10000, color='red', linestyle='--', label='初始资金')
        plt.title('真实滚动回测 (未来盲测) 资金曲线')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig('backtest_roi.png', dpi=120)
        plt.close()
    
    top1_acc = (top1_hits / total_predicted) * 100 if total_predicted > 0 else 0
    top3_acc = (top3_hits / total_predicted) * 100 if total_predicted > 0 else 0
    
    print(f"✅ 真实盲测完成！下注胜率 {win_rate:.1f}%，ROI {roi:+.1f}%")
    print(f"🎯 比分命中率：首选 {top1_acc:.1f}%，前三 {top3_acc:.1f}%")
    
    report = f"""--- 历史回测报告 (V45.0 防御极客版) ---
训练数据量: {len(train_df)} 场
测试数据量: {total_predicted} 场

首选比分精准命中率: {top1_acc:.2f}%
Top3比分包含命中率: {top3_acc:.2f}%

下注胜率: {win_rate:.2f}%
总收益率 (ROI): {roi:+.2f}%
总盈亏: {total_profit:+.2f} 元
========================================
"""
    with open('backtest_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ 科学盲测报告已强制写入！")

if __name__ == "__main__":
    run_backtest()
