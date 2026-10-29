import pandas as pd
import numpy as np
import joblib
import os
import warnings
import lightgbm as lgb
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from team_mapping import translate_team_name

warnings.filterwarnings('ignore')
print("==================================================")
print("🚀 启动 V31.0 模型重训引擎 (16 维标准特征版)")
print("==================================================")

# 1. 加载数据
if not os.path.exists('all_leagues_matches.csv'):
    print("❌ 缺少 all_leagues_matches.csv")
    exit()

df_hist = pd.read_csv('all_leagues_matches.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist['h_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['a_cn'] = df_hist['away_team'].apply(translate_team_name)
df_hist = df_hist.sort_values('date')
df_hist = df_hist.dropna(subset=['home_goals', 'away_goals'])

# 加载 Elo 评分 (如果存在)
elo_dict = joblib.load('elo_dict.pkl') if os.path.exists('elo_dict.pkl') else {}

# 2. 构造 16 维特征引擎
print("⏳ 正在构建特征库...")
avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
stats, last_date = {}, {}

X_data = []
y_h, y_a, y_res = [], [], []

for idx, r in df_hist.iterrows():
    h, a, d = r['h_cn'], r['a_cn'], r['date']
    for t in [h, a]:
        if t not in stats: 
            stats[t] = {'xg':[], 'xga':[], 'h_xg':[], 'h_xga':[], 'a_xg':[], 'a_xga':[], 'dates':[], 'count':0}
        if t not in last_date: 
            last_date[t] = None

    hs, as_ = stats[h], stats[a]
    
    # 当两队都有 >= 3 场数据时，构造特征
    if hs['count'] >= 3 and as_['count'] >= 3:
        h_rest = (d - last_date[h]).days if last_date[h] else 7
        a_rest = (d - last_date[a]).days if last_date[a] else 7
        
        def decay_mean(arr, decay=0.7):
            if not arr: return avg_goals
            arr = np.array(arr)
            w = np.array([decay ** (len(arr) - 1 - i) for i in range(len(arr))])
            return np.sum(arr * (w / np.sum(w)))

        # 🌟 严格 16 维特征，与 final_prediction.py 完全对齐
        feat = np.array([
            elo_dict.get(h, 1500), elo_dict.get(a, 1500), elo_dict.get(h, 1500) - elo_dict.get(a, 1500), 1500, 1500,
            decay_mean(hs['xg'][-5:]), decay_mean(as_['xg'][-5:]),
            decay_mean(hs['xga'][-5:]), decay_mean(as_['xga'][-5:]),
            np.mean(hs['h_xg'][-3:]) if hs['h_xg'] else decay_mean(hs['xg'][-5:]),
            np.mean(hs['h_xga'][-3:]) if hs['h_xga'] else decay_mean(hs['xga'][-5:]),
            np.mean(as_['a_xg'][-3:]) if as_['a_xg'] else decay_mean(as_['xg'][-5:]),
            np.mean(as_['a_xga'][-3:]) if as_['a_xga'] else decay_mean(as_['xga'][-5:]),
            h_rest - a_rest,
            sum(1 for x in hs['dates'] if (d - x).days <= 14),
            sum(1 for x in as_['dates'] if (d - x).days <= 14)
        ]).clip(-1000, 3000)
        
        X_data.append(feat)
        y_h.append(r['home_goals'])
        y_a.append(r['away_goals'])
        
        if r['home_goals'] > r['away_goals']: y_res.append(0)
        elif r['home_goals'] == r['away_goals']: y_res.append(1)
        else: y_res.append(2)

    # 更新历史状态
    stats[h]['count'] += 1; stats[a]['count'] += 1
    stats[h]['xg'].append(r['home_goals']); stats[h]['xga'].append(r['away_goals'])
    stats[a]['xg'].append(r['away_goals']); stats[a]['xga'].append(r['home_goals'])
    stats[h]['h_xg'].append(r['home_goals']); stats[h]['h_xga'].append(r['away_goals'])
    stats[a]['a_xg'].append(r['away_goals']); stats[a]['a_xga'].append(r['home_goals'])
    stats[h]['dates'].append(d); stats[a]['dates'].append(d)
    last_date[h], last_date[a] = d, d

# 3. 转换为 Numpy 数组
X = np.array(X_data)
y_h = np.array(y_h)
y_a = np.array(y_a)
y_res = np.array(y_res)

print(f"✅ 特征构建完成，共 {len(X)} 场比赛，特征维度: {X.shape[1]}")

# 4. 训练模型
print("⏳ 正在训练 LightGBM 与 XGBoost 模型...")

# 训练主场进球模型
m_h_lgb = lgb.LGBMRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42, n_jobs=-1).fit(X, y_h)
m_h_xgb = xgb.XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42, n_jobs=-1).fit(X, y_h)

# 训练客场进球模型
m_a_lgb = lgb.LGBMRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42, n_jobs=-1).fit(X, y_a)
m_a_xgb = xgb.XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42, n_jobs=-1).fit(X, y_a)

# 训练胜平负分类器
clf = LogisticRegression(max_iter=1000, random_state=42).fit(X, y_res)

# 5. 保存模型
joblib.dump(m_h_lgb, 'epl_v31_home_goals_model_lgb.pkl')
joblib.dump(m_h_xgb, 'epl_v31_home_goals_model_xgb.pkl')
joblib.dump(m_a_lgb, 'epl_v31_away_goals_model_lgb.pkl')
joblib.dump(m_a_xgb, 'epl_v31_away_goals_model_xgb.pkl')
joblib.dump(clf, 'epl_result_classifier.pkl')

print("🎉 16 维模型重训完成！所有 .pkl 文件已覆盖更新，完美匹配 V350.0 预测引擎。")
