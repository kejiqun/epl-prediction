import pandas as pd
import numpy as np
import requests
import joblib
import os
import io
import json
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
from scipy.stats import poisson
from team_mapping import translate_team_name
from itertools import combinations

warnings.filterwarnings('ignore')
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("==================================================")
print("🚀 启动 V350.0 终极纠错版 (严丝合缝 16 维)")
print("==================================================")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

# ================= 1. 玄学美学展示模块 =================
def get_wuxing_theme():
    base_date = datetime(1900, 1, 31)
    today = datetime.now()
    days_diff = (today - base_date).days
    
    tiangan = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
    dizhi = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
    gan_idx = days_diff % 10
    zhi_idx = days_diff % 12
    day_ganzhi = tiangan[gan_idx] + dizhi[zhi_idx]
    
    wuxing_map = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土', '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
    element = wuxing_map[tiangan[gan_idx]]
    
    themes = {
        '木': {'bg': '#f0f7f4', 'primary': '#2e7d32', 'grad1': '#1b5e20', 'grad2': '#4caf50', 'icon': '🌳'},
        '火': {'bg': '#fdf5f5', 'primary': '#c62828', 'grad1': '#b71c1c', 'grad2': '#ef5350', 'icon': '🔥'},
        '土': {'bg': '#faf8f5', 'primary': '#e65100', 'grad1': '#bf360c', 'grad2': '#ff9800', 'icon': '⛰️'},
        '金': {'bg': '#f8f9fa', 'primary': '#c0a060', 'grad1': '#8d6e63', 'grad2': '#d4af37', 'icon': '⚔️'},
        '水': {'bg': '#f0f4f8', 'primary': '#1565c0', 'grad1': '#0d47a1', 'grad2': '#42a5f5', 'icon': '🌊'}
    }
    return day_ganzhi, element, themes[element]

DAY_GANZHI, ELEMENT, THEME = get_wuxing_theme()
print(f"🌙 今日玄学匹配: {DAY_GANZHI}日 ({ELEMENT}属性)")

