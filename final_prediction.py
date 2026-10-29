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
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("==================================================")
print("🚀 启动 V200.0 玄学美学·天气全知版")
print("==================================================")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

# ================= 1. 玄学五行模块 =================
def get_wuxing_theme():
    """计算当天的天干地支及五行主题颜色"""
    base_date = datetime(1900, 1, 31)
    today = datetime.now()
    days_diff = (today - base_date).days
    
    tiangan = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
    dizhi = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
    
    gan_idx = days_diff % 10
    zhi_idx = days_diff % 12
    day_ganzhi = tiangan[gan_idx] + dizhi[zhi_idx]
    
    wuxing_map = {
        '甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土', 
        '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'
    }
    element = wuxing_map[tiangan[gan_idx]]
    
    themes = {
        '木': {'bg': '#f0f7f4', 'primary': '#2e7d32', 'grad1': '#1b5e20', 'grad2': '#4caf50', 'icon': '🌳'},
        '火': {'bg': '#fdf5f5', 'primary': '#c62828', 'grad1': '#b71c1c', 'grad2': '#ef5350', 'icon': '🔥'},
        '土': {'bg': '#faf8f5', 'primary': '#e65100', 'grad1': '#bf360c', 'grad2': '#ff9800', 'icon': '⛰️'},
        '金': {'bg': '#f8f9fa', 'primary': '#c0a060', 'grad1': '#8d6e63', 'grad2': '#d4af37', 'icon': '⚔️'},
        '水': {'bg': '#f0f4f8', 'primary': '#1565c0', 'grad1': '#0d47a1', 'grad2': '#42a5f5', 'icon': '🌊'}
    }
    
    theme = themes[element]
    return day_ganzhi, element, theme

DAY_GANZHI, ELEMENT, THEME = get_wuxing_theme()
print(f"🌙 今日玄学匹配: {DAY_GANZHI}日 ({ELEMENT}属性)")

# ================= 2. 鲁棒性工具类 =================
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

