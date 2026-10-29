import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import TimeSeriesSplit
import lightgbm as lgb
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
import warnings
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')
print("🚀 正在启动 20 维特征终极重训引擎...")

# 1. 加载数据
df_hist = pd.read_csv('all_leagues_matches.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist['h_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['a_cn'] = df_hist['away_team'].apply(translate_team_name)
df_hist = df_hist.sort_values('date')
df_hist = df_hist.dropna(subset=['home_goals', 'away_goals'])

# 2. 构造时间衰减特征引擎
avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
stats, last_date = {}, {}
X_data, y_h, y_a, y_res = [], [], [], []

for idx, r in df_hist.iterrows():
    h, a, d = r['h_cn'], r['a_cn'], r['date']
    for t in [h, a]:
        if t not in stats: 
            stats[t] = {'xg':[], 'xga':[], 'h_xg':[], 'h_xga':[], 'a_xg':[], 'a_xga':[], 'dates':[], 'count':0, 'clean_sheets':0, 'failed_to_score':0}
        if t not in last_date: 
            last_date[t] = None

    hs, as_ = stats[h], stats[a]
    
    # 只有当两队都有 3 场历史数据时，才进行特征构造
    if hs['count'] >= 3 and as_['count'] >= 3:
        h_rest = (d - last_date[h]).days if last_date[h] else 7
        a_rest = (d - last_date[a]).days if last_date[a] else 7
        
        def decay_mean(arr, decay=0.7):
            if not arr: return avg_goals
            arr = np.array(arr)
            w = np.array([decay ** (len(arr) - 1 - i) for i in range(len(arr))])
            return np.sum(arr * (w / np.sum(w)))

        feat = np.array([
            1500, 1500, 0, 1500, 1500, # 这里为了简化，Elo 用假值，实际你可以接入 elo_dict
            decay_mean(hs['xg'][-5:]), decay_mean(as_['xg'][-5:]),
            decay_mean(hs['xga'][-5:]), decay_mean(as_['xga'][-5:]),
            np.mean(hs['h_xg'][-3:]) if hs['h_xg'] else avg_goals,
            np.mean(hs['h_xga'][-3:]) if hs['h_xga'] else avg_goals,
            np.mean(as_['a_xg'][-3:]) if as_['a_xg'] else avg_goals,
            np.mean(as_['a_xga'][-3:]) if as_['a_xga'] else avg_goals,
            h_rest - a_rest,
            sum(1 for d in hs['dates'] if (d - d).days <= 14),
            sum(1 for d in as_['dates'] if (d - d).days <= 14),
            # 🌟 新增 4 维特征
            hs['clean_sheets'] / hs['count'],
            as_['clean_sheets'] / as_['count'],
            hs['failed_to_score'] / hs['count'],
            as_['failed_to_score'] / as_['count']
        ])
        
        X_data.append(feat)
        y_h.append(r['home_goals'])
        y_a.append(r['away_goals'])
        
        # 赛果分类
        if r['home_goals'] > r['away_goals']: y_res.append(0)
        elif r['home_goals'] == r['away_goals']: y_res.append(1)
        else: y_res.append(2)

    # 更新历史状态
    stats[h]['count'] += 1; stats[a]['count'] += 1
    if r['away_goals'] == 0: stats[h]['clean_sheets'] += 1
    if r['home_goals'] == 0: stats[a]['clean_sheets'] += 1
    if r['home_goals'] == 0: stats[h]['failed_to_score'] += 1
    if r['away_goals'] == 0: stats[a]['failed_to_score'] += 1

    stats[h]['xg'].append(r['home_goals']); stats[h]['xga'].append(r['away_goals'])
    stats[a]['xg'].append(r['away_goals']); stats[a]['xga'].append(r['home_goals'])
    stats[h]['h_xg'].append(r['home_goals']); stats[h]['h_xga'].append(r['away_goals'])
    stats[a]['a_xg'].append(r['away_goals']); stats[a]['a_xga'].append(r['home_goals'])
    stats[h]['dates'].append(d); stats[a]['dates'].append(d)
    last_date[h], last_date[a] = d, d

# 3. 训练模型
X = np.array(X_data)
y_h = np.array(y_h)
y_a = np.array(y_a)
y_res = np.array(y_res)

print(f"📊 训练集构建完成，共 {len(X)} 场比赛，特征维度: {X.shape[1]} (必须是 20)")

# 训练主场进球模型
m_h_lgb = lgb.LGBMRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42).fit(X, y_h)
m_h_xgb = xgb.XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42).fit(X, y_h)

# 训练客场进球模型
m_a_lgb = lgb.LGBMRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42).fit(X, y_a)
m_a_xgb = xgb.XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42).fit(X, y_a)

# 训练胜平负分类器（用于校准）
clf = LogisticRegression(max_iter=1000).fit(X, y_res)

# 4. 保存模型
joblib.dump(m_h_lgb, 'epl_v31_home_goals_model_lgb.pkl')
joblib.dump(m_h_xgb, 'epl_v31_home_goals_model_xgb.pkl')
joblib.dump(m_a_lgb, 'epl_v31_away_goals_model_lgb.pkl')
joblib.dump(m_a_xgb, 'epl_v31_away_goals_model_xgb.pkl')
joblib.dump(clf, 'epl_result_classifier.pkl')

print("✅ 20 维模型重训完成！新的 .pkl 文件已覆盖。")