# ================= 2. 鲁棒性工具 =================
def send_email(subject, html, imgs, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: 
        print("⚠️ 缺少邮箱配置，跳过发送。")
        return
    msg = MIMEMultipart('related')
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, receiver, Header(subject, 'utf-8')
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    for i, buf in enumerate(imgs):
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

def safe_request(url, timeout=8):
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200: 
            return resp.json()
    except: 
        pass
    return None

def get_weather(team, date_str):
    city_map = {'阿森纳': 'London', '曼联': 'Manchester', '利物浦': 'Liverpool', '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '拜仁慕尼黑': 'Munich', '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin', '那不勒斯': 'Naples', '蒙扎': 'Monza'}
    cache_file = 'team_city_cache.json'
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if team in cache: 
                    city_map[team] = cache[team]
        except: 
            pass
    city = city_map.get(team, 'London')
    data = safe_request(f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh")
    if data and 'forecast' in data:
        day = data['forecast']['forecastday'][0]['day']
        return day['condition']['text'], round(day['avgtemp_c'], 1)
    return "未知", 0

# ================= 3. 绝对科学内核：动态 Dixon-Coles 解析解 =================
def generate_dynamic_score_matrix(home_xg, away_xg, h_def_strength, a_def_strength, max_goals=8):
    defense_avg = (h_def_strength + a_def_strength) / 2.0
    if defense_avg > 0.7:
        rho = -0.25 
    elif defense_avg < 0.4:
        rho = -0.05 
    else:
        rho = -0.15

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
    return scores, matrix, rho

def get_total_goals(matrix, max_goals=8):
    totals = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            total = h + a
            totals[total] = totals.get(total, 0) + matrix[h][a]
    sorted_goals = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    top2 = [f"{k}球" for k, v in sorted_goals[:2] if k <= 7]
    prob_over = sum(p for g, p in totals.items() if g > 2.5)
    return " / ".join(top2), prob_over

# ================= 4. 数据装载与特征处理 =================
bankroll, base_kelly = 10000.0, 0.2
if os.path.exists('bankroll.csv'):
    try:
        df_bank = pd.read_csv('bankroll.csv')
        bankroll = df_bank.iloc[-1]['当前资金']
        win_rate = len(df_bank.tail(10)[df_bank.tail(10)['盈亏'] > 0]) / 10
        if win_rate < 0.4: base_kelly = 0.1 
        elif win_rate > 0.6: base_kelly = 0.3
    except: pass

if not os.path.exists('all_leagues_matches.csv'): exit()

# 1. 自动抓取赛程
df_auto = pd.DataFrame()
if os.path.exists('daily_matches.csv'):
    try:
        df_auto = pd.read_csv('daily_matches.csv')
        df_auto['主队'] = df_auto['主队'].apply(translate_team_name)
        df_auto['客队'] = df_auto['客队'].apply(translate_team_name)
        df_auto['datetime_parsed'] = pd.to_datetime(df_auto['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    except Exception as e: print(f"⚠️ 自动赛程读取异常: {e}")

# 2. 手动填入数据
manual_odds, df_manual = {}, pd.DataFrame()
if os.path.exists('manual_odds.csv'):
    try:
        raw = pd.read_csv('manual_odds.csv')
        raw['datetime_parsed'] = pd.to_datetime(raw['比赛日期'].astype(str).str.strip() + ' ' + raw['比赛时间'].astype(str).str.strip())
        raw['主队'] = raw['主队'].apply(translate_team_name)
        raw['客队'] = raw['客队'].apply(translate_team_name)
        for _, r in raw.iterrows():
            manual_odds[(r['datetime_parsed'].strftime('%Y-%m-%d'), r['主队'], r['客队'])] = r
        df_manual = raw.copy()
        df_manual['联赛'] = '手动精选'
        df_manual['比赛时间'] = df_manual['datetime_parsed']
    except Exception as e: print(f"⚠️ 手动赔率读取异常: {e}")

# 3. 自动抓取海外赔率
real_odds = {}
if os.path.exists('real_odds.csv'):
    try:
        for _, r in pd.read_csv('real_odds.csv').iterrows():
            real_odds[(pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d'), translate_team_name(r['主队']), translate_team_name(r['客队']))] = r
    except: pass

df_next = pd.concat([df_auto, df_manual]).drop_duplicates(subset=['主队', '客队', 'datetime_parsed'], keep='last')
now, end = pd.Timestamp.now(), pd.Timestamp.now() + pd.Timedelta(hours=24)
df_next = df_next[(df_next['datetime_parsed'] > now) & (df_next['datetime_parsed'] <= end)].sort_values('datetime_parsed')
if df_next.empty: exit()

# 历史特征提取
df_hist = pd.read_csv('all_leagues_matches.csv')
df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist['h_cn'] = df_hist['home_team'].apply(translate_team_name)
df_hist['a_cn'] = df_hist['away_team'].apply(translate_team_name)
df_hist = df_hist.sort_values('date')
avg_goals = (df_hist['home_goals'].mean() + df_hist['away_goals'].mean()) / 2

stats, last_date = {}, {}
for _, r in df_hist.iterrows():
    h, a, d = r['h_cn'], r['a_cn'], r['date']
    for t in [h, a]:
        if t not in stats: 
            stats[t] = {'xg':[], 'xga':[], 'h_xg':[], 'h_xga':[], 'a_xg':[], 'a_xga':[], 'dates':[], 'count':0, 'clean_sheets':0}
        if t not in last_date: last_date[t] = None
            
    stats[h]['count'] += 1; stats[a]['count'] += 1
    if r['away_goals'] == 0: stats[h]['clean_sheets'] += 1
    if r['home_goals'] == 0: stats[a]['clean_sheets'] += 1

    stats[h]['xg'].append(r['home_goals']); stats[h]['xga'].append(r['away_goals'])
    stats[a]['xg'].append(r['away_goals']); stats[a]['xga'].append(r['home_goals'])
    stats[h]['h_xg'].append(r['home_goals']); stats[h]['h_xga'].append(r['away_goals'])
    stats[a]['a_xg'].append(r['away_goals']); stats[a]['a_xga'].append(r['home_goals'])
    stats[h]['dates'].append(d); stats[a]['dates'].append(d)
    last_date[h], last_date[a] = d, d

def decay_mean(arr, decay=0.7):
    if not arr: return avg_goals
    a = np.array(arr)
    w = np.array([decay ** (len(a) - 1 - i) for i in range(len(a))])
    return np.sum(a * (w / np.sum(w)))

m_hl = joblib.load('epl_v31_home_goals_model_lgb.pkl')
m_al = joblib.load('epl_v31_away_goals_model_lgb.pkl')
m_hx = joblib.load('epl_v31_home_goals_model_xgb.pkl')
m_ax = joblib.load('epl_v31_away_goals_model_xgb.pkl')
elo = joblib.load('elo_dict.pkl') if os.path.exists('elo_dict.pkl') else {}

picks, logs, html_cards, imgs = [], [], "", []
parlay_pool = []

# ================= 5. 主循环 =================
for league in df_next['联赛'].unique():
    html_cards += f"<div style='background:linear-gradient(90deg,{THEME['grad1']},{THEME['grad2']});color:#fff;padding:12px 20px;border-radius:8px;margin-top:35px;margin-bottom:25px;'><h2 style='margin:0;'>{league}</h2></div>"
    
    for _, m in df_next[df_next['联赛'] == league].iterrows():
        h, a = m['主队'], m['客队']
        date_str = m['datetime_parsed'].strftime('%Y-%m-%d')
        time_str = m['datetime_parsed'].strftime('%m月%d日 %H:%M')
        
        if stats.get(h, {'count':0})['count'] < 3 or stats.get(a, {'count':0})['count'] < 3: continue
        
        od_manual = manual_odds.get((date_str, h, a))
        od_auto = real_odds.get((date_str, h, a))
        od = od_manual if od_manual is not None else od_auto
        
        has_odds, src = False, "无赔率"
        if od is not None:
            try:
                oh, od_, oa = float(od['主胜赔率']), float(od['平局赔率']), float(od['客胜赔率'])
                tl, over_odd, under_odd = float(od.get('大小球盘口', 2.5)), float(od.get('大球赔率', 0)), float(od.get('小球赔率', 0))
                has_odds = True
                src = "手动体彩盘" if od_manual is not None else "自动海外盘(参考)"
            except: pass
            
        hs, as_ = stats.get(h, {}), stats.get(a, {})
        h_rest = (pd.Timestamp(m['datetime_parsed']).date() - last_date[h].date()).days if h in last_date else 7
        a_rest = (pd.Timestamp(m['datetime_parsed']).date() - last_date[a].date()).days if a in last_date else 7
        
        # 🌟 严格恢复为 16 维特征 (模型要求的维度)
        feat = np.array([
            elo.get(h,1500), elo.get(a,1500), elo.get(h,1500)-elo.get(a,1500), 1500, 1500,
            decay_mean(hs.get('xg',[])[-5:]), decay_mean(as_.get('xg',[])[-5:]),
            decay_mean(hs.get('xga',[])[-5:]), decay_mean(as_.get('xga',[])[-5:]),
            np.mean(hs.get('h_xg',[])[-3:]) if hs.get('h_xg') else decay_mean(hs.get('xg',[])[-5:]),
            np.mean(hs.get('h_xga',[])[-3:]) if hs.get('h_xga') else decay_mean(hs.get('xga',[])[-5:]),
            np.mean(as_.get('a_xg',[])[-3:]) if as_.get('a_xg') else decay_mean(as_.get('xg',[])[-5:]),
            np.mean(as_.get('a_xga',[])[-3:]) if as_.get('a_xga') else decay_mean(as_.get('xga',[])[-5:]),
            h_rest - a_rest,
            sum(1 for d in hs.get('dates',[]) if (pd.Timestamp(m['datetime_parsed']) - d).days <= 14),
            sum(1 for d in as_.get('dates',[]) if (pd.Timestamp(m['datetime_parsed']) - d).days <= 14)
        ]).clip(-1000, 3000).reshape(1, -1)
        
        ph_l, ph_x = m_hl.predict(feat)[0], m_hx.predict(feat)[0]
        pa_l, pa_x = m_al.predict(feat)[0], m_ax.predict(feat)[0]
        
        penalty = 1.0
        warn_c = ""
        if abs(ph_l - ph_x) > 0.4 or abs(pa_l - pa_x) > 0.4:
            penalty = 0.8
            warn_c = "⚠️ 模型分歧度过高，已强制削减置信度。"
            
        home_xg = max(0.1, (ph_l + ph_x)/2 * penalty)
        away_xg = max(0.1, (pa_l + pa_x)/2 * penalty)
        
        if has_odds and tl > 0 and abs((home_xg+away_xg) - tl) > 1.0:
            s = tl / (home_xg + away_xg)
            home_xg *= s; away_xg *= s

        h_def_str = hs.get('clean_sheets', 0) / hs.get('count', 1)
        a_def_str = as_.get('clean_sheets', 0) / as_.get('count', 1)

        sc_probs, matrix, dynamic_rho = generate_dynamic_score_matrix(home_xg, away_xg, h_def_str, a_def_str)
        p_h = np.sum(np.tril(matrix, -1))
        p_d = np.sum(np.diag(matrix))
        p_a = np.sum(np.triu(matrix, 1))
        
        final_rec, bet_amt, ou_rec = "观望", 0.0, "观望"
        choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")
        tg_str, prob_over = get_total_goals(matrix, 8)
        
        if has_odds:
            margin = 1/oh + 1/od_ + 1/oa
            ih, id_, ia = (1/oh)/margin, (1/od_)/margin, (1/oa)/margin
            p_h = p_h * 0.6 + ih * 0.4
            p_d = p_d * 0.6 + id_ * 0.4
            p_a = p_a * 0.6 + ia * 0.4
            total_p = p_h + p_d + p_a
            p_h, p_d, p_a = p_h/total_p, p_d/total_p, p_a/total_p
            
            choice = "主胜" if p_h > max(p_d, p_a) else ("平局" if p_d > max(p_h, p_a) else "客胜")
            
            kh, kd, ka = (p_h*oh-1)/(oh-1), (p_d*od_-1)/(od_-1), (p_a*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            
            if max_k > 0.02:
                bet_rec = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (bet_rec=="主胜" and p_h>0.25) or (bet_rec=="平局" and p_d>0.25) or (bet_rec=="客胜" and p_a>0.25):
                    dynamic_kelly = base_kelly * (1 + max_k)
                    bet_amt = bankroll * min(dynamic_kelly, 0.05)
                    final_rec = bet_rec
                    
                    real_p = p_h if bet_rec=="主胜" else (p_d if bet_rec=="平局" else p_a)
                    real_odds_val = oh if bet_rec=="主胜" else (od_ if bet_rec=="平局" else oa)
                    parlay_pool.append({'match': f"{h} vs {a}", 'choice': bet_rec, 'prob': real_p, 'odds': real_odds_val, 'ev': real_p * real_odds_val})
            
            ou_rec = "大球" if prob_over * over_odd > 1.05 else ("小球" if (1-prob_over) * under_odd > 1.05 else "观望")
        else:
            final_rec = "无盘口观望"

        best_score = sc_probs[0][0]
        top3 = " | ".join([f"{s[0]} ({s[1]*100:.1f}%)" for s in sc_probs[:3]])

        if bet_amt > 0:
            picks.append({'时间': time_str, '赛事': league, '对阵': f"{h} vs {a}", '推荐': final_rec, '金额': round(bet_amt,2), '比分': best_score, '总进球': tg_str, '大小球': ou_rec})

        ai_txt = "无风险提示。"
        if llm_client and bet_amt > 0:
            prompt = f"比赛:{h} vs {a}。模型推荐:{final_rec}。预期进球:{home_xg:.1f} vs {away_xg:.1f}。请用60字评估此单风险。"
            try: 
                res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":prompt}], stream=False, timeout=8)
                ai_txt = res.choices[0].message.content.strip()
            except: pass

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))
        ax1.bar(['主胜', '平局', '客胜'], [p_h*100, p_d*100, p_a*100], color=[THEME['primary'], '#f28e2b', '#e15759'], width=0.5)
        ax1.set_title("融合胜率", color=THEME['primary'], fontweight='bold'); ax1.set_ylim(0,100)
        for i,v in enumerate([p_h*100,p_d*100,p_a*100]): ax1.text(i, v+2, f"{v:.1f}%", ha='center', fontweight='bold')
        ax2.barh(['客队', '主队'], [away_xg, home_xg], color=['#59a14f', THEME['primary']], height=0.4)
        ax2.set_title("基准预期进球(xG)", color=THEME['primary'], fontweight='bold')
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); imgs.append(buf); plt.close(fig)

        logs.append({'date': date_str, 'league': league, 'home': h, 'away': a, 'res': final_rec, 'bet': round(bet_amt,2), 'score': best_score})

        html_cards += f"""
        <div style="border: 1px solid #e0e0e0; border-radius: 12px; padding: 25px; margin-bottom: 25px; background: #ffffff; box-shadow: 0 6px 12px rgba(0,0,0,0.05); border-top: 4px solid {THEME['primary']};">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #f0f0f0; padding-bottom: 15px; margin-bottom: 20px;">
                <h3 style="margin: 0; color: #2c3e50; font-size: 19px; font-weight: 600;">⏰ {time_str} &nbsp;&nbsp; {h} <span style="color:{THEME['primary']}; font-size:16px; font-weight:normal;">vs</span> {a}</h3>
                <span style="background-color: {THEME['bg']}; color: {THEME['primary']}; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; border: 1px solid {THEME['primary']};">{src}</span>
            </div>
            
            <img src="cid:chart_{len(imgs)-1}" width="100%" style="margin-bottom: 20px; border-radius: 8px;">
            
            <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                <div style="flex: 1; background: #fdfbf7; border-left: 4px solid #ffc107; padding: 15px; border-radius: 6px;">
                    <span style="font-size: 13px; color: #856404; font-weight: bold; display: block; margin-bottom: 8px;">🎯 首选比分</span>
                    <span style="font-size: 24px; color: {THEME['primary']}; font-weight: bold; letter-spacing: 1px;">{best_score}</span>
                    <span style="font-size: 12px; color: #666; margin-left: 10px;">防冷: {top3}</span>
                </div>
                <div style="flex: 1; background: #f4f8fd; border-left: 4px solid {THEME['primary']}; padding: 15px; border-radius: 6px;">
                    <span style="font-size: 13px; color: {THEME['primary']}; font-weight: bold; display: block; margin-bottom: 8px;">⚽ 总进球数</span>
                    <span style="font-size: 20px; color: #1e3c72; font-weight: bold;">{tg_str}</span>
                </div>
            </div>

            <div style="background: #fff8f8; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; text-align: center; font-size: 13px; color: #555; font-weight: bold;">
                    <div>主胜概率: <span style="color:{THEME['primary']};">{p_h*100:.1f}%</span></div>
                    <div>平局概率: <span style="color:#f28e2b;">{p_d*100:.1f}%</span></div>
                    <div>客胜概率: <span style="color:#e15759;">{p_a*100:.1f}%</span></div>
                </div>
            </div>

            {f"<div style='background-color: #fff3cd; color: #856404; padding: 12px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; font-weight: bold; border-left: 3px solid #ffc107;'>{warn_c}</div>" if warn_c else ""}
            {f"<div style='background-color: #e8f4fd; color: #1e3c72; padding: 12px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; font-weight: bold; border-left: 3px solid #3498db;'>注：此场无手动体彩赔率，使用海外盘口参考，建议谨慎下注。</div>" if src == "自动海外盘(参考)" else ""}

            <div style="padding: 16px; border: 1px dashed {THEME['primary']}; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; background-color: {THEME['bg']};">
                <div>
                    <span style="font-size: 15px; color:#555;"><b>💡 预测结论：</b></span>
                    <span style="font-size: 24px; color: {THEME['primary']}; font-weight: bold; margin-right: 15px;">{choice}</span>
                    <span style="font-size: 16px; color: #d9534f; font-weight: bold;">推荐关注: {final_rec}</span>
                </div>
            </div>

            <p style="margin-top: 20px; margin-bottom: 0; color: #444; font-size: 14px; line-height: 1.7; border-top: 1px solid #eee; padding-top: 15px;"><b>⚖️ AI裁判长：</b>{ai_txt}</p>
        </div>
        """

# ================= 6. 串关算法 =================
parlay_html = "<p style='text-align:center; color:#888; padding: 20px;'>今日无明显正期望值单子，不推荐串关。</p>"
if len(parlay_pool) >= 2:
    parlay_pool = sorted(parlay_pool, key=lambda x: x['ev'], reverse=True)[:5]
    parlay_candidates = []
    for r in [2, 3]:
        for combo in combinations(parlay_pool, r):
            joint_prob = np.prod([c['prob'] for c in combo])
            joint_odds = np.prod([c['odds'] for c in combo])
            ev = joint_prob * joint_odds
            if ev > 1.15:
                parlay_candidates.append({
                    'type': f"{r}串1",
                    'matches': " + ".join([f"{c['match']}({c['choice']})" for c in combo]),
                    'odds': round(joint_odds, 2),
                    'prob': f"{joint_prob*100:.1f}%",
                    'ev': round(ev, 2)
                })
    
    if parlay_candidates:
        parlay_candidates = sorted(parlay_candidates, key=lambda x: x['ev'], reverse=True)[:3]
        df_parlay = pd.DataFrame(parlay_candidates)
        df_parlay['建议金额'] = df_parlay['ev'].apply(lambda x: round(bankroll * 0.02, 2)) 
        
        parlay_html = f"""
        <div style="background:#ffffff; padding:25px; border-radius:12px; border-top:5px solid #27ae60; box-shadow: 0 6px 12px rgba(0,0,0,0.05);">
            <p style="color:#27ae60; font-weight:bold; font-size:16px; margin-bottom:15px;">✨ 系统侦测到高期望值串关机会，利用复利法则博取高赔率：</p>
            <table style="width:100%; border-collapse:collapse; text-align:center; font-size:14px;">
                <thead>
                    <tr style="background:#27ae60; color:white;">
                        <th style="padding:12px; border:1px solid #eee;">类型</th>
                        <th style="padding:12px; border:1px solid #eee;">组合</th>
                        <th style="padding:12px; border:1px solid #eee;">赔率</th>
                        <th style="padding:12px; border:1px solid #eee;">命中率</th>
                        <th style="padding:12px; border:1px solid #eee;">EV</th>
                        <th style="padding:12px; border:1px solid #eee;">建议金额</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f"<tr style='border-bottom:1px solid #eee;'><td style='padding:12px;'>{row['type']}</td><td style='padding:12px; text-align:left;'>{row['matches']}</td><td style='padding:12px; color:#e74c3c; font-weight:bold;'>{row['odds']}</td><td style='padding:12px;'>{row['prob']}</td><td style='padding:12px; color:#27ae60; font-weight:bold;'>{row['ev']}</td><td style='padding:12px; font-weight:bold;'>{row['建议金额']}元</td></tr>" for _, row in df_parlay.iterrows()])}
                </tbody>
            </table>
        </div>
        """
    else:
        parlay_html = "<p style='text-align:center; color:#888; padding: 20px;'>今日单场EV不足，不强行组合串关。</p>"

# ================= 7. 最终组装发送 =================
if picks:
    df_picks = pd.DataFrame(picks)
    picks_rows = ""
    for _, r in df_picks.iterrows():
        picks_rows += f"<tr style='border-bottom:1px solid #f0f0f0;'><td style='padding:15px;'>{r['时间']}</td><td style='padding:15px;'>{r['赛事']}</td><td style='padding:15px; font-weight:bold;'>{r['对阵']}</td><td style='padding:15px; color:{THEME['primary']}; font-weight:bold;'>{r['推荐']}</td><td style='padding:15px; color:#d9534f; font-weight:bold;'>{r['金额']}</td><td style='padding:15px;'>{r['比分']}</td><td style='padding:15px;'>{r['总进球']}</td><td style='padding:15px;'>{r['大小球']}</td></tr>"
        
    picks_html = f"""
    <table style="width:100%; border-collapse:collapse; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px rgba(0,0,0,0.05); text-align:center; font-size:14px;">
        <thead>
            <tr style="background:linear-gradient(90deg, {THEME['grad1']}, {THEME['grad2']}); color:white;">
                <th style="padding:15px;">时间</th>
                <th style="padding:15px;">赛事</th>
                <th style="padding:15px;">对阵</th>
                <th style="padding:15px;">推荐</th>
                <th style="padding:15px;">金额</th>
                <th style="padding:15px;">比分</th>
                <th style="padding:15px;">总进球</th>
                <th style="padding:15px;">大小球</th>
            </tr>
        </thead>
        <tbody>
            {picks_rows}
        </tbody>
    </table>
    """
else:
    picks_html = f"<div style='background:#fff; border-top:5px solid {THEME['primary']}; padding:30px; border-radius:12px; text-align:center; box-shadow:0 4px 12px rgba(0,0,0,0.05);'><h3 style='color:{THEME['primary']}; margin:0; font-size:18px;'>🛑 今日无高价值单关，建议空仓。</h3></div>"

html = f"""<html><body style="font-family:'Helvetica Neue', Arial, sans-serif; padding:20px; background-color:{THEME['bg']}; color:#333;">
<div style="max-width:950px; margin:auto;">
    
    <div style="text-align:center; margin-bottom:30px;">
        <h1 style="color:{THEME['primary']}; margin:0; font-size:28px; letter-spacing:2px;">{THEME['icon']} 足球量化决策清单</h1>
        <p style="color:#666; font-size:14px; margin-top:10px; background:#fff; display:inline-block; padding:6px 15px; border-radius:20px; border:1px solid #eee;">
            农历匹配：今日干支为 <b>{DAY_GANZHI}</b> 日（属<b>{ELEMENT}</b>），运势主题已契合更换。
        </p>
    </div>

    <div style="margin-bottom:40px;">
        <h2 style="color:{THEME['primary']}; border-left:5px solid {THEME['primary']}; padding-left:12px; font-size:20px; margin-bottom:15px;">Part 1: 单关狙击清单</h2>
        {picks_html}
    </div>

    <div style="margin-bottom:40px;">
        <h2 style="color:#27ae60; border-left:5px solid #27ae60; padding-left:12px; font-size:20px; margin-bottom:15px;">Part 2: 串关复利策略 (High EV)</h2>
        {parlay_html}
    </div>

    <div>
        <h2 style="color:{THEME['primary']}; border-left:5px solid {THEME['primary']}; padding-left:12px; font-size:20px; margin-bottom:15px;">Part 3: 全景数据剖析</h2>
        {html_cards}
    </div>

</div>
</body></html>"""

if logs:
    pd.DataFrame(logs).to_csv('predictions_log.csv', mode='a', header=not os.path.exists('predictions_log.csv'), index=False, encoding='utf-8-sig')
open('dashboard.html', 'w', encoding='utf-8').write(html)
send_email(f"【{DAY_GANZHI}日·{ELEMENT}】⚽ 足球量化决策清单 (V350.0)", html, imgs)
print("🏁 运行完毕！")
