import pandas as pd
import numpy as np
import joblib
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import poisson
import warnings
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

def generate_score_matrix(home_xg, away_xg, max_goals=7, rho=-0.08):
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
    return scores

def run_backtest():
    print("⏳ 启动时光机回测系统 (V34.0)...")
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file): return
        
    df = pd.read_csv(history_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['home_team_cn'] = df['home_team'].apply(translate_team_name)
    df['away_team_cn'] = df['away_team'].apply(translate_team_name)
    
    if os.path.exists('xg_data.csv'):
        df_xg = pd.read_csv('xg_data.csv')
        df_xg['date'] = pd.to_datetime(df_xg['date'])
        df = pd.merge(df, df_xg, on=['date', 'home_team_cn', 'away_team_cn'], how='left', suffixes=('', '_xg'))
    
    league_avg_goals = (df['home_goals'].mean() + df['away_goals'].mean()) / 2
    
    try:
        model_h_lgb = joblib.load('epl_v31_home_goals_model_lgb.pkl')
        model_a_lgb = joblib.load('epl_v31_away_goals_model_lgb.pkl')
        model_h_xgb = joblib.load('epl_v31_home_goals_model_xgb.pkl')
        model_a_xgb = joblib.load('epl_v31_away_goals_model_xgb.pkl')
        calibrated_clf = joblib.load('epl_result_classifier.pkl')
        elo_dict = joblib.load('elo_dict.pkl')
    except Exception as e: 
        print(f"❌ 找不到模型文件: {e}")
        return

    initial_bankroll = 10000.0
    bankroll = initial_bankroll
    bet_amount = 100.0 
    records = []
    team_stats, last_date = {}, {}
    backtest_start_date = df['date'].max() - pd.Timedelta(days=365)
    
    total_predicted = 0
    top1_hits = 0
    top3_hits = 0

    for idx, row in df.iterrows():
        h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        
        for t in [h, a]:
            if t not in team_stats: 
                team_stats[t] = {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[]}
            if t not in last_date: last_date[t] = None
                
        if m_date >= backtest_start_date:
            h_rest = (m_date - last_date[h]).days if last_date[h] else 7
            a_rest = (m_date - last_date[a]).days if last_date[a] else 7
            rest_diff = h_rest - a_rest
            
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
            
            h_elo = elo_dict.get(h, 1500)
            a_elo = elo_dict.get(a, 1500)
            
            feat = [
                h_elo, a_elo, h_elo - a_elo, 
                h_sos, a_sos, h_xg, a_xg, h_xga, a_xga, 
                h_home_xg, h_home_xga, a_away_xg, a_away_xga, rest_diff
            ]
            feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
            
            pred_h_xg_lgb = model_h_lgb.predict(feat)[0]
            pred_h_xg_xgb = model_h_xgb.predict(feat)[0]
            pred_h_xg = max(0.1, (pred_h_xg_lgb + pred_h_xg_xgb) / 2.0)
            
            pred_a_xg_lgb = model_a_lgb.predict(feat)[0]
            pred_a_xg_xgb = model_a_xgb.predict(feat)[0]
            pred_a_xg = max(0.1, (pred_a_xg_lgb + pred_a_xg_xgb) / 2.0)
            
            scores_list = generate_score_matrix(pred_h_xg, pred_a_xg)
            
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
        
        team_stats[h]['opp_elo'].append(elo_dict.get(a, 1500)); team_stats[a]['opp_elo'].append(elo_dict.get(h, 1500))
        team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
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
        plt.axhline(y=initial_bankroll, color='red', linestyle='--', label='初始资金')
        plt.title('历史回测资金曲线 (V34.0)')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig('backtest_roi.png', dpi=120)
        plt.close()
    
    top1_acc = (top1_hits / total_predicted) * 100 if total_predicted > 0 else 0
    top3_acc = (top3_hits / total_predicted) * 100 if total_predicted > 0 else 0
    
    print(f"✅ 回测完成！下注胜率 {win_rate:.1f}%，ROI {roi:+.1f}%")
    print(f"🎯 比分命中率：首选 {top1_acc:.1f}%，前三 {top3_acc:.1f}%")
    
    report = f"""--- 历史回测报告 (V34.0 主客场剥离版) ---
总预测场次: {total_predicted} 场
首选比分精准命中率: {top1_acc:.2f}%
Top3比分包含命中率: {top3_acc:.2f}%

下注胜率: {win_rate:.2f}%
总收益率 (ROI): {roi:+.2f}%
总盈亏: {total_profit:+.2f} 元
========================================
"""
    with open('backtest_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ 新报告已强制写入！")

if __name__ == "__main__":
    run_backtest()
