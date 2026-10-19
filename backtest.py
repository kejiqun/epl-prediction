import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestRegressor, StackingRegressor
from sklearn.neural_network import MLPRegressor
from scipy.stats import poisson
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

team_mapping = {
    'Arsenal FC': '阿森纳', 'Arsenal': '阿森纳', 'Aston Villa FC': '阿斯顿维拉', 'Aston Villa': '阿斯顿维拉',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Brighton & Hove Albion FC': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西', 'Crystal Palace FC': '水晶宫', 'Crystal Palace': '水晶宫',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿', 'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Ipswich Town FC': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester City FC': '莱斯特城', 'Leicester City': '莱斯特城',
    'Liverpool FC': '利物浦', 'Liverpool': '利物浦', 'Manchester City FC': '曼城', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United FC': '曼联', 'Manchester United': '曼联', 'Man United': '曼联', 'Man Utd': '曼联',
    'Newcastle United FC': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联', 'Newcastle': '纽卡斯尔联',
    'Nottingham Forest FC': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林',
    'Southampton FC': '南安普顿', 'Southampton': '南安普顿', 'Tottenham Hotspur FC': '托特纳姆热刺', 'Tottenham Hotspur': '托特纳姆热刺', 'Tottenham': '托特纳姆热刺',
    'West Ham United FC': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolverhampton Wanderers FC': '狼队', 'Wolverhampton Wanderers': '狼队', 'Wolves': '狼队',
    'Leeds United FC': '利兹联', 'Leeds United': '利兹联', 'Sunderland AFC': '桑德兰', 'Sunderland': '桑德兰',
    'Hull City AFC': '赫尔城', 'Hull City': '赫尔城', 'Coventry City FC': '考文垂', 'Coventry City': '考文垂'
}

def translate_team_name(name):
    if isinstance(name, str): return team_mapping.get(name.replace(" and ", " & ").strip(), name)
    return name

