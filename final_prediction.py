import pandas as pd
import numpy as np
import requests
import joblib
import os
import io
import json
import re
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
from itertools import combinations

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("==================================================")
print("🚀 启动 V190.1 动态凯利与串关策略引擎 (修复版)")
print("==================================================")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

def safe_request(url, timeout=8):
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200: return resp.json()
    except: pass
    return None

def send_email(subject, html, imgs, receiver="308730509@qq.com"):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
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
    except Exception as e: print(f"❌ 邮件失败: {e}")

def get_weather(team, date_str):
    city = {'阿森纳': 'London', '曼联': 'Manchester', '利物浦': 'Liverpool', '皇家马德里': 'Madrid', '巴塞罗那': 'Barcelona', '拜仁慕尼黑': 'Munich', '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin'}.get(team, 'London')
    data = safe_request(f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh")
    if data and 'forecast' in data:
        day = data['forecast']['forecastday'][0]['day']
        return day['condition']['text'], round(day['avgtemp_c'], 1)
    return "未知", 0

# 🌟 核心：零膨胀时间切片引擎
def zinb_time_sliced_simulation(home_xg, away_xg, h_def_rate=0.2, a_def_rate=0.2, sims=10000):
    h_goals = np.zeros(sims, dtype=int)
    a_goals = np.zeros(sims, dtype=int)
    time_weights = np.array([0.12, 0.15, 0.18, 0.18, 0.17, 0.20]) 
    
    for i, weight in enumerate(time_weights):
        base_h = (home_xg / 6.0) * weight * 6
        base_a = (away_xg / 6.0) * weight * 6
        h_adv = (h_goals - a_goals) > 0
        a_adv = (a_goals - h_goals) > 0
        
        h_seg_xg = np.where(h_adv, base_h * 0.95, np.where(a_adv, base_h * 1.10, base_h))
        a_seg_xg = np.where(a_adv, base_a * 0.95, np.where(h_adv, base_a * 1.10, base_a))
        
        h_goals += np.random.negative_binomial(5.0, 5.0 / (5.0 + h_seg_xg))
        a_goals += np.random.negative_binomial(5.0, 5.0 / (5.0 + a_seg_xg))
        
    h_zero_mask = np.random.rand(sims) < h_def_rate
    a_zero_mask = np.random.rand(sims) < a_def_rate
    h_goals = np.where(h_zero_mask & (h_goals < 2), 0, h_goals)
    a_goals = np.where(a_zero_mask & (a_goals < 2), 0, a_goals)
    h_goals = np.clip(h_goals, 0, 10)
    a_goals = np.clip(a_goals, 0, 10)
    
    h_win = np.mean(h_goals > a_goals)
    draw = np.mean(h_goals == a_goals)
    a_win = np.mean(h_goals < a_goals)
    
    scores = h_goals * 100 + a_goals
    unique, counts = np.unique(scores, return_counts=True)
    probs = counts / sims
    score_probs = []
    for u, p in zip(unique, probs):
        h, a = u // 100, u % 100
        score_probs.append((f"{h}-{a}", p))
    score_probs.sort(key=lambda x: x[1], reverse=True)
    return h_win, draw, a_win, score_probs, h_goals, a_goals

# ================= 3. 数据装载 =================
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

df_auto = pd.DataFrame()
if os.path.exists('daily_matches.csv'):
    try:
        df_auto = pd.read_csv('daily_matches.csv')
        df_auto['主队'] = df_auto['主队'].apply(translate_team_name)
        df_auto['客队'] = df_auto['客队'].apply(translate_team_name)
        df_auto['datetime_parsed'] = pd.to_datetime(df_auto['比赛时间'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    except: pass

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
    except: pass

df_next = pd.concat([df_auto, df_manual]).drop_duplicates(subset=['主队', '客队', 'datetime_parsed'], keep='last')
now, end = pd.Timestamp.now(), pd.Timestamp.now() + pd.Timedelta(hours=24)
df_next = df_next[(df_next['datetime_parsed'] > now) & (df_next['datetime_parsed'] <= end)].sort_values('datetime_parsed')
if df_next.empty: exit()

real_odds = {}
if os.path.exists('real_odds.csv'):
    for _, r in pd.read_csv('real_odds.csv').iterrows():
        try: real_odds[(pd.to_datetime(r['比赛时间']).strftime('%Y-%m-%d'), translate_team_name(r['主队']), translate_team_name(r['客队']))] = r
        except: pass

inj_dict, att_pen, def_pen = {}, {}, {}
fpl = safe_request("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=12)
if fpl:
    try:
        t_map = {t['id']: translate_team_name(t['name']) for t in fpl['teams']}
        for e in fpl['elements']:
            if e['status'] in ['d','i','s','u'] or (e.get('chance_of_playing_next_round') or 100) < 75:
                tn = t_map.get(e['team'])
                if tn:
                    inj_dict.setdefault(tn, []).append(e['web_name'])
                    w = e.get('now_cost', 50) / 100.0
                    if e['element_type'] in [3,4]: att_pen[tn] = att_pen.get(tn, 0) + w*0.15
                    elif e['element_type'] in [1,2]: def_pen[tn] = def_pen.get(tn, 0) + w*0.15
    except: pass

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
        if t not in stats: stats[t] = {'xg':[], 'xga':[], 'h_xg':[], 'h_xga':[], 'a_xg':[], 'a_xga':[], 'dates':[], 'count':0, 'clean_sheets':0}
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

# ================= 4. 主预测流 =================
for league in df_next['联赛'].unique():
    html_cards += f"<div style='background:linear-gradient(90deg,#1e3c72,#2a5298);color:#fff;padding:10px 20px;border-radius:8px;margin-top:30px;margin-bottom:20px;'><h2 style='margin:0;'>{league}</h2></div>"
    
    for _, m in df_next[df_next['联赛'] == league].iterrows():
        h, a = m['主队'], m['客队']
        date_str = m['datetime_parsed'].strftime('%Y-%m-%d')
        time_str = m['datetime_parsed'].strftime('%m月%d日 %H:%M')
        
        if stats.get(h, {'count':0})['count'] < 3 or stats.get(a, {'count':0})['count'] < 3: continue
        
        # 🌟 核心修复：规避 Series 的真假值歧义问题
        od_manual = manual_odds.get((date_str, h, a))
        od_auto = real_odds.get((date_str, h, a))
        od = od_manual if od_manual is not None else od_auto
        
        has_odds, src = False, "无赔率"
        if od is not None:
            try:
                oh, od_, oa = float(od['主胜赔率']), float(od['平局赔率']), float(od['客胜赔率'])
                tl, over, under = float(od.get('大小球盘口', 2.5)), float(od.get('大球赔率', 0)), float(od.get('小球赔率', 0))
                has_odds = True
                src = "手动盘" if od_manual is not None else "自动盘"
            except: pass
            
        hs, as_ = stats.get(h, {}), stats.get(a, {})
        h_rest = (pd.Timestamp(m['datetime_parsed']).date() - last_date[h].date()).days if h in last_date else 7
        a_rest = (pd.Timestamp(m['datetime_parsed']).date() - last_date[a].date()).days if a in last_date else 7
        
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
            
        home_xg = max(0.1, (ph_l + ph_x)/2 * penalty) * max(0.5, 1 - att_pen.get(h,0)) + (pa_l*0.2)
        away_xg = max(0.1, (pa_l + pa_x)/2 * penalty) * max(0.5, 1 - att_pen.get(a,0)) + (ph_l*0.2)
        
        w_txt, _ = get_weather(h, date_str)
        if "雨" in w_txt or "雪" in w_txt: home_xg *= 0.9; away_xg *= 0.9

        warn_r = ""
        if has_odds and tl > 0 and abs((home_xg+away_xg) - tl) > 1.0:
            warn_r = f"⚠️ 模型xG({home_xg+away_xg:.1f})与盘口({tl})偏离大，已修正。"
            s = tl / (home_xg + away_xg)
            home_xg *= s; away_xg *= s

        h_cs_rate = hs.get('clean_sheets', 0) / hs.get('count', 1)
        a_cs_rate = as_.get('clean_sheets', 0) / as_.get('count', 1)

        ph, pd_, pa, sc_probs, h_sim, a_sim = zinb_time_sliced_simulation(
            home_xg, away_xg, h_def_rate=a_cs_rate*0.5, a_def_rate=h_cs_rate*0.5
        )
        
        warn_t, final_rec, bet = "", "观望", 0.0
        ou_rec, tg_str = "观望", ""
        
        if has_odds:
            margin = 1/oh + 1/od_ + 1/oa
            ih, id_, ia = (1/oh)/margin, (1/od_)/margin, (1/oa)/margin
            
            ph, pd_, pa = ph*0.6 + ih*0.4, pd_*0.6 + id_*0.4, pa*0.6 + ia*0.4
            ph, pd_, pa = ph/(ph+pd_+pa), pd_/(ph+pd_+pa), pa/(ph+pd_+pa)
            
            if ph - ih > 0.12: warn_t = "⚠️ 冷门警报：主胜疑似诱盘。"
            elif pa - ia > 0.12: warn_t = "⚠️ 冷门警报：客胜疑似诱盘。"
            
            choice = "主胜" if ph > max(pd_, pa) else ("平局" if pd_ > max(ph, pa) else "客胜")
            if choice == "平局" and (home_xg+away_xg) > 2.8: choice = "主胜" if elo.get(h,1500) > elo.get(a,1500) else "客胜"
            
            kh, kd, ka = (ph*oh-1)/(oh-1), (pd_*od_-1)/(od_-1), (pa*oa-1)/(oa-1)
            max_k = max(kh, kd, ka)
            
            if max_k > 0.02 and not warn_t:
                bet_rec = "主胜" if max_k == kh else ("平局" if max_k == kd else "客胜")
                if (bet_rec=="主胜" and ph>0.25) or (bet_rec=="平局" and pd_>0.25) or (bet_rec=="客胜" and pa>0.25):
                    dynamic_kelly = base_kelly * (1 + max_k) 
                    bet = bankroll * min(dynamic_kelly, 0.06) 
                    final_rec = bet_rec
                    
                    real_p = ph if bet_rec=="主胜" else (pd_ if bet_rec=="平局" else pa)
                    real_odds_val = oh if bet_rec=="主胜" else (od_ if bet_rec=="平局" else oa)
                    parlay_pool.append({
                        'match': f"{h} vs {a}", 'choice': bet_rec, 
                        'prob': real_p, 'odds': real_odds_val, 'ev': real_p * real_odds_val
                    })
                else: final_rec = "观望"
            else: final_rec = "观望"
            
            totals = h_sim + a_sim
            over_prob = np.mean(totals > tl)
            ou_rec = "大球" if over_prob*over > 1.05 else ("小球" if (1-over_prob)*under > 1.05 else "观望")
            tg_counts = pd.Series(totals).value_counts()
            tg_str = " / ".join([f"{k}球" for k in tg_counts.index[:2] if k <= 7])
        else:
            choice = "主胜" if ph > max(pd_, pa) else ("平局" if pd_ > max(ph, pa) else "客胜")
            final_rec = f"倾向:{choice}"
            totals = h_sim + a_sim
            tg_counts = pd.Series(totals).value_counts()
            tg_str = " / ".join([f"{k}球" for k in tg_counts.index[:2] if k <= 7])

        top3 = " | ".join([f"{s[0]} ({s[1]*100:.1f}%)" for s in sc_probs[:3]])
        best_sc = sc_probs[0][0]

        if has_odds and (bet > 0 or ou_rec != "观望"):
            picks.append({'时间': time_str, '赛事': league, '对阵': f"{h} vs {a}", '推荐': final_rec, '金额': round(bet,2), '比分': best_sc, '总进球': tg_str, '大小球': ou_rec})

        ai_txt = "AI裁判长连接超时，已跳过。"
        if llm_client:
            prompt = f"比赛:{h} vs {a}。模型倾向:{choice}。风险提示:{warn_c}{warn_t}{warn_r}。请用80字客观总结风险，给出操盘建议。"
            try: 
                res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":prompt}], stream=False, timeout=10)
                ai_txt = res.choices[0].message.content.strip()
            except: pass

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))
        ax1.bar(['主胜', '平局', '客胜'], [ph*100, pd_*100, pa*100], color=['#4e79a7','#f28e2b','#e15759'], width=0.5)
        ax1.set_title("零膨胀融合胜率"); ax1.set_ylim(0,100)
        for i,v in enumerate([ph*100,pd_*100,pa*100]): ax1.text(i, v+2, f"{v:.1f}%", ha='center', fontweight='bold')
        ax2.barh(['客队', '主队'], [away_xg, home_xg], color=['#59a14f','#e15759'], height=0.4)
        ax2.set_title("基准预期进球(xG)")
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); imgs.append(buf); plt.close(fig)

        logs.append({'date': date_str, 'league': league, 'home': h, 'away': a, 'res': final_rec, 'bet': round(bet,2), 'score': best_sc})

        html_cards += f"""
        <div style="border:1px solid #ddd; border-radius:10px; padding:20px; margin-bottom:20px; background:#fff;">
            <h3 style="color:#2c3e50; border-bottom:2px solid #eee; padding-bottom:10px;">{time_str} {h} vs {a} <span style="float:right; font-size:14px; background:#e8f4fd; padding:4px 8px; border-radius:10px;">{src}</span></h3>
            <img src="cid:chart_{len(imgs)-1}" width="100%" style="margin:10px 0;">
            <div style="display:flex; justify-content:space-between; background:#f8f9fa; padding:10px; border-radius:6px;">
                <div><b>首选比分:</b> {best_sc} <br><span style="color:#666; font-size:12px;">防冷: {top3}</span></div>
                <div><b>总进球:</b> {tg_str}</div>
            </div>
            {f"<p style='color:#c0392b; font-size:13px; margin-top:10px;'>{warn_c} {warn_t} {warn_r}</p>" if warn_c or warn_t or warn_r else ""}
            <p style="font-size:13px; margin-top:10px;"><b>💡 结论:</b> {choice} (推荐: {final_rec})</p>
            <p style="font-size:13px; color:#333;"><b>⚖️ AI裁判长:</b> {ai_txt}</p>
        </div>
        """

# ================= 5. V190.1 核心：串关策略引擎 =================
parlay_html = "<p style='text-align:center; color:#666;'>今日无明显正期望值单子，不推荐串关。</p>"
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
        <div style="background:#fff; padding:20px; border-radius:10px; border-top:5px solid #27ae60;">
            <p style="color:#27ae60; font-weight:bold;">✨ 系统侦测到高期望值串关机会，利用复利法则博取高赔率：</p>
            {df_parlay.to_html(index=False, border=0, classes='report-table', justify='center', escape=False)}
        </div>
        """
    else:
        parlay_html = "<p style='text-align:center; color:#666;'>今日单场EV不足，不强行组合串关。</p>"

# ================= 6. 结果发送 =================
html = f"""<html><body style="font-family:Arial; padding:20px; background-color:#f4f7f6;">
<div style="max-width:900px; margin:auto;">
<h1 style="text-align:center; color:#2c3e50;">⚽ 足球量化决策清单 (V190.1 终极资金版)</h1>
<h2 style="color:#e74c3c; border-bottom:2px solid #e74c3c; padding-bottom:10px;">Part 1: 单关狙击清单</h2>
{ pd.DataFrame(picks).to_html(index=False, border=0, justify='center', escape=False) if picks else "<p style='text-align:center; color:#c0392b; font-weight:bold; padding:20px;'>今日无高价值单关，建议空仓。</p>" }
<h2 style="color:#27ae60; border-bottom:2px solid #27ae60; padding-bottom:10px; margin-top:30px;">Part 2: 串关复利策略 (High EV)</h2>
{parlay_html}
<h2 style="color:#2980b9; border-bottom:2px solid #2980b9; padding-bottom:10px; margin-top:40px;">Part 3: 全景数据剖析</h2>
{html_cards}
</div>
</body></html>"""

if logs:
    pd.DataFrame(logs).to_csv('predictions_log.csv', mode='a', header=not os.path.exists('predictions_log.csv'), index=False, encoding='utf-8-sig')
open('dashboard.html', 'w', encoding='utf-8').write(html)
send_email("⚽ 今日竞彩量化清单 (V190.1 终极资金版)", html, imgs)
print("🏁 运行完毕！")
