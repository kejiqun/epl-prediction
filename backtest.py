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
    print("⏳ 启动时光机回测系统 (极简严选版)...")
    
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
    except: return

    initial_bankroll = 10000.0
    bankroll = initial_bankroll
    bet_amount = 100.0 
    records = []
    team_stats = {}
    backtest_start_date = df['date'].max() - pd.Timedelta(days=365)
    
    for idx, row in df.iterrows():
        home, away, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        
        for t in [home, away]:
            if t not in team_stats: 
                team_stats[t] = {'xg':[], 'xga':[], 'pts':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[]}
                
        if m_date >= backtest_start_date:
            # 特征提取
            h_all_xg = np.mean(team_stats[home]['xg'][-5:]) if team_stats[home]['xg'] else league_avg_goals
            h_home_xg = np.mean(team_stats[home]['home_xg'][-5:]) if team_stats[home]['home_xg'] else league_avg_goals
            h_home_xga = np.mean(team_stats[home]['home_xga'][-5:]) if team_stats[home]['home_xga'] else league_avg_goals
            h_pts = np.mean(team_stats[home]['pts'][-5:]) if team_stats[home]['pts'] else 1.0
            h_trend = (np.mean(team_stats[home]['pts'][-3:]) - np.mean(team_stats[home]['pts'][-5:])) if len(team_stats[home]['pts']) >= 5 else 0.0
            
            a_all_xg = np.mean(team_stats[away]['xg'][-5:]) if team_stats[away]['xg'] else league_avg_goals
            a_away_xg = np.mean(team_stats[away]['away_xg'][-5:]) if team_stats[away]['away_xg'] else league_avg_goals
            a_away_xga = np.mean(team_stats[away]['away_xga'][-5:]) if team_stats[away]['away_xga'] else league_avg_goals
            a_pts = np.mean(team_stats[away]['pts'][-5:]) if team_stats[away]['pts'] else 1.0
            a_trend = (np.mean(team_stats[away]['pts'][-3:]) - np.mean(team_stats[away]['pts'][-5:])) if len(team_stats[away]['pts']) >= 5 else 0.0
            
            feat = [h_all_xg, a_all_xg, h_home_xg, h_home_xga, a_away_xg, a_away_xga, h_pts, a_pts, h_trend, a_trend]
            feat = np.clip(np.nan_to_num(feat, nan=0.0, posinf=5.0, neginf=0.0), -5.0, 5.0).reshape(1, -1)
            
            pred_h_xg = max(0.1, model_h.predict(feat)[0])
            pred_a_xg = max(0.1, model_a.predict(feat)[0])
            
            prob_matrix = np.zeros((7, 7))
            for i in range(7):
                for j in range(7):
                    prob_matrix[i][j] = poisson.pmf(i, pred_h_xg) * poisson.pmf(j, pred_a_xg) * dixon_coles_tau(i, j, pred_h_xg, pred_a_xg)
            
            p_h, p_d, p_a = np.sum(np.tril(prob_matrix, -1)), np.sum(np.diag(prob_matrix)), np.sum(np.triu(prob_matrix, 1))
            total_p = p_h + p_d + p_a
            p_h, p_d, p_a = p_h/total_p, p_d/total_p, p_a/total_p
            
            # 🌟 动态模拟赔率：根据模型概率反推（加上了庄家抽水）
            # 如果模型算主胜 50%，模拟赔率大概在 1.9 左右
            sim_odds_h = 1 / (p_h + 0.05) if p_h > 0.1 else 15.0
            sim_odds_d = 1 / (p_d + 0.05) if p_d > 0.1 else 15.0
            sim_odds_a = 1 / (p_a + 0.05) if p_a > 0.1 else 15.0
            
            # 🌟 极简严选策略
            # 1. 只买概率最高的一项
            probs = [p_h, p_d, p_a]
            max_p = max(probs)
            bet_choice = ""
            
            if max_p > 0.55: # 胜率不够 55% 绝对不碰
                if max_p == p_h and sim_odds_h > 1.3: bet_choice = "主胜"
                elif max_p == p_d and sim_odds_d > 2.8: bet_choice = "平局"
                elif max_p == p_a and sim_odds_a > 1.6: bet_choice = "客胜"
                
            if bet_choice:
                actual_res = "主胜" if row['home_goals'] > row['away_goals'] else ("平局" if row['home_goals'] == row['away_goals'] else "客胜")
                
                if bet_choice == actual_res:
                    if bet_choice == "主胜": profit = bet_amount * (sim_odds_h - 1)
                    elif bet_choice == "平局": profit = bet_amount * (sim_odds_d - 1)
                    else: profit = bet_amount * (sim_odds_a - 1)
                else:
                    profit = -bet_amount
                    
                bankroll += profit
                records.append({
                    'date': m_date.strftime('%Y-%m-%d'), 'match': f"{home} vs {away}",
                    'bet': bet_choice, 'actual': actual_res, 'profit': profit, 'bankroll': bankroll
                })
        
        # 更新统计数据
        act_h_xg = row['home_xg'] if not pd.isna(row.get('home_xg', np.nan)) else row['home_goals']
        act_a_xg = row['away_xg'] if not pd.isna(row.get('away_xg', np.nan)) else row['away_goals']
        
        team_stats[home]['xg'].append(act_h_xg); team_stats[home]['xga'].append(act_a_xg)
        team_stats[home]['home_xg'].append(act_h_xg); team_stats[home]['home_xga'].append(act_a_xg)
        team_stats[home]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
        
        team_stats[away]['xg'].append(act_a_xg); team_stats[away]['xga'].append(act_h_xg)
        team_stats[away]['away_xg'].append(act_a_xg); team_stats[away]['away_xga'].append(act_h_xg)
        team_stats[away]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))

    if not records:
        print("⚠️ 在过去一年的回测中，由于极度严选，模型没有找到符合条件的比赛。")
        return
        
    df_rec = pd.DataFrame(records)
    total_bets = len(df_rec)
    win_bets = len(df_rec[df_rec['profit'] > 0])
    win_rate = (win_bets / total_bets) * 100 if total_bets > 0 else 0
    total_profit = df_rec['profit'].sum()
    roi = (total_profit / (total_bets * bet_amount)) * 100 if total_bets > 0 else 0
    
    print(f"✅ 回测完成！共下注 {total_bets} 场，胜率 {win_rate:.1f}%，总盈亏 {total_profit:+.2f} 元，ROI {roi:+.1f}%")
    
    # 画图
    plt.figure(figsize=(10, 5))
    plt.plot(range(len(df_rec)), df_rec['bankroll'], marker='', color='gold', linewidth=2, label='资金曲线')
    plt.axhline(y=initial_bankroll, color='red', linestyle='--', label='初始资金')
    plt.title('历史回测资金曲线 (V24.0 极简严选版)')
    plt.xlabel('下注场次')
    plt.ylabel('资金')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig('backtest_roi.png', dpi=120)
    plt.close()
    
    report = f"""--- 历史回测报告 (V24.0 极简严选版) ---
回测时间段: {backtest_start_date.strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}
回测比赛总数: {len(df[df['date'] >= backtest_start_date])} 场
实际下注场次: {total_bets} 场 (极简严选)
命中场次: {win_bets} 场
下注胜率: {win_rate:.2f}%
初始资金: {initial_bankroll:.2f}
最终资金: {bankroll:.2f}
总收益率 (ROI): {roi:+.2f}%
总盈亏: {total_profit:+.2f} 元
========================================
"""
    with open('backtest_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ 回测报告已生成。")

if __name__ == "__main__":
    run_backtest()
