import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, log_loss
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

print("⏳ 正在启动时光机 V6.0 (核心分类重构版)...")
df_hist = pd.read_csv('epl_matches_10y.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values('date').reset_index(drop=True)
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

try:
    df_odds = pd.read_csv('epl_matches_odds.csv')
    rename_dict = {'date': 'date', 'home_team': 'home_team', 'away_team': 'away_team', 'b365_h': 'odds_h', 'b365_d': 'odds_d', 'b365_a': 'odds_a'}
    df_odds = df_odds.rename(columns=rename_dict)
    df_odds['date'] = pd.to_datetime(df_odds['date'], errors='coerce')
    df_odds = df_odds.dropna(subset=['date', 'odds_h', 'odds_d', 'odds_a'])
    df_odds['home_team_cn'] = df_odds['home_team'].apply(translate_team_name)
    df_odds['away_team_cn'] = df_odds['away_team'].apply(translate_team_name)
    
    df_hist = pd.merge(df_hist, df_odds[['date', 'home_team_cn', 'away_team_cn', 'odds_h', 'odds_d', 'odds_a']], 
                       on=['date', 'home_team_cn', 'away_team_cn'], how='inner') # 只保留有赔率的比赛
    print(f"✅ 成功筛选出 {len(df_hist)} 场有真实赔率的历史比赛。")
except Exception as e:
    print(f"⚠️ 加载赔率失败: {e}"); exit()

# 基础特征计算（严格遵守时序，不使用未来数据）
team_stats = {}; last_match_date = {}; features_list = []

for idx, row in df_hist.iterrows():
    home, away, date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [home, away]:
        if t not in team_stats: team_stats[t] = {'scored':[], 'conceded':[], 'points':[]}
        if t not in last_match_date: last_match_date[t] = None

    # 严格计算赛前已知的平均值
    h_avg_scored = np.mean(team_stats[home]['scored'][-5:]) if team_stats[home]['scored'] else 1.5
    h_avg_conceded = np.mean(team_stats[home]['conceded'][-5:]) if team_stats[home]['conceded'] else 1.2
    a_avg_scored = np.mean(team_stats[away]['scored'][-5:]) if team_stats[away]['scored'] else 1.2
    a_avg_conceded = np.mean(team_stats[away]['conceded'][-5:]) if team_stats[away]['conceded'] else 1.5
    
    h_rest = min(max((date - last_match_date[home]).days if last_match_date[home] else 7, 2), 14)
    a_rest = min(max((date - last_match_date[away]).days if last_match_date[away] else 7, 2), 14)
    
    h_win_rate = np.mean(team_stats[home]['points'][-5:]) if team_stats[home]['points'] else 1.0
    a_win_rate = np.mean(team_stats[away]['points'][-5:]) if team_stats[away]['points'] else 1.0

    # 市场隐含概率
    imp_h = 1 / row['odds_h']; imp_d = 1 / row['odds_d']; imp_a = 1 / row['odds_a']
    total_imp = imp_h + imp_d + imp_a
    prob_h = imp_h / total_imp; prob_d = imp_d / total_imp; prob_a = imp_a / total_imp

    features_list.append({
        'h_avg_scored': h_avg_scored, 'h_avg_conceded': h_avg_conceded,
        'a_avg_scored': a_avg_scored, 'a_avg_conceded': a_avg_conceded,
        'h_rest': h_rest, 'a_rest': a_rest,
        'h_win_rate': h_win_rate, 'a_win_rate': a_win_rate,
        'prob_h_odds': prob_h, 'prob_d_odds': prob_d, 'prob_a_odds': prob_a,
        'home_goals': row['home_goals'], 'away_goals': row['away_goals'],
        'odds_h': row['odds_h'], 'odds_d': row['odds_d'], 'odds_a': row['odds_a']
    })

    team_stats[home]['scored'].append(row['home_goals']); team_stats[home]['conceded'].append(row['away_goals'])
    h_pts = 3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[home]['points'].append(h_pts)
    
    team_stats[away]['scored'].append(row['away_goals']); team_stats[away]['conceded'].append(row['home_goals'])
    a_pts = 3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0)
    team_stats[away]['points'].append(a_pts)
    
    last_match_date[home] = date; last_match_date[away] = date

df_model = pd.DataFrame(features_list)

# 目标变量：0=客胜，1=平局，2=主胜
def get_result(row):
    if row['home_goals'] > row['away_goals']: return 2
    elif row['home_goals'] == row['away_goals']: return 1
    else: return 0

df_model['result'] = df_model.apply(get_result, axis=1)

# 严格时序切分：前 80% 训练，后 20% 测试
split_idx = int(len(df_model) * 0.8)
train_df = df_model.iloc[:split_idx]
test_df = df_model.iloc[split_idx:]

