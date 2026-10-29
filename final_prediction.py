import pandas as pd
import numpy as np
import requests
import joblib
import os
import io
import json
import re
from scipy.stats import poisson
from datetime import datetime, timedelta
import warnings
from openai import OpenAI
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from team_mapping import translate_team_name

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

print("⏳ 正在初始化系统环境及 API 客户端...")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# ================= 工具函数区 =================
def send_rich_email(subject, html_content, img_buffers, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: 
        print("⚠️ 缺少邮箱配置，跳过发送。")
        return
    msg = MIMEMultipart('related')
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, receiver, Header(subject, 'utf-8')
    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)
    msg_alt.attach(MIMEText(html_content, 'html', 'utf-8'))
    for i, buf in enumerate(img_buffers):
        img = MIMEImage(buf.getvalue())
        img.add_header('Content-ID', f'<chart_{i}>')
        msg.attach(img)
    try:
        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtpObj.sendmail(EMAIL_SENDER, [receiver], msg.as_string())
        print("✅ 邮件发送成功！")
    except Exception as e: 
        print(f"❌ 邮件失败: {e}")

def get_match_weather(home_team, date_str):
    city = {'阿森纳': 'London', '曼联': 'Manchester', '利物浦': 'Liverpool', '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '拜仁慕尼黑': 'Munich', '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin', '那不勒斯': 'Naples', '罗马': 'Rome', '多特蒙德': 'Dortmund', '巴黎圣日耳曼': 'Paris'}.get(home_team, 'London')
    try:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            day = resp.json()['forecast']['forecastday'][0]['day']
            return day['condition']['text'], round(day['avgtemp_c'], 1)
    except: 
        pass
    return "未知", 0

def generate_score_matrix(home_xg, away_xg, max_goals=8):
    # 动态 RHO 调整：基于预期总进球数调整比分分布
    total_xg = home_xg + away_xg
    if total_xg > 3.2:
        rho = -0.05  # 倾向于大比分
    elif total_xg < 2.2:
        rho = -0.25  # 倾向于小比分
    else:
        rho = -0.15  # 常规防守

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

def get_total_goals_recommendation(prob_matrix, max_goals=7):
    goal_probs = {}
    for total_g in range(8):
        prob = 0
        for hg in range(total_g + 1):
            ag = total_g - hg
            if hg <= 7 and ag <= 7:
                prob += prob_matrix[hg][ag]
        goal_probs[str(total_g)] = prob
        
    prob_7_plus = 0
    for hg in range(8):
        for ag in range(8):
            if hg + ag >= 7:
                prob_7_plus += prob_matrix[hg][ag]
    goal_probs['7+'] = prob_7_plus
    
    sorted_goals = sorted(goal_probs.items(), key=lambda x: x[1], reverse=True)
    top2_list = [f"{k}球" for k, v in sorted_goals[:2]]
    return " / ".join(top2_list), sorted_goals[0][0] + "球"

# ================= 多智能体核心逻辑 =================
def scout_agent_intel(home_cn, away_cn, league, knowledge):
    """情报官：负责收集战意、德比、球风等场外因素"""
    prompt = f"""你是一名顶级的足球球探。请针对即将到来的比赛：{home_cn} vs {away_cn}（{league}）。
    根据你掌握的世界足球知识，输出双方的【战术风格、近期战意（如保级/争冠/欧战）、主客场因素、是否存在德比或恩怨情仇】。
    请简明扼要，字数在120字以内。如果你不知道这两队的近况，请结合该联赛的普遍特征进行合理推演。
    参考经验库：{knowledge}"""
    try:
        res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        return res.choices[0].message.content.strip()
    except Exception as e: 
        print(f"⚠️ 球探情报获取失败: {e}")
        return "情报收集失败，按基础模型推演。"

def risk_agent_odds_trap(p_h, p_d, p_a, real_h, real_d, real_a):
    """风控官：识别伪数据与机构诱盘（真伪数据筛查）"""
    if real_h == 0: 
        return ""
    # 计算赔率隐含概率（含返还率估计）
    margin = 1/real_h + 1/real_d + 1/real_a
    implied_h, implied_d, implied_a = (1/real_h)/margin, (1/real_d)/margin, (1/real_a)/margin
    
    # 如果模型推算的真实概率远超博彩公司开出的隐含概率，存在极大诱盘嫌疑
    if p_h > implied_h + 0.15: 
        return f"⚠️ 异常：主胜模型概率({p_h*100:.1f}%)远高于隐含概率({implied_h*100:.1f}%)，疑似机构诱盘。"
    if p_d > implied_d + 0.12: 
        return f"⚠️ 异常：平局模型概率({p_d*100:.1f}%)远高于隐含概率({implied_d*100:.1f}%)，疑似机构诱盘。"
    if p_a > implied_a + 0.15: 
        return f"⚠️ 异常：客胜模型概率({p_a*100:.1f}%)远高于隐含概率({implied_a*100:.1f}%)，疑似机构诱盘。"
    return ""

def ai_adjust_probabilities(home_cn, away_cn, p_h, p_d, p_a, injury_info, odds_trend, knowledge, ref_info):
    """风控总监：综合所有维度微调概率"""
    prompt = f"""你是一位量化风控总监。比赛：{home_cn} vs {away_cn}。
    基础概率：主胜 {p_h*100:.1f}%，平局 {p_d*100:.1f}%，客胜 {p_a*100:.1f}%。
    【伤停情报】: {injury_info}；【盘口异动】: {odds_trend}；裁判：{ref_info.get('name', '未知')}。
    请根据【经验库】，输出严格 JSON 格式微调概率：{{"p_h": 0.45, "p_d": 0.30, "p_a": 0.25, "reason": "理由"}}
    【经验库】：{knowledge}"""
    try:
        res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False)
        match = re.search(r'\{.*\}', res.choices[0].message.content.strip(), re.DOTALL)
        if match:
            d = json.loads(match.group(0))
            nh, nd, na = float(d.get('p_h', p_h)), float(d.get('p_d', p_d)), float(d.get('p_a', p_a))
            total = nh + nd + na
            return nh/total, nd/total, na/total, d.get('reason', 'AI微调完成')
    except Exception as e: 
        print(f"⚠️ AI 微调异常: {e}")
    return p_h, p_d, p_a, "AI未干预"

