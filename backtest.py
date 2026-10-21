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
    print("⏳ 启动时光机回测系统...")
    
    history_file = 'all_leagues_matches.csv' if os.path.exists('all_leagues_matches.csv') else 'epl_matches_10y.csv'
    if not os.path.exists(history_file):
        print("❌ 找不到历史数据，无法回测。")
        return
        
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
    except:
        print("❌ 找不到模型文件，请先运行 train_v31.py 训练模型。")
        return

    # 模拟资金与回测池
    initial_bankroll = 10000.0
    bankroll = initial_bankroll
    bet_amount = 100.0 # 每场固定下注100元
    records = []
    
    team_stats = {}
    
    # 我们只回测最近一年的数据，之前的作为历史底库
    backtest_start_date = df['date'].max() - pd.Timedelta(days=365)
    
    for idx, row in df.iterrows():
        home, away, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
        
        for t in [home, away]:
            if t not in team_stats: 
                team_stats[t] = {'xg':[], 'xga':[], 'pts':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[]}
                
        if m_date >= backtest_start_date:
            # 提取特征
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
            
            # 采用一个基础的模拟赔率（因为没有历史赔率，我们用行业均值 2.0, 3.3, 3.5 作为基准来测试胜率）
            # 在真实量化中，你可以用同样的逻辑去跑有赔率的历史数据
            sim_odds_h, sim_odds_d, sim_odds_a = 2.10, 3.30, 3.50
            
            # 简单的凯利策略
            kelly_h = (p_h * sim_odds_h - 1) / (sim_odds_h - 1)
            kelly_d = (p_d * sim_odds_d - 1) / (sim_odds_d - 1)
            kelly_a = (p_a * sim_odds_a - 1) / (sim_odds_a - 1)
            
            max_kelly = max(kelly_h, kelly_d, kelly_a)
            bet_choice = ""
            if max_kelly > 0.05: # 回测中稍微放宽门槛
                if max_kelly == kelly_h and p_h > 0.3: bet_choice = "主胜"
                elif max_kelly == kelly_d and p_d > 0.3: bet_choice = "平局"
                elif max_kelly == kelly_a and p_a > 0.3: bet_choice = "客胜"
                
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
        print("⚠️ 在过去一年的回测中，模型没有找到符合下注条件的比赛。")
        return
        
    df_rec = pd.DataFrame(records)
    total_bets = len(df_rec)
    win_bets = len(df_rec[df_rec['profit'] > 0])
    win_rate = (win_bets / total_bets) * 100
    total_profit = df_rec['profit'].sum()
    roi = (total_profit / (total_bets * bet_amount)) * 100
    
    print(f"✅ 回测完成！共下注 {total_bets} 场，胜率 {win_rate:.1f}%，总盈亏 {total_profit:+.2f} 元，ROI {roi:+.1f}%")
    
    # 生成回测报告与曲线图
    plt.figure(figsize=(10, 5))
    plt.plot(range(len(df_rec)), df_rec['bankroll'], marker='', color='gold', linewidth=2, label='资金曲线')
    plt.title('历史回测资金曲线 (每场固定100元)')
    plt.xlabel('下注场次')
    plt.ylabel('资金')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig('backtest_roi.png', dpi=120)
    plt.close()
    
    report = f"""--- 历史回测报告 ---
回测时间段: {backtest_start_date.strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}
总下注场次: {total_bets}
盈利场次: {win_bets}
胜率: {win_rate:.2f}%
总盈亏: {total_profit:+.2f} 元
投资回报率 (ROI): {roi:+.2f}%
"""
    with open('backtest_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ 回测报告已生成 (backtest_report.txt / backtest_roi.png)")

if __name__ == "__main__":
    run_backtest()