print("⏳ 正在启动时光机，加载历史数据...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats = {}; last_match_date = {}; features_list = []

for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats:
            team_stats[t] = {'scored':[], 'conceded':[], 'points':[], 'home_scored':[], 'home_conceded':[], 'away_scored':[], 'away_conceded':[]}
        if t not in last_match_date: last_match_date[t] = None

    h_rest = min(max((date - last_match_date[home]).days if last_match_date[home] else 7, 2), 14)
    a_rest = min(max((date - last_match_date[away]).days if last_match_date[away] else 7, 2), 14)

    h_avg_scored = np.mean(team_stats[home]['scored'][-5:]) if team_stats[home]['scored'] else league_avg_goals
    h_avg_conceded = np.mean(team_stats[home]['conceded'][-5:]) if team_stats[home]['conceded'] else league_avg_goals
    a_avg_scored = np.mean(team_stats[away]['scored'][-5:]) if team_stats[away]['scored'] else league_avg_goals
    a_avg_conceded = np.mean(team_stats[away]['conceded'][-5:]) if team_stats[away]['conceded'] else league_avg_goals

    h_attack, h_defense = h_avg_scored / league_avg_goals, h_avg_conceded / league_avg_goals
    a_attack, a_defense = a_avg_scored / league_avg_goals, a_avg_conceded / league_avg_goals

    h_home_scored = np.mean(team_stats[home]['home_scored'][-3:]) if team_stats[home]['home_scored'] else league_avg_goals
    h_home_conceded = np.mean(team_stats[home]['home_conceded'][-3:]) if team_stats[home]['home_conceded'] else league_avg_goals
    a_away_scored = np.mean(team_stats[away]['away_scored'][-3:]) if team_stats[away]['away_scored'] else league_avg_goals
    a_away_conceded = np.mean(team_stats[away]['away_conceded'][-3:]) if team_stats[away]['away_conceded'] else league_avg_goals

    h_home_attack, h_home_defense = h_home_scored / league_avg_goals, h_home_conceded / league_avg_goals
    a_away_attack, a_away_defense = a_away_scored / league_avg_goals, a_away_conceded / league_avg_goals

    h_pts_series, a_pts_series = team_stats[home]['points'], team_stats[away]['points']
    h_win_rate = np.mean(h_pts_series[-5:]) if h_pts_series else 0.5
    a_win_rate = np.mean(a_pts_series[-5:]) if a_pts_series else 0.5
    h_form_trend = (np.mean(h_pts_series[-3:]) - np.mean(h_pts_series[-5:])) if len(h_pts_series) >= 5 else 0.0
    a_form_trend = (np.mean(a_pts_series[-3:]) - np.mean(a_pts_series[-5:])) if len(a_pts_series) >= 5 else 0.0

    features_list.append({
        'attack': h_attack, 'defense': h_defense, 'opp_attack': a_attack, 'opp_defense': a_defense,
        'home_attack_spec': h_home_attack, 'home_defense_spec': h_home_defense,
        'away_attack_spec': a_away_attack, 'away_defense_spec': a_away_defense,
        'win_rate': h_win_rate, 'opp_win_rate': a_win_rate, 'win_rate_diff': h_win_rate - a_win_rate,
        'rest_days': h_rest, 'opp_rest_days': a_rest, 'is_home': 1,
        'home_rank': 15, 'away_rank': 15,
        'h_form_trend': h_form_trend, 'a_form_trend': a_form_trend,
        'prob_h_odds': 0.33, 'prob_d_odds': 0.33, 'prob_a_odds': 0.33,
        'home_goals': row['home_goals'], 'away_goals': row['away_goals'],
        'date': date
    })

    team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
    team_stats[home]['home_scored'].append(row['home_goals']); team_stats[home]['home_conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
    team_stats[away]['away_scored'].append(row['away_goals']); team_stats[away]['away_conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    last_match_date[home] = date; last_match_date[away] = date

df_model = pd.DataFrame(features_list)

feature_cols = [
    'attack', 'defense', 'opp_attack', 'opp_defense',
    'home_attack_spec', 'home_defense_spec', 'away_attack_spec', 'away_defense_spec',
    'win_rate', 'opp_win_rate', 'win_rate_diff',
    'rest_days', 'opp_rest_days', 'is_home',
    'home_rank', 'away_rank', 'h_form_trend', 'a_form_trend',
    'prob_h_odds', 'prob_d_odds', 'prob_a_odds'
]

split_idx = int(len(df_model) * 0.8)
train_df = df_model.iloc[:split_idx]
test_df = df_model.iloc[split_idx:]

X_train = train_df[feature_cols].fillna(0.33)
y_home_train = train_df['home_goals'].astype(int)
y_away_train = train_df['away_goals'].astype(int)

print(f"⏳ 正在训练模型 (样本量: {len(X_train)})...")
estimators = [
    ('xgb', xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42)),
    ('lgbm', lgb.LGBMRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, verbose=-1))
]
final_estimator = xgb.XGBRegressor(n_estimators=50, max_depth=3, random_state=42)
model_home = StackingRegressor(estimators=estimators, final_estimator=final_estimator, cv=3)
model_away = StackingRegressor(estimators=estimators, final_estimator=final_estimator, cv=3)

model_home.fit(X_train, y_home_train)
model_away.fit(X_train, y_away_train)

print(f"⏳ 开始在测试集上模拟下注 (共 {len(test_df)} 场)...")
X_test = test_df[feature_cols].fillna(0.33)
test_home_xg = model_home.predict(X_test)
test_away_xg = model_away.predict(X_test)

ODDS_H, ODDS_D, ODDS_A = 2.0, 3.3, 3.5
initial_bankroll = 1000.0
bankroll = initial_bankroll
bankroll_history = [bankroll]
bets_placed = 0
bets_won = 0
max_bankroll = bankroll
max_drawdown = 0.0

for i in range(len(test_df)):
    hg_exp, ag_exp = max(0.1, test_home_xg[i]), max(0.1, test_away_xg[i])
    prob_matrix = np.zeros((6, 6))
    for hg in range(6):
        for ag in range(6):
            prob_matrix[hg][ag] = poisson.pmf(hg, hg_exp) * poisson.pmf(ag, ag_exp)
    
    prob_h = np.sum(np.tril(prob_matrix, -1))
    prob_d = np.sum(np.diag(prob_matrix))
    prob_a = np.sum(np.triu(prob_matrix, 1))
    total_p = prob_h + prob_d + prob_a
    prob_h /= total_p; prob_d /= total_p; prob_a /= total_p
    
    kelly_h = max(0, (prob_h * ODDS_H - 1) / (ODDS_H - 1))
    kelly_d = max(0, (prob_d * ODDS_D - 1) / (ODDS_D - 1))
    kelly_a = max(0, (prob_a * ODDS_A - 1) / (ODDS_A - 1))
    
    best_kelly, best_choice = 0, None
    if kelly_h > best_kelly: best_kelly, best_choice = kelly_h, 'H'
    if kelly_d > best_kelly: best_kelly, best_choice = kelly_d, 'D'
    if kelly_a > best_kelly: best_kelly, best_choice = kelly_a, 'A'
    
    bet_amount = 0
    if best_kelly > 0.02:
        # 🛠️ 核心修改：平注+最高限额！每次最多下注资金的 2%（防止复利爆炸）
        bet_amount = initial_bankroll * 0.02 
        bets_placed += 1
        
    if bet_amount > 0:
        hg_real = test_df.iloc[i]['home_goals']
        ag_real = test_df.iloc[i]['away_goals']
        real_res = 'H' if hg_real > ag_real else ('D' if hg_real == ag_real else 'A')
        
        if best_choice == real_res:
            if best_choice == 'H': bankroll += bet_amount * (ODDS_H - 1)
            elif best_choice == 'D': bankroll += bet_amount * (ODDS_D - 1)
            else: bankroll += bet_amount * (ODDS_A - 1)
            bets_won += 1
        else:
            bankroll -= bet_amount
            
    bankroll_history.append(bankroll)
    # 计算最大回撤
    if bankroll > max_bankroll: max_bankroll = bankroll
    drawdown = (max_bankroll - bankroll) / max_bankroll * 100
    if drawdown > max_drawdown: max_drawdown = drawdown

plt.figure(figsize=(10, 5))
plt.plot(bankroll_history, label='资金曲线 (Bankroll)', color='green', linewidth=2)
plt.axhline(y=initial_bankroll, color='red', linestyle='--', label='初始资金 (1000)')
plt.title('时光机回测：V31 模型历史资金曲线 (严格平注限额版)')
plt.xlabel('下注场次')
plt.ylabel('资金余额')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('backtest_roi.png', dpi=150)

roi = (bankroll - initial_bankroll) / initial_bankroll * 100
win_rate = (bets_won / bets_placed * 100) if bets_placed > 0 else 0

report = f"""
====================================
⚽ 时光机回测报告 (严格限额版 V2.0)
====================================
回测比赛总数: {len(test_df)} 场
实际下注场次: {bets_placed} 场
命中场次: {bets_won} 场
下注胜率: {win_rate:.2f}%
初始资金: {initial_bankroll:.2f}
最终资金: {bankroll:.2f}
总收益率 (ROI): {roi:+.2f}%
最大回撤 (Max Drawdown): -{max_drawdown:.2f}%
====================================
"""
print(report)
with open('backtest_report.txt', 'w', encoding='utf-8') as f:
    f.write(report)
print("✅ 回测完毕！已生成 backtest_roi.png 和 backtest_report.txt")