# ================= 主程序初始化 =================
print("⏳ 正在加载资金库及读取赛程数据...")
bankroll = 10000.0
kelly_multiplier = 0.2
if os.path.exists('bankroll.csv'):
    try:
        df_bank = pd.read_csv('bankroll.csv')
        bankroll = df_bank.iloc[-1]['当前资金']
        recent = df_bank.tail(10)
        if '盈亏' in recent.columns:
            wins = len(recent[recent['盈亏'] > 0])
            win_rate = wins / len(recent)
            if win_rate < 0.4: kelly_multiplier = 0.1 
            elif win_rate > 0.6: kelly_multiplier = 0.3
    except Exception as e: 
        print(f"⚠️ 资金库读取失败: {e}")

if not os.path.exists('all_leagues_matches.csv'):
    print("❌ 致命错误：缺少 all_leagues_matches.csv，请先运行 fetch_league_history.py")
    exit()

# 1. 读取自动赛程
df_auto = pd.DataFrame()
if os.path.exists('daily_matches.csv'):
    try:
        df_auto = pd.read_csv('daily_matches.csv')
        df_auto['主队'] = df_auto['主队'].apply(translate_team_name)
        df_auto['客队'] = df_auto['客队'].apply(translate_team_name)
        df_auto['datetime_parsed'] = pd.to_datetime(df_auto['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    except Exception as e:
        print(f"⚠️ 自动赛程读取异常: {e}")

# 2. 读取手动赔率
manual_odds_dict = {}
df_manual = pd.DataFrame()
if os.path.exists('manual_odds.csv'):
    try:
        df_manual_raw = pd.read_csv('manual_odds.csv')
        df_manual_raw['比赛时间_str'] = df_manual_raw['比赛日期'].astype(str).str.strip() + ' ' + df_manual_raw['比赛时间'].astype(str).str.strip()
        df_manual_raw['datetime_parsed'] = pd.to_datetime(df_manual_raw['比赛时间_str'])
        df_manual_raw['主队'] = df_manual_raw['主队'].apply(translate_team_name)
        df_manual_raw['客队'] = df_manual_raw['客队'].apply(translate_team_name)
        
        for _, r in df_manual_raw.iterrows():
            date_str = r['datetime_parsed'].strftime('%Y-%m-%d')
            manual_odds_dict[(date_str, r['主队'], r['客队'])] = r
            
        df_manual['主队'] = df_manual_raw['主队']
        df_manual['客队'] = df_manual_raw['客队']
        df_manual['datetime_parsed'] = df_manual_raw['datetime_parsed']
        df_manual['联赛'] = '手动精选'
        df_manual['比赛时间'] = df_manual['datetime_parsed']
    except Exception as e: 
        print(f"⚠️ 手动赔率读取异常: {e}")

# 3. 合并并执行时间铁闸
df_next_round = pd.concat([df_auto, df_manual]).drop_duplicates(subset=['主队', '客队', 'datetime_parsed'], keep='last')
df_next_round['match_date_str'] = df_next_round['datetime_parsed'].dt.strftime('%Y-%m-%d')

now_ts = pd.Timestamp.now()
end_window = now_ts + pd.Timedelta(hours=24)
df_next_round = df_next_round[(df_next_round['datetime_parsed'] > now_ts) & (df_next_round['datetime_parsed'] <= end_window)].sort_values('datetime_parsed')

if df_next_round.empty: 
    print("⚠️ 未来 24 小时内暂无赛事。")
    html_report = f"""<html><body><div style="text-align: center; padding: 50px;">
        <h2 style="color: #2c3e50;">🛡️ 今日休战</h2>
        <p style="color: #666; font-size: 16px;">未来 24 小时内已无未开赛的足球赛事。</p>
    </div></body></html>"""
    send_rich_email("🛡️ 多联赛每日战报 (今日休战)", html_report, [])
    exit()

print(f"✅ 成功加载 {len(df_next_round)} 场待预测赛事，正在准备辅助数据...")

# 4. 读取真实赔率、裁判、教练
real_odds_dict = {}
if os.path.exists('real_odds.csv'):
    try:
        for _, r in pd.read_csv('real_odds.csv').iterrows():
            date_str = pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d')
            real_odds_dict[(date_str, translate_team_name(r['主队']), translate_team_name(r['客队']))] = r
    except: pass

ref_dict, coach_dict = {}, {}
if os.path.exists('referee_stats.csv'):
    try:
        df_ref = pd.read_csv('referee_stats.csv')
        for _, r in df_ref.iterrows(): 
            ref_dict[(r['主队'], r['客队'])] = {'name': r['主裁判'], 'yellow': r['场均黄牌'], 'penalty': r['场均点球']}
    except: pass
if os.path.exists('coach_stats.csv'):
    try:
        df_coach = pd.read_csv('coach_stats.csv')
        for _, r in df_coach.iterrows(): 
            coach_dict[r['球队']] = {'style': r['教练风格']}
    except: pass

# 5. 读取伤停数据
injury_dict, injury_impact_att, injury_impact_def = {}, {}, {}
try:
    fpl_data = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=15).json()
    teams_map = {t['id']: translate_team_name(t['name']) for t in fpl_data['teams']}
    for e in fpl_data['elements']:
        if (e['status'] in ['d', 'i', 's', 'u'] or (e.get('chance_of_playing_next_round') or 100) < 75) and (e.get('now_cost', 0) >= 50 or e.get('total_points', 0) >= 20):
            t_name = teams_map.get(e['team'])
            if t_name:
                injury_dict.setdefault(t_name, []).append(f"{e['web_name']}")
                pos = e.get('element_type')
                cost_weight = e.get('now_cost', 50) / 100.0
                if pos in [3, 4]: 
                    injury_impact_att[t_name] = injury_impact_att.get(t_name, 0) + cost_weight * 0.1
                elif pos in [1, 2]: 
                    injury_impact_def[t_name] = injury_impact_def.get(t_name, 0) + cost_weight * 0.1
except Exception as e: 
    print(f"⚠️ FPL 伤病数据获取失败: {e}")

# 6. 构建庞大历史特征库
print("⏳ 正在构建历史特征库...")
df_hist = pd.read_csv('all_leagues_matches.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist['home_team_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['away_team_cn'] = df_hist['away_team'].apply(translate_team_name)

league_avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2
team_stats, last_date = {}, {}
for _, row in df_hist.iterrows():
    h, a, m_date = row['home_team_cn'], row['away_team_cn'], row['date']
    for t in [h, a]:
        if t not in team_stats: 
            team_stats[t] = {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[], 'count': 0}
        if t not in last_date: 
            last_date[t] = None
        
    team_stats[h]['count'] += 1
    team_stats[a]['count'] += 1
    
    act_h_xg = row['home_goals']
    act_a_xg = row['away_goals']
    
    team_stats[h]['xg'].append(act_h_xg); team_stats[h]['xga'].append(act_a_xg)
    team_stats[a]['xg'].append(act_a_xg); team_stats[a]['xga'].append(act_h_xg)
    team_stats[h]['home_xg'].append(act_h_xg); team_stats[h]['home_xga'].append(act_a_xg)
    team_stats[a]['away_xg'].append(act_a_xg); team_stats[a]['away_xga'].append(act_h_xg)
    
    team_stats[h]['opp_elo'].append(1500); team_stats[a]['opp_elo'].append(1500)
    team_stats[h]['pts'].append(3 if row['home_goals'] > row['away_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    team_stats[a]['pts'].append(3 if row['away_goals'] > row['home_goals'] else (1 if row['home_goals'] == row['away_goals'] else 0))
    
    team_stats[h]['dates'].append(m_date); team_stats[a]['dates'].append(m_date)
    last_date[h] = m_date; last_date[a] = m_date

elo_dict = {}
if os.path.exists('elo_dict.pkl'): 
    try: elo_dict = joblib.load('elo_dict.pkl')
    except: pass

knowledge_base = open('knowledge.txt', 'r', encoding='utf-8').read() if os.path.exists('knowledge.txt') else ""

# 7. 加载机器学习模型
print("⏳ 正在加载 LightGBM 与 XGBoost 预测模型...")
model_h_lgb = joblib.load('epl_v31_home_goals_model_lgb.pkl')
model_a_lgb = joblib.load('epl_v31_away_goals_model_lgb.pkl')
model_h_xgb = joblib.load('epl_v31_home_goals_model_xgb.pkl')
model_a_xgb = joblib.load('epl_v31_away_goals_model_xgb.pkl')

jczq_picks_list = []
prediction_logs = [] 
html_report_cards = ""
img_buffers = []

# ================= 核心预测循环 =================
print("🚀 开始执行智能预测决策流...")
for league in df_next_round['联赛'].unique():
    html_report_cards += f"""<div style="background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 10px 20px; border-radius: 8px; margin-top: 30px; margin-bottom: 20px;"><h2 style="margin: 0; font-size: 22px;">🏆 {league}</h2></div>"""
    
    for _, match in df_next_round[df_next_round['联赛'] == league].iterrows():
        h_cn, a_cn = match['主队'], match['客队']
        match_date_str = match['match_date_str']
        m_time = pd.to_datetime(match['datetime_parsed']).strftime('%m月%d日 %H:%M')
        m_date = pd.to_datetime(match['datetime_parsed']).date()
        
        h_count = team_stats.get(h_cn, {'count': 0})['count']
        a_count = team_stats.get(a_cn, {'count': 0})['count']
        
        # 🚨 铁血纪律一：历史数据不足，直接拦截
        if h_count < 3 or a_count < 3:
            print(f"⚠️ 拦截比赛：{h_cn} vs {a_cn}，历史数据不足。")
            html_report_cards += f"""
            <div style="border: 2px dashed #e74c3c; border-radius: 10px; padding: 20px; margin-bottom: 25px; background-color: #fdf2f2;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: #c0392b; font-size: 18px;">⏰ {m_time} <span style="color: #000; margin-left: 10px; font-size: 20px;">{h_cn} vs {a_cn}</span></h3>
                    <span style="background-color: #e74c3c; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px;">数据拦截</span>
                </div>
                <p style="color: #c0392b; font-size: 14px; margin-top: 15px; font-weight: bold;">
                    ❌ 已拦截：该球队在历史数据库中的真实场次不足 (主队:{h_count}场, 客队:{a_count}场)。<br>
                    系统已严格执行客观纪律，拒绝使用假数据污染模型。
                </p>
            </div>
            """
            continue
            
        # 🚨 铁血纪律二：赔率获取与优先级（手动 > 自动）
        manual_row = manual_odds_dict.get((match_date_str, h_cn, a_cn))
        auto_row = real_odds_dict.get((match_date_str, h_cn, a_cn))
        use_odds = manual_row if manual_row is not None else auto_row
        odds_source = "手动体彩盘" if manual_row is not None else ("自动海外盘" if auto_row is not None else "无赔率")
        
        has_real = False
        if use_odds is not None:
            try:
                real_h, real_d, real_a = float(use_odds['主胜赔率']), float(use_odds['平局赔率']), float(use_odds['客胜赔率'])
                hc_line, hc_h_odd, hc_a_odd = float(use_odds.get('让球盘口', 0.0)), float(use_odds.get('主让胜赔率', 0.0)), float(use_odds.get('客受让胜赔率', 0.0))
                tl_line, over_odd, under_odd = float(use_odds.get('大小球盘口', 2.5)), float(use_odds.get('大球赔率', 0.0)), float(use_odds.get('小球赔率', 0.0))
                has_real = True
            except:
                real_h, real_d, real_a = 0.0, 0.0, 0.0
                hc_line, hc_h_odd, hc_a_odd = 0.0, 0.0, 0.0
                tl_line, over_odd, under_odd = 2.5, 0.0, 0.0
        else:
            real_h, real_d, real_a = 0.0, 0.0, 0.0
            hc_line, hc_h_odd, hc_a_odd = 0.0, 0.0, 0.0
            tl_line, over_odd, under_odd = 2.5, 0.0, 0.0

        # 🧠 核心：特征工程构建（融合多维度数据）
        h = team_stats.get(h_cn, {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]})
        a = team_stats.get(a_cn, {'xg':[], 'xga':[], 'home_xg':[], 'home_xga':[], 'away_xg':[], 'away_xga':[], 'opp_elo':[], 'pts':[], 'dates':[]})
        
        # 计算休息天数差（体能因素）
        h_rest = (pd.Timestamp(m_date) - last_date[h_cn]).days if h_cn in last_date else 7
        a_rest = (pd.Timestamp(m_date) - last_date[a_cn]).days if a_cn in last_date else 7
        rest_diff = h_rest - a_rest
        
        # 计算赛程密集度（14天内比赛场次）
        h_recent_matches = sum(1 for d in h['dates'] if (pd.Timestamp(m_date) - d).days <= 14)
        a_recent_matches = sum(1 for d in a['dates'] if (pd.Timestamp(m_date) - d).days <= 14)
        
        # 核心进攻/防守数据
        h_xg = np.mean(h['xg'][-5:]) if h['xg'] else league_avg_goals
        a_xg = np.mean(a['xg'][-5:]) if a['xg'] else league_avg_goals
        h_xga = np.mean(h['xga'][-5:]) if h['xga'] else league_avg_goals
        a_xga = np.mean(a['xga'][-5:]) if a['xga'] else league_avg_goals
        
        # 主客场专项数据（非常重要）
        h_home_xg = np.mean(h['home_xg'][-3:]) if h['home_xg'] else h_xg
        h_home_xga = np.mean(h['home_xga'][-3:]) if h['home_xga'] else h_xga
        a_away_xg = np.mean(a['away_xg'][-3:]) if a['away_xg'] else a_xg
        a_away_xga = np.mean(a['away_xga'][-3:]) if a['away_xga'] else a_xga
        
        # 对手强度与 Elo
        h_sos = np.mean(h['opp_elo'][-5:]) if h['opp_elo'] else 1500
        a_sos = np.mean(a['opp_elo'][-5:]) if a['opp_elo'] else 1500
        h_elo = elo_dict.get(h_cn, 1500)
        a_elo = elo_dict.get(a_cn, 1500)
        
        # 构造完整的 16 维特征向量喂给模型
        feat = [
            h_elo, a_elo, h_elo - a_elo, 
            h_sos, a_sos, h_xg, a_xg, h_xga, a_xga, 
            h_home_xg, h_home_xga, a_away_xg, a_away_xga, 
            rest_diff, h_recent_matches, a_recent_matches
        ]
        feat = np.clip(np.nan_to_num(feat, nan=0.0), -1000, 3000).reshape(1, -1)
        
        # 机器学习模型预测基础 xG
        pred_h_xg = max(0.1, (model_h_lgb.predict(feat)[0] + model_h_xgb.predict(feat)[0]) / 2.0)
        pred_a_xg = max(0.1, (model_a_lgb.predict(feat)[0] + model_a_xgb.predict(feat)[0]) / 2.0)
        
        # 伤病惩罚权重
        h_att_penalty = 1 - injury_impact_att.get(h_cn, 0)
        h_def_penalty = 1 - injury_impact_def.get(h_cn, 0)
        a_att_penalty = 1 - injury_impact_att.get(a_cn, 0)
        a_def_penalty = 1 - injury_impact_def.get(a_cn, 0)
        
        # 最终 xG 修正（引入对手防守漏洞）
        home_xg = pred_h_xg * max(0.5, h_att_penalty) + (pred_a_xg * (1 - max(0.5, a_def_penalty)) * 0.2)
        away_xg = pred_a_xg * max(0.5, a_att_penalty) + (pred_h_xg * (1 - max(0.5, h_def_penalty)) * 0.2)
        
        # 天气因素影响
        w_text, w_temp = get_match_weather(h_cn, match_date_str)
        if "雨" in w_text or "雪" in w_text:
            home_xg *= 0.9
            away_xg *= 0.9

        # 生成比分矩阵
        scores_list, prob_matrix = generate_score_matrix(home_xg, away_xg, max_goals=8)
        
        # 计算胜平负基础概率
        p_h, p_d, p_a = np.sum(np.tril(prob_matrix, -1)), np.sum(np.diag(prob_matrix)), np.sum(np.triu(prob_matrix, 1))
        total_p = p_h + p_d + p_a
        p_h, p_d, p_a = p_h/total_p, p_d/total_p, p_a/total_p
        
        ref_info = ref_dict.get((h_cn, a_cn), {'name': '未公布'})
        h_inj_str = ','.join(injury_dict.get(h_cn, ['无']))
        a_inj_str = ','.join(injury_dict.get(a_cn, ['无']))
        injury_info = f"主队伤停: {h_inj_str}; 客队伤停: {a_inj_str}"
        
        # 风控总监微调概率
        odds_trend = "暂无盘口轨迹数据"
        p_h, p_d, p_a, ai_reason = ai_adjust_probabilities(h_cn, a_cn, p_h, p_d, p_a, injury_info, odds_trend, knowledge_base, ref_info)
        
        # 伪数据筛查
        trap_warning = risk_agent_odds_trap(p_h, p_d, p_a, real_h, real_d, real_a) if has_real else ""
        
        # 判定最终倾向
        predict_choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")
        
        # 平局熔断机制
        expected_total_goals = home_xg + away_xg
        if predict_choice == "平局" and expected_total_goals > 2.8:
            predict_choice = "主胜" if h_elo > a_elo else "客胜"
            ai_reason = "⚠️ 触发平局熔断：双方进攻预期较高，平局概率不可靠，强制修正方向。" + ai_reason

        oh, od, oa = (real_h, real_d, real_a) if has_real else (2.0, 3.3, 3.5)
        
        # 资金管理与推荐逻辑
        final_rec, bet_amt, split_msg = "观望", 0.0, ""
        ou_msg, hc_msg, ou_rec, hc_rec = "未开出", "未开出", "观望", "观望"
        
        if has_real and "异常" not in trap_warning:
            # 凯利公式计算
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od-1)/(od-1), (p_a*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            if max_k > 0.02:
                b_choice = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                # 严格阈值，概率低于 25% 绝不推荐
                if (b_choice == "主胜" and p_h > 0.25) or (b_choice == "平局" and p_d > 0.25) or (b_choice == "客胜" and p_a > 0.25):
                    safe_k = min(max_k * kelly_multiplier, 0.05)
                    bet_amt, final_rec = bankroll * safe_k, b_choice
                    split_msg = f"推荐下注 {bet_amt:.2f}元"
                else: 
                    split_msg = "概率不足，空仓观望"
            else: 
                split_msg = "无正期望价值"

            # 大小球分析
            if pd.notna(tl_line) and tl_line > 0:
                prob_over = sum(prob_matrix[i][j] for i in range(9) for j in range(9) if i + j > tl_line)
                ou_msg = f"盘口{tl_line}，大球{prob_over*100:.1f}% / 小球{(1-prob_over)*100:.1f}%"
                if prob_over * over_odd > 1.05: 
                    ou_rec = "大球 (高价值)"
                elif (1-prob_over) * under_odd > 1.05: 
                    ou_rec = "小球 (高价值)"
                
            # 亚盘分析
            if pd.notna(hc_line) and hc_line != 0:
                prob_hc_home = sum(prob_matrix[i][j] for i in range(9) for j in range(9) if i + hc_line > j)
                hc_msg = f"主让{hc_line}，主赢盘{prob_hc_home*100:.1f}% / 客赢盘{(1-prob_hc_home)*100:.1f}%"
                if prob_hc_home * hc_h_odd > 1.05: 
                    hc_rec = "主队赢盘"
                elif (1-prob_hc_home) * hc_a_odd > 1.05: 
                    hc_rec = "客队赢盘"
        else:
            final_rec = f"技术倾向：{predict_choice}"
            bet_amt = 0.0
            split_msg = "(无真实盘口，不提供价值推荐)"

        # 比分提取与防冷扩充
        valid_scores = [s for s in scores_list if s[1] > 0.012]
        top3 = valid_scores[:3]
        if abs(h_elo - a_elo) > 100 and not any(int(s[0].split('-')[0]) >= 3 or int(s[0].split('-')[1]) >= 3 for s in top3):
            high_var_scores = [s for s in valid_scores if int(s[0].split('-')[0]) >= 3 or int(s[0].split('-')[1]) >= 3]
            if high_var_scores: 
                top3[2] = high_var_scores[0]
        
        top3_str = " | ".join([f"<b>{s[0]}</b> ({s[1]*100:.1f}%)" for s in top3])
        best_score = top3[0][0]

        total_goals_rec_str, _ = get_total_goals_recommendation(prob_matrix)

        # 组装狙击清单（Part 1）
        if has_real and (bet_amt > 0 or "高价值" in ou_rec or "高价值" in hc_rec):
            jczq_picks_list.append({
                '比赛时间': m_time, '赛事': league, '对阵': f"{h_cn} vs {a_cn}",
                '推荐': final_rec if bet_amt > 0 else "观望", '金额': round(bet_amt, 2) if bet_amt > 0 else 0,
                '比分': best_score, '总进球': total_goals_rec_str, '让球': hc_rec, '大小球': ou_rec
            })

        venue = f"{h_cn}主场" 

        # 球探情报
        scout_intel = scout_agent_intel(h_cn, a_cn, league, knowledge_base)
        
        # AI 专家综合点评
        prompt = f"""资深专家，请对以下比赛输出180字内的深度点评。
        比赛：{h_cn} vs {a_cn}（{league}）。
        数学模型倾向：{predict_choice}，首选比分：{best_score}。
        【球探情报】：{scout_intel}
        【伤停情报】：{injury_info}
        【风控提示】：{trap_warning if trap_warning else '无异常'}
        请结合数据与情报，客观指出比赛隐患和防守重点。以“推荐关注：{final_rec}”结尾。"""
        try: 
            ai_comment = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False).choices[0].message.content.strip()
        except: 
            ai_comment = "AI解析失败"

        # 生成双轴图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))
        fig.patch.set_facecolor('#f8f9fa')
        
        labels = ['主胜', '平局', '客胜']
        probs = [p_h*100, p_d*100, p_a*100]
        colors = ['#4e79a7', '#f28e2b', '#e15759']
        bars = ax1.bar(labels, probs, color=colors, width=0.5, edgecolor='white', linewidth=1)
        ax1.set_ylim(0, 100)
        ax1.set_title(f"{h_cn} vs {a_cn} - 赛果概率", fontsize=12, fontweight='bold', color='#333')
        for bar in bars:
            yval = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2, yval + 2, f'{yval:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
        ax1.tick_params(axis='both', labelsize=10)
        
        ax2.barh(['客队', '主队'], [away_xg, home_xg], color=['#59a14f', '#e15759'], height=0.4)
        ax2.set_xlim(0, max(home_xg, away_xg) + 1)
        ax2.set_title("预期进球 (xG)", fontsize=12, fontweight='bold', color='#333')
        ax2.text(home_xg + 0.1, 1, f'{home_xg:.2f}', va='center', fontsize=11, fontweight='bold')
        ax2.text(away_xg + 0.1, 0, f'{away_xg:.2f}', va='center', fontsize=11, fontweight='bold')
        ax2.tick_params(axis='both', labelsize=10)

        plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); img_buffers.append(buf); plt.close(fig)

        # 记录日志，用于次日复盘和自我学习
        prediction_logs.append({
            'date': m_date.strftime('%Y-%m-%d'), 'league': league, 'home_team': h_cn, 'away_team': a_cn,
            'predicted_result': final_rec, 'bet_amount': round(bet_amt, 2),
            'pred_prob_h': round(p_h, 4), 'pred_prob_d': round(p_d, 4), 'pred_prob_a': round(p_a, 4),
            'predicted_score': best_score, 'top3_scores': top3_str.replace("<b>", "").replace("</b>", ""),
            'odds_h': oh, 'odds_d': od, 'odds_a': oa, 'home_injuries': h_inj_str, 'away_injuries': a_inj_str
        })

        # 组装 HTML 卡片（Part 2）
        html_report_cards += f"""
        <div style="border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 25px; background-color: #ffffff; box-shadow: 0 4px 10px rgba(0,0,0,0.06);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; margin-bottom: 15px;">
                <h3 style="margin: 0; color: #2c3e50; font-size: 18px;">⏰ {m_time} <span style="color: #000; margin-left: 10px; font-size: 20px;">{h_cn} vs {a_cn}</span></h3>
                <span style="background-color: #e8f4fd; color: #1e3c72; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px;">{venue}</span>
            </div>
            
            <img src='cid:chart_{len(img_buffers)-1}' width='100%' style='border-radius: 6px; margin-bottom: 15px;'>

            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <div style="flex: 1; background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; border-radius: 4px;">
                    <span style="font-size: 13px; color: #856404; font-weight: bold; display: block; margin-bottom: 5px;">🎯 首选比分</span>
                    <span style="font-size: 22px; color: #d9534f; font-weight: bold;">{best_score}</span>
                    <span style="font-size: 12px; color: #666; margin-left: 8px;">防冷: {top3_str}</span>
                </div>
                <div style="flex: 1; background-color: #e8f4fd; border-left: 4px solid #3498db; padding: 10px; border-radius: 4px;">
                    <span style="font-size: 13px; color: #2980b9; font-weight: bold; display: block; margin-bottom: 5px;">⚽ 总进球数</span>
                    <span style="font-size: 20px; color: #1e3c72; font-weight: bold;">{total_goals_rec_str}</span>
                </div>
            </div>

            {f"<div style='background-color: #f8d7da; color: #721c24; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; font-weight: bold;'>{trap_warning}</div>" if "异常" in trap_warning else ""}
            {f"<div style='background-color: #e8f4fd; color: #1e3c72; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 13px;'><b>🔍 球探情报：</b>{scout_intel}</div>" if scout_intel else ""}

            <div style="display: flex; flex-wrap: wrap; font-size: 13px; line-height: 1.8; color: #444; margin-bottom: 12px; background-color: #f8f9fa; padding: 10px; border-radius: 6px;">
                <div style="width: 50%;">💪 <b>Elo:</b> 主 {h_elo:.0f} / 客 {a_elo:.0f}</div>
                <div style="width: 50%;">🌤️ <b>天气:</b> {w_text} {w_temp}℃</div>
                <div style="width: 50%;">⏱️ <b>休息:</b> 主 {h_rest} 天 / 客 {a_rest} 天</div>
                <div style="width: 50%;">🧑‍⚖️ <b>裁判:</b> {ref_info['name']}</div>
                <div style="width: 100%; color: #d9534f; margin-top: 5px;"><b>🚨 伤停:</b> 主[{h_inj_str}] / 客[{a_inj_str}]</div>
            </div>

            <div style="display: flex; justify-content: space-around; text-align: center; font-size: 13px; margin-bottom: 15px;">
                <div><span style="color: #666;">亚盘</span> <b style="color: #1e3c72;">{hc_rec} ({hc_msg})</b></div>
                <div><span style="color: #666;">大小球</span> <b style="color: #1e3c72;">{ou_rec} ({ou_msg})</b></div>
            </div>

            <div style="padding: 12px; border: 1px dashed #ccc; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; background-color: #fafafa;">
                <div>
                    <span style="font-size: 15px;"><b>💡 预测结果：</b><span style="font-size: 22px; color: #d9534f; font-weight: bold; margin-right: 10px;">{predict_choice}</span></span>
                </div>
            </div>

            <p style="margin-top: 15px; margin-bottom: 0; color: #555; font-size: 13px; line-height: 1.6;"><b>🧠 专家联合点评：</b>{ai_comment}</p>
        </div>
        """

# 组装最终邮件内容
final_html = """
<html>
<head>
<style>
    body { font-family: 'Helvetica Neue', Helvetica, Arial, 'Microsoft YaHei', sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; }
    .container { max-width: 900px; margin: auto; }
    .header { text-align: center; margin-bottom: 30px; }
    .header h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; font-size: 28px; margin: 0; }
    .report-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden; }
    .report-table th { background-color: #2c3e50; color: #ffffff; font-weight: bold; padding: 12px 10px; text-align: center; border-bottom: 2px solid #1a252f; }
    .report-table td { padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: center; color: #333; }
    .report-table tr:nth-child(even) { background-color: #f8f9fa; }
    .report-table tr:hover { background-color: #e8f4fd; }
    .section-title { text-align: center; color: #d35400; font-size: 20px; margin-top: 0; margin-bottom: 10px; border-bottom: 2px solid #f39c12; display: inline-block; padding-bottom: 5px; }
</style>
</head>
<body>
<div class="container">
"""

final_html += "<h1>⚽ 今日竞彩全景预测与狙击清单 (V61.0 旗舰版)</h1>"

final_html += "<h2 style='color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 10px;'>🎯 Part 1: 今日竞彩狙击清单 (价值投资)</h2>"
if jczq_picks_list:
    df_picks = pd.DataFrame(jczq_picks_list)
    df_picks.to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')
    picks_html = df_picks.to_html(index=False, border=0, classes='report-table', justify='center', escape=False)
    final_html += f"""
    <div style='background-color: #fff; padding: 20px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); border-top: 5px solid #f39c12;'>
        {picks_html}
    </div>
    """
else:
    final_html += """
    <div style='background-color: #fdf2f2; border-top: 5px solid #e74c3c; padding: 20px; border-radius: 10px; margin-bottom: 30px; text-align: center; box-shadow: 0 4px 10px rgba(0,0,0,0.05);'>
        <h3 style='color: #c0392b; margin-top: 0; font-size: 20px;'>🛑 今日无高价值狙击目标</h3>
        <p style='color: #c0392b; font-size: 14px;'>系统严格执行纪律：因无真实赔率或期望价值不足，拒绝强行出单，建议空仓观望。</p>
    </div>
    """
    pd.DataFrame(columns=['比赛时间', '赛事', '对阵', '推荐', '金额', '比分', '总进球', '让球', '大小球']).to_csv('daily_jczq_picks.csv', index=False, encoding='utf-8-sig')

final_html += "<h2 style='color: #2980b9; border-bottom: 2px solid #2980b9; padding-bottom: 10px; margin-top: 40px;'>📊 Part 2: 今日全部比赛全景预测分析</h2>"
final_html += html_report_cards

final_html += "</div></body></html>"

log_df = pd.DataFrame(prediction_logs)
if not log_df.empty:
    if os.path.exists('predictions_log.csv'):
        old = pd.read_csv('predictions_log.csv')
        log_df = pd.concat([old, log_df]).drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
    log_df.to_csv('predictions_log.csv', index=False, encoding='utf-8-sig')

open('dashboard.html', 'w', encoding='utf-8').write(final_html)
send_rich_email("⚽ 今日竞彩全景预测与狙击清单 (V61.0 旗舰版)", final_html, img_buffers)