# ================= 3. 超级天气智能追踪模块 =================
def get_weather(team, date_str):
    # 1. 超大静态字典（覆盖五大联赛及常见球队）
    city_map = {
        '阿森纳': 'London', '切尔西': 'London', '热刺': 'London', '西汉姆联': 'London', '水晶宫': 'London', '富勒姆': 'London', '布伦特福德': 'London',
        '曼联': 'Manchester', '曼城': 'Manchester',
        '利物浦': 'Liverpool', '埃弗顿': 'Liverpool',
        '纽卡斯尔联': 'Newcastle', '阿斯顿维拉': 'Birmingham', '狼队': 'Wolverhampton', '诺丁汉森林': 'Nottingham', '莱斯特城': 'Leicester', '南安普敦': 'Southampton', '布莱顿': 'Brighton', '伯恩茅斯': 'Bournemouth', '伊普斯维奇': 'Ipswich',
        '皇家马德里': 'Madrid', '马德里竞技': 'Madrid', '巴塞罗那': 'Barcelona', '西班牙人': 'Barcelona', '塞维利亚': 'Seville', '皇家贝蒂斯': 'Seville', '瓦伦西亚': 'Valencia', '比利亚雷亚尔': 'Villarreal', '毕尔巴鄂竞技': 'Bilbao', '皇家社会': 'San Sebastian', '赫罗纳': 'Girona', '塞尔塔': 'Vigo',
        '拜仁慕尼黑': 'Munich', '多特蒙德': 'Dortmund', '勒沃库森': 'Leverkusen', 'RB莱比锡': 'Leipzig', '法兰克福': 'Frankfurt', '斯图加特': 'Stuttgart', '门兴格拉德巴赫': 'Monchengladbach', '沃尔夫斯堡': 'Wolfsburg', '云达不莱梅': 'Bremen', '弗赖堡': 'Freiburg', '柏林联合': 'Berlin', '霍芬海姆': 'Sinsheim', '美因茨': 'Mainz', '奥格斯堡': 'Augsburg',
        '国际米兰': 'Milan', 'AC米兰': 'Milan', '尤文图斯': 'Turin', '都灵': 'Turin', '那不勒斯': 'Naples', '罗马': 'Rome', '拉齐奥': 'Rome', '亚特兰大': 'Bergamo', '佛罗伦萨': 'Florence', '博洛尼亚': 'Bologna', '热那亚': 'Genoa', '乌迪内斯': 'Udine', '蒙扎': 'Monza', '莱切': 'Lecce', '卡利亚里': 'Cagliari', '维罗纳': 'Verona', '恩波利': 'Empoli', '帕尔马': 'Parma', '科莫': 'Como', '威尼斯': 'Venice',
        '巴黎圣日耳曼': 'Paris', '马赛': 'Marseille', '摩纳哥': 'Monaco', '里尔': 'Lille', '里昂': 'Lyon', '尼斯': 'Nice', '朗斯': 'Lens', '雷恩': 'Rennes', '兰斯': 'Reims', '图卢兹': 'Toulouse', '蒙彼利埃': 'Montpellier', '斯特拉斯堡': 'Strasbourg', '南特': 'Nantes', '布雷斯特': 'Brest', '勒阿弗尔': 'Le Havre',
        '马尔默': 'Malmo', '哥本哈根': 'Copenhagen', '博多格林特': 'Bodo'
    }
    
    # 2. 读取本地缓存
    cache_file = 'team_city_cache.json'
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if team in cache:
                    city_map[team] = cache[team]
        except: pass

    city = city_map.get(team)
    
    # 3. 智能反查（针对冷门球队）
    if not city:
        print(f"🌍 字典中未找到 '{team}' 的城市，正在让 AI 自动检索...")
        if llm_client:
            try:
                prompt = f"球队 '{team}' 的主场在哪个城市？请只回复英文城市名，不要标点符号。例如：Milan。"
                res = llm_client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], stream=False, timeout=5)
                city = res.choices[0].message.content.strip().replace('.', '')
                if city and len(city) < 30:
                    city_map[team] = city
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(city_map, f, ensure_ascii=False, indent=4)
                else:
                    city = 'London'
            except:
                city = 'London'
        else:
            city = 'London'

    data = safe_request(f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&dt={date_str[:10]}&lang=zh")
    if data and 'forecast' in data:
        day = data['forecast']['forecastday'][0]['day']
        return day['condition']['text'], round(day['avgtemp_c'], 1)
    
    return "未知", 0

# ================= 4. 核心算法：零膨胀时间切片 =================
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

# ================= 5. 数据装载 =================
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

# ================= 6. 主预测流 =================
for league in df_next['联赛'].unique():
    html_cards += f"""
    <div style="background: linear-gradient(90deg, {THEME['grad1']} 0%, {THEME['grad2']} 100%); color: white; padding: 12px 20px; border-radius: 8px; margin-top: 35px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h2 style="margin: 0; font-size: 20px; letter-spacing: 1px;">🏆 {league}</h2>
    </div>
    """
    
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
        ax1.bar(['主胜', '平局', '客胜'], [ph*100, pd_*100, pa*100], color=[THEME['primary'], '#f28e2b', '#e15759'], width=0.5)
        ax1.set_title("零膨胀融合胜率", color=THEME['primary'], fontweight='bold'); ax1.set_ylim(0,100)
        for i,v in enumerate([ph*100,pd_*100,pa*100]): ax1.text(i, v+2, f"{v:.1f}%", ha='center', fontweight='bold')
        ax2.barh(['客队', '主队'], [away_xg, home_xg], color=['#59a14f', THEME['primary']], height=0.4)
        ax2.set_title("基准预期进球(xG)", color=THEME['primary'], fontweight='bold')
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); imgs.append(buf); plt.close(fig)

        logs.append({'date': date_str, 'league': league, 'home': h, 'away': a, 'res': final_rec, 'bet': round(bet,2), 'score': best_sc})

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
                    <span style="font-size: 24px; color: {THEME['primary']}; font-weight: bold; letter-spacing: 1px;">{best_sc}</span>
                    <span style="font-size: 12px; color: #666; margin-left: 10px;">防冷: {top3}</span>
                </div>
                <div style="flex: 1; background: #f4f8fd; border-left: 4px solid {THEME['primary']}; padding: 15px; border-radius: 6px;">
                    <span style="font-size: 13px; color: {THEME['primary']}; font-weight: bold; display: block; margin-bottom: 8px;">⚽ 总进球数</span>
                    <span style="font-size: 20px; color: #1e3c72; font-weight: bold;">{tg_str}</span>
                </div>
            </div>

            <div style="background: #fff8f8; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; text-align: center; font-size: 13px; color: #555; font-weight: bold;">
                    <div>主胜概率: <span style="color:{THEME['primary']};">{ph*100:.1f}%</span></div>
                    <div>平局概率: <span style="color:#f28e2b;">{pd_*100:.1f}%</span></div>
                    <div>客胜概率: <span style="color:#e15759;">{pa*100:.1f}%</span></div>
                </div>
            </div>

            {f"<div style='background-color: #fff3cd; color: #856404; padding: 12px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; font-weight: bold; border-left: 3px solid #ffc107;'>{warn_c} {warn_t} {warn_r}</div>" if warn_c or warn_t or warn_r else ""}

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

# ================= 7. 串关策略引擎 =================
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

# ================= 8. 最终组装发送 =================
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
send_email(f"【{DAY_GANZHI}日·{ELEMENT}】⚽ 足球量化决策清单 (V200.0)", html, imgs)
print("🏁 运行完毕！")
