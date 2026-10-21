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

def dixon_coles_tau(h, a, home_xg, away_xg, rho=-0.1):
    if h == 0 and a == 0: return 1 - home_xg * away_xg * rho
    elif h == 0 and a == 1: return 1 + home_xg * rho
    elif h == 1 and a == 0: return 1 + away_xg * rho
    elif h == 1 and a == 1: return 1 - rho
    return 1.0

def run_backtest():
    print("⏳ 启动时光机回测系统 (V27.0 10大特征版)...")
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
        model_h = joblib.load('epl_v31_home_goals_model.pkl')
        model_a = joblib.load('epl_v31_away_goals_model.pkl')
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
    
    for idx, row in df.iterrows():
        h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        
        for t in [h, a]:
            if t not in team_stats: team_stats[t] = {'xg':[], 'opp_elo':[], 'pts':[]}
            if t not in last_date: last_date[t] = None
                
        if m_date >= backtest_start_date:
            h_rest = (m_date - last_date[h]).days if last_date[h] else 7
            a_rest = (m_date - last_date[a]).days if last_date[a] else 7
            rest_diff = h_rest - a_rest
            
            h_xg = np.mean(team_stats[h]['xg'][-5:]) if team_stats[h]['xg'] else league_avg_goals
            a_xg = np.mean(team_stats[a]['xg'][-5:]) if team_stats[a]['xg'] else league_avg_goals
            h_sos = np.mean(team_stats[h]['opp_elo'][-5:]) if team_stats[h]['opp_elo'] else 1500
            a_sos = np.mean(team_stats[a]['opp_elo'][-5:]) if team_stats[a]['opp_elo'] else 1500
            h_pts = np.mean(team_stats[h]['pts'][-5:]) if team_stats[h]['pts'] else 1.0
            a_pts = np.mean(team_stats[a]['pts'][-5:]) if team_stats[a]['pts'] else 1.0
            
            h_elo = elo_dict.get(h, 1500)
            a_elo = elo_dict.get(a, 1500)
            
            # 🌟 核心修复：补齐第 10 个特征 rest_diff
            feat = [h_elo, a_elo, h_elo - a_elo, h_sos, a_sos, h_xg, a_xg, h_pts, a_pts, rest_diff]
            feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
            
            clf_probs = calibrated_clf.predict_proba(feat)[0]
            p_a_clf, p_d_clf, p_h_clf = clf_probs[0], clf_probs[1], clf_probs[2]
            
            max_p = max(p_h_clf, p_d_clf, p_a_clf)
            bet_choice = ""
            
            if max_p > 0.55: # 设定回测严选胜率阈值
                if max_p == p_h_clf: bet_choice = "主胜"
                elif max_p == p_d_clf: bet_choice = "平局"
                else: bet_choice = "客胜"
                
            if bet_choice:
                actual_res = "主胜" if row['home_goals'] > row['away_goals'] else ("平局" if row['home_goals'] == row['away_goals'] else "客胜")
                sim_odds = 2.0 
                
                if bet_choice == actual_res:
                    profit = bet_amount * (sim_odds - 1)
                else:
                    profit = -bet_amount
                    
                bankroll += profit
                records.append({
                    'date': m_date.strftime('%Y-%m-%d'), 'match': f"{h} vs {a}",
                    'bet': bet_choice, 'actual': actual_res, 'profit': profit, 'bankroll': bankroll
                })
        
        # 更新统计数据
        act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
        act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
        team_stats[h]['xg'].append(act_h_xg); team_stats[h]['opp_elo'].append(elo_dict.get(a, 1500))
        team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        team_stats[a]['xg'].append(act_a_xg); team_stats[a]['opp_elo'].append(elo_dict.get(h, 1500))
        team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        last_date[h] = m_date; last_date[a] = m_date

    if not records:
        print("⚠️ 没有比赛符合严选条件。")
        return
        
    df_rec = pd.DataFrame(records)
    total_bets = len(df_rec)
    win_bets = len(df_rec[df_rec['profit'] > 0])
    win_rate = (win_bets / total_bets) * 100
    total_profit = df_rec['profit'].sum()
    roi = (total_profit / (total_bets * bet_amount)) * 100
    
    print(f"✅ 回测完成！共下注 {total_bets} 场，胜率 {win_rate:.1f}%，总盈亏 {total_profit:+.2f} 元，ROI {roi:+.1f}%")
    
    plt.figure(figsize=(10, 5))
    plt.plot(range(len(df_rec)), df_rec['bankroll'], marker='', color='gold', linewidth=2, label='资金曲线')
    plt.axhline(y=initial_bankroll, color='red', linestyle='--', label='初始资金')
    plt.title('历史回测资金曲线 (V27.0 十维特征版)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig('backtest_roi.png', dpi=120)
    plt.close()
    
    report = f"""--- 历史回测报告 (V27.0 十维特征版) ---
下注胜率: {win_rate:.2f}%
总收益率 (ROI): {roi:+.2f}%
总盈亏: {total_profit:+.2f} 元
========================================
"""
    with open('backtest_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ 回测报告已生成。")

if __name__ == "__main__":
    run_backtest()