# 特征列（包含了市场赔率概率，让模型学习如何“修正”市场）
feature_cols = [
    'h_avg_scored', 'h_avg_conceded', 'a_avg_scored', 'a_avg_conceded',
    'h_rest', 'a_rest', 'h_win_rate', 'a_win_rate',
    'prob_h_odds', 'prob_d_odds', 'prob_a_odds'
]

X_train = train_df[feature_cols]
y_train = train_df['result']
X_test = test_df[feature_cols]
y_test = test_df['result']

print(f"⏳ 正在训练【多分类 XGBoost 模型】(训练样本: {len(X_train)})...")
# 使用多分类模型，直接预测 胜/平/负
model = xgb.XGBClassifier(
    n_estimators=200, max_depth=4, learning_rate=0.05, 
    objective='multi:softprob', num_class=3, random_state=42, n_jobs=-1
)
model.fit(X_train, y_train)

# 预测概率
test_probs = model.predict_proba(X_test)

initial_bankroll = 1000.0
bankroll = initial_bankroll
bankroll_history = [bankroll]
bets_placed = 0
bets_won = 0
max_drawdown = 0.0
max_bankroll = bankroll

print(f"⏳ 开始基于【模型修正概率】进行价值下注...")
for i in range(len(test_df)):
    if bankroll < initial_bankroll * 0.5:
        print(f"🛑 触发止损熔断！资金跌破 50%。当前场次: {i}")
        bankroll_history.extend([bankroll] * (len(test_df) - i))
        break

    p_a, p_d, p_h = test_probs[i][0], test_probs[i][1], test_probs[i][2]
    
    odds_h = test_df.iloc[i]['odds_h']
    odds_d = test_df.iloc[i]['odds_d']
    odds_a = test_df.iloc[i]['odds_a']
    
    ev_h = p_h * odds_h
    ev_d = p_d * odds_d
    ev_a = p_a * odds_a
    
    best_ev, best_choice, best_prob = 0, None, 0
    if ev_h > best_ev: best_ev, best_choice, best_prob = ev_h, 'H', p_h
    if ev_d > best_ev: best_ev, best_choice, best_prob = ev_d, 'D', p_d
    if ev_a > best_ev: best_ev, best_choice, best_prob = ev_a, 'A', p_a
    
    # 职业级过滤条件：
    # 1. 预期收益 EV > 1.1 (至少 10% 利润)
    # 2. 模型预测概率 > 30%（避免瞎蒙）
    # 3. 模型概率必须比市场概率高出 5% 以上（说明模型看到了市场的盲点）
    market_p = test_df.iloc[i]['prob_h_odds'] if best_choice=='H' else (test_df.iloc[i]['prob_d_odds'] if best_choice=='D' else test_df.iloc[i]['prob_a_odds'])
    
    bet_amount = 0
    if best_ev > 1.10 and best_prob > 0.30 and (best_prob - market_p) > 0.05:
        # 使用分数凯利下注（保守型）
        kelly = (best_ev - 1) / (odds_h if best_choice=='H' else (odds_d if best_choice=='D' else odds_a) - 1)
        safe_kelly = max(0, kelly) * 0.25 # 四分之一凯利
        bet_amount = bankroll * min(safe_kelly, 0.05) # 最多下注 5%
        bets_placed += 1
        
    if bet_amount > 0:
        hg_real = test_df.iloc[i]['home_goals']
        ag_real = test_df.iloc[i]['away_goals']
        real_res = 'H' if hg_real > ag_real else ('D' if hg_real == ag_real else 'A')
        
        if best_choice == real_res:
            if best_choice == 'H': bankroll += bet_amount * (odds_h - 1)
            elif best_choice == 'D': bankroll += bet_amount * (odds_d - 1)
            else: bankroll += bet_amount * (odds_a - 1)
            bets_won += 1
        else:
            bankroll -= bet_amount
            
    bankroll_history.append(bankroll)
    if bankroll > max_bankroll: max_bankroll = bankroll
    drawdown = (max_bankroll - bankroll) / max_bankroll * 100
    if drawdown > max_drawdown: max_drawdown = drawdown

plt.figure(figsize=(10, 5))
plt.plot(bankroll_history, label='资金曲线 (Bankroll)', color='green', linewidth=2)
plt.axhline(y=initial_bankroll, color='red', linestyle='--', label='初始资金 (1000)')
plt.title('时光机回测：V31 模型历史资金曲线 (V6.0 核心重构版)')
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
⚽ 时光机回测报告 (V6.0 核心分类重构版)
====================================
回测比赛总数: {len(test_df)} 场
实际下注场次: {bets_placed} 场 (严格过滤市场盲点)
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
print("✅ 重构回测完毕！")
