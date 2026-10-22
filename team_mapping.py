import unicodedata

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

TEAM_MAPPING = {
    # ================== 🇬🇧 英格兰 (Premier League, Championship, League One, League Two) ==================
    'Arsenal': '阿森纳', 'Arsenal FC': '阿森纳', 'Aston Villa': '阿斯顿维拉', 'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯',
    'Brentford': '布伦特福德', 'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿', 'Chelsea': '切尔西', 
    'Crystal Palace': '水晶宫', 'Everton': '埃弗顿', 'Fulham': '富勒姆', 'Ipswich Town': '伊普斯维奇', 'Ipswich': '伊普斯维奇',
    'Leicester City': '莱斯特城', 'Leicester': '莱斯特城', 'Liverpool': '利物浦', 'Manchester City': '曼城', 'Man City': '曼城',
    'Manchester United': '曼联', 'Man Utd': '曼联', 'Man United': '曼联', 'Newcastle United': '纽卡斯尔联', 'Newcastle': '纽卡斯尔联',
    'Nottingham Forest': '诺丁汉森林', 'Nott\'m Forest': '诺丁汉森林', 'Southampton': '南安普顿', 
    'Tottenham Hotspur': '热刺', 'Tottenham': '热刺', 'Spurs': '热刺', 'West Ham United': '西汉姆联', 'West Ham': '西汉姆联',
    'Wolverhampton Wanderers': '狼队', 'Wolves': '狼队', 'Wolverhampton': '狼队',
    
    'Leeds United': '利兹联', 'Leeds': '利兹联', 'Burnley': '伯恩利', 'Sheffield United': '谢菲尔德联', 'Luton Town': '卢顿', 'Luton': '卢顿',
    'Sunderland': '桑德兰', 'Middlesbrough': '米德尔斯堡', 'West Bromwich Albion': '西布罗姆维奇', 'West Brom': '西布罗姆维奇',
    'Norwich City': '诺维奇', 'Norwich': '诺维奇', 'Hull City': '赫尔城', 'Hull': '赫尔城', 'Coventry City': '考文垂', 'Coventry': '考文垂',
    'Watford': '沃特福德', 'Bristol City': '布里斯托尔城', 'Swansea City': '斯旺西', 'Swansea': '斯旺西', 'Cardiff City': '卡迪夫城', 'Cardiff': '卡迪夫城',
    'Preston North End': '普雷斯顿', 'Preston': '普雷斯顿', 'Millwall': '米尔沃尔', 'Queens Park Rangers': '女王公园巡游者', 'QPR': '女王公园巡游者',
    'Stoke City': '斯托克城', 'Stoke': '斯托克城', 'Blackburn Rovers': '布莱克本', 'Blackburn': '布莱克本', 'Sheffield Wednesday': '谢周三', 'Sheffield Wed': '谢周三',
    'Plymouth Argyle': '普利茅斯', 'Plymouth': '普利茅斯', 'Derby County': '德比郡', 'Derby': '德比郡',
    'Birmingham City': '伯明翰', 'Birmingham': '伯明翰', 'Huddersfield Town': '哈德斯菲尔德', 'Huddersfield': '哈德斯菲尔德',
    'Charlton Athletic': '查尔顿', 'Charlton': '查尔顿', 'Bolton Wanderers': '博尔顿', 'Bolton': '博尔顿', 
    'Fleetwood Town': '弗利特伍德', 'Bradford City': '布拉德福德', 'Peterborough United': '彼得堡联', 'Peterborough': '彼得堡联',
    'Accrington Stanley': '艾宁顿', 'Barnet': '巴尼特', 'Barnsley': '巴恩斯利', 'Blackpool': '布莱克浦', 'Boreham Wood': '博勒姆伍德',
    'Bristol Rovers': '布里斯托尔流浪', 'Burton Albion': '伯顿阿尔比恩', 'Bury': '贝里', 'Wrexham': '雷克瑟姆', 

    # ================== 🇩🇪 德国 (Bundesliga, 2. Bundesliga, 3. Liga) ==================
    'Bayern Munich': '拜仁慕尼黑', 'Bayern': '拜仁慕尼黑', 'Borussia Dortmund': '多特蒙德', 'Dortmund': '多特蒙德', 
    'Bayer Leverkusen': '勒沃库森', 'Leverkusen': '勒沃库森', 'RB Leipzig': '莱比锡红牛', 'Leipzig': '莱比锡红牛', 
    'VfB Stuttgart': '斯图加特', 'Stuttgart': '斯图加特', 'Eintracht Frankfurt': '法兰克福', 'Frankfurt': '法兰克福', 
    'SC Freiburg': '弗赖堡', 'Freiburg': '弗赖堡', 'TSG Hoffenheim': '霍芬海姆', 'Hoffenheim': '霍芬海姆', 
    'FC Augsburg': '奥格斯堡', 'Augsburg': '奥格斯堡', 'Werder Bremen': '云达不莱梅', 'Bremen': '云达不莱梅', 
    'VfL Wolfsburg': '沃尔夫斯堡', 'Wolfsburg': '沃尔夫斯堡', 'Borussia Monchengladbach': '门兴格拉德巴赫', 'Gladbach': '门兴格拉德巴赫',
    'Mainz 05': '美因茨', 'Mainz': '美因茨', 'Union Berlin': '柏林联合', '1. FC Union Berlin': '柏林联合', 
    'VfL Bochum': '波鸿', 'Bochum': '波鸿', 'FC Cologne': '科隆', 'Cologne': '科隆', '1. FC Heidenheim': '海登海姆', 'Heidenheim': '海登海姆',
    'Darmstadt 98': '达姆施塔特', 'Darmstadt': '达姆施塔特', 'Schalke 04': '沙尔克04', 'Schalke': '沙尔克04', 
    'Hamburger SV': '汉堡', 'Hamburg': '汉堡', 'Fortuna Dusseldorf': '杜塞尔多夫', 'Dusseldorf': '杜塞尔多夫',
    'Hannover 96': '汉诺威96', 'Hannover': '汉诺威96', '1. FC Nurnberg': '纽伦堡', 'Nurnberg': '纽伦堡', 
    'Hertha BSC': '柏林赫塔', 'Hertha': '柏林赫塔', 'SC Paderborn 07': '帕德博恩', 'Paderborn': '帕德博恩',
    'Greuther Furth': '菲尔特', 'Furth': '菲尔特', 'Holstein Kiel': '基尔', 'Kiel': '基尔', 'Karlsruher SC': '卡尔斯鲁厄', 'Karlsruhe': '卡尔斯鲁厄',
    'SV Elversberg': '艾禾斯堡', 'Elversberg': '艾禾斯堡', 'Wehen Wiesbaden': '威斯巴登', 'Wiesbaden': '威斯巴登',
    'Hansa Rostock': '罗斯托克', 'Rostock': '罗斯托克', 'Arminia Bielefeld': '比勒菲尔德', 'Bielefeld': '比勒菲尔德', 
    'TSV 1860 Munich': '慕尼黑1860', '1860 Munich': '慕尼黑1860', 'Dynamo Dresden': '德累斯顿', 'Dresden': '德累斯顿',
    'Rot-Weiss Essen': '红白埃森', 'Essen': '红白埃森', 'Waldhof Mannheim': '曼海姆', 'Mannheim': '曼海姆',

    # ================== 🇮🇹 意大利 (Serie A, Serie B, Serie C) ==================
    'Inter Milan': '国际米兰', 'Inter': '国际米兰', 'AC Milan': 'AC米兰', 'Milan': 'AC米兰', 
    'Juventus': '尤文图斯', 'Juventus FC': '尤文图斯', 'Napoli': '那不勒斯', 'Atalanta': '亚特兰大', 
    'AS Roma': '罗马', 'Roma': '罗马', 'Lazio': '拉齐奥', 'SS Lazio': '拉齐奥', 'Fiorentina': '佛罗伦萨',
    'Bologna': '博洛尼亚', 'Torino': '都灵', 'Monza': '蒙扎', 'Genoa': '热那亚', 'Lecce': '莱切', 
    'Sassuolo': '萨索洛', 'Udinese': '乌迪内斯', 'Cagliari': '卡利亚里', 'Empoli': '恩波利', 
    'Hellas Verona': '维罗纳', 'Verona': '维罗纳', 'Frosinone': '弗洛西诺内', 'Salernitana': '萨勒尼塔纳',
    'Como': '科莫', 'Parma': '帕尔马', 'Parma Calcio': '帕尔马', 'Venezia': '威尼斯', 'Cremonese': '克雷莫内塞',
    'Sampdoria': '桑普多利亚', 'Palermo': '巴勒莫', 'Bari': '巴里', 'Pisa': '比萨', 'Reggiana': '雷吉亚纳',
    'Spezia': '斯佩齐亚', 'Catanzaro': '卡坦扎罗', 'Südtirol': '南蒂罗尔', 'Modena': '摩德纳', 'Cosenza': '科森扎',
    'Brescia': '布雷西亚', 'Ascoli': '阿斯科利', 'Lecco': '莱科', 'Ternana': '特尔纳纳', 'FeralpiSalo': '费拉尔皮萨洛',

    # ================== 🇪🇸 西班牙 (La Liga, La Liga 2, Primera Federación) ==================
    'Real Madrid': '皇家马德里', 'Real Madrid CF': '皇家马德里', 'Barcelona': '巴塞罗那', 'FC Barcelona': '巴塞罗那',
    'Atletico Madrid': '马德里竞技', 'Atletico': '马德里竞技', 'Girona': '赫罗纳', 'Girona FC': '赫罗纳',
    'Athletic Bilbao': '毕尔巴鄂竞技', 'Athletic Club': '毕尔巴鄂竞技', 'Real Sociedad': '皇家社会', 'Real Betis': '皇家贝蒂斯', 
    'Villarreal': '比利亚雷亚尔', 'Valencia': '瓦伦西亚', 'Valencia CF': '瓦伦西亚', 'Sevilla': '塞维利亚', 'Sevilla FC': '塞维利亚',
    'Osasuna': '奥萨苏纳', 'Getafe': '赫塔菲', 'Celta Vigo': '塞尔塔', 'Mallorca': '马洛卡', 'Las Palmas': '拉斯帕尔马斯',
    'Rayo Vallecano': '巴列卡诺', 'Alaves': '阿拉维斯', 'Cadiz': '加的斯', 'Granada': '格拉纳达', 'Almeria': '阿尔梅里亚',
    'Leganes': '莱加内斯', 'Real Valladolid': '巴拉多利德', 'Valladolid': '巴拉多利德', 'Espanyol': '西班牙人',
    'Levante': '莱万特', 'Malaga': '马拉加', 'Deportivo La Coruna': '拉科鲁尼亚', 'Deportivo': '拉科鲁尼亚',
    'Racing Santander': '桑坦德竞技', 'Elche': '埃尔切', 'Real Zaragoza': '皇家萨拉戈萨', 'Sporting Gijon': '希洪竞技',
    'Oviedo': '奥维耶多', 'Eibar': '埃瓦尔', 'Huesca': '韦斯卡', 'Mirandes': '米兰德斯', 'Albacete': '阿尔巴塞特',
    'Burgos': '布尔戈斯', 'FC Andorra': '安道尔FC', 'Amorebieta': '阿莫雷比埃塔', 'Eldense': '埃尔登塞', 'Cartagena': '卡塔赫纳',

    # ================== 🇫🇷 法国 (Ligue 1, Ligue 2, National) ==================
    'Paris Saint-Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼', 'Paris SG': '巴黎圣日耳曼', 'Marseille': '马赛', 'Olympique Marseille': '马赛',
    'Monaco': '摩纳哥', 'AS Monaco': '摩纳哥', 'Lille': '里尔', 'Lille OSC': '里尔', 'Nice': '尼斯', 'OGC Nice': '尼斯', 
    'Lens': '朗斯', 'RC Lens': '朗斯', 'Rennes': '雷恩', 'Stade Rennais': '雷恩', 'Lyon': '里昂', 'Olympique Lyonnais': '里昂', 
    'Reims': '兰斯', 'Montpellier': '蒙彼利埃', 'Toulouse': '图卢兹', 'Strasbourg': '斯特拉斯堡', 'Nantes': '南特',
    'Brest': '布雷斯特', 'Le Havre': '勒阿弗尔', 'Metz': '梅斯', 'Lorient': '洛里昂', 'Clermont Foot': '克莱蒙', 'Clermont': '克莱蒙',
    'Saint-Etienne': '圣埃蒂安', 'AS Saint-Etienne': '圣埃蒂安', 'Auxerre': '欧塞尔', 'Angers': '昂热', 'SCO Angers': '昂热',
    'Bordeaux': '波尔多', 'Girondins Bordeaux': '波尔多', 'Amiens': '亚眠', 'Guingamp': '甘冈', 'Sochaux': '索肖',
    'Caen': '卡昂', 'Bastia': '巴斯蒂亚', 'Ajaccio': '阿雅克肖', 'Grenoble': '格勒诺布尔', 'Pau FC': '波城', 'Rodez': '罗德兹',
    'Dunkerque': '敦刻尔克', 'Concarneau': '孔卡尔诺', 'Valenciennes': '瓦朗谢纳', 'Troyes': '特鲁瓦', 'Quevilly-Rouen': '克维伊',

    # ================== 🇳🇱 荷兰 (Eredivisie, Eerste Divisie) ==================
    'Ajax': '阿贾克斯', 'Ajax Amsterdam': '阿贾克斯', 'PSV Eindhoven': '埃因霍温', 'PSV': '埃因霍温', 
    'Feyenoord': '费耶诺德', 'Feyenoord Rotterdam': '费耶诺德', 'AZ Alkmaar': '阿尔克马尔', 'AZ': '阿尔克马尔',
    'FC Twente': '特温特', 'Twente': '特温特', 'NEC Nijmegen': '奈梅亨', 'NEC': '奈梅亨', 'N.E.C.': '奈梅亨', 
    'FC Utrecht': '乌德勒支', 'Utrecht': '乌德勒支', 'Go Ahead Eagles': '前进之鹰', 'Sparta Rotterdam': '鹿特丹斯巴达',
    'Heerenveen': '海伦芬', 'SC Heerenveen': '海伦芬', 'PEC Zwolle': '兹沃勒', 'Zwolle': '兹沃勒', 'Fortuna Sittard': '锡塔德幸运',
    'Almere City': '阿尔梅勒城', 'Heracles Almelo': '赫拉克勒斯', 'RKC Waalwijk': '瓦尔韦克', 'Vitesse': '维特斯', 'SBV Vitesse': '维特斯',
    'Excelsior': '埃克塞尔西奥', 'Volendam': '沃伦丹', 'Willem II': '威廉二世', 'FC Groningen': '格罗宁根', 'Groningen': '格罗宁根',
    'Roda JC Kerkrade': '罗达JC', 'ADO Den Haag': '海牙', 'VVV-Venlo': '芬洛', 'FC Emmen': '埃门', 'Cambuur': '坎布尔',

    # ================== 🌍 东欧 / 俄罗斯 / 乌克兰 / 波兰 / 捷克 ==================
    'Zenit St. Petersburg': '圣彼得堡泽尼特', 'Zenit': '圣彼得堡泽尼特', 'FC Krasnodar': '克拉斯诺达尔', 'Krasnodar': '克拉斯诺达尔',
    'Dynamo Moscow': '莫斯科迪纳摩', 'FC Dynamo Moscow': '莫斯科迪纳摩', 'Lokomotiv Moscow': '莫斯科火车头', 'FC Lokomotiv Moscow': '莫斯科火车头',
    'Spartak Moscow': '莫斯科斯巴达克', 'CSKA Moscow': '莫斯科中央陆军', 'Rostov': '罗斯托夫', 'FC Rostov': '罗斯托夫',
    'Rubin Kazan': '喀山红宝石', 'Akhmat Grozny': '格罗兹尼艾哈迈特', 'Sochi': '索契', 'FC Sochi': '索契', 'Krylia Sovetov': '苏维埃之翼',
    'Ural Yekaterinburg': '乌拉尔', 'Nizhny Novgorod': '下诺夫哥罗德', 'Baltika': '加里宁格勒波罗的海', 'Fakel Voronezh': '沃罗涅日火炬',
    
    'Shakhtar Donetsk': '顿涅茨克矿工', 'FC Shakhtar Donetsk': '顿涅茨克矿工', 'Dynamo Kyiv': '基辅迪纳摩', 'FC Dynamo Kyiv': '基辅迪纳摩',
    'SC Dnipro-1': '第聂伯罗-1', 'Zorya Luhansk': '卢甘斯克黎明', 'Vorskla Poltava': '波尔塔瓦沃尔斯克拉', 'Oleksandriya': '亚历山德里亚',
    'Kolos Kovalivka': '科洛斯', 'Chornomorets Odesa': '敖德萨黑海人', 'Rukh Lviv': '利沃夫鲁赫', 'Polissya Zhytomyr': '日托米尔波利西亚',
    
    'Rakow Czestochowa': '琴斯托霍瓦', 'Legia Warsaw': '华沙莱吉亚', 'Lech Poznan': '波兹南莱赫', 'Jagiellonia Bialystok': '乔治罗尼亚',
    'Gornik Zabrze': '扎布热矿工', 'Pogon Szczecin': '什切青波贡', 'Wislaw Plock': '华沙普洛克', 'Slask Wroclaw': '弗罗茨瓦夫斯拉斯克',
    'Radomiak Radom': '拉多米亚克', 'Widzew Lodz': '罗兹维泽夫', 'Cracovia': '克拉科维亚', 'Zaglebie Lubin': '卢宾扎格勒比',
    'Piast Gliwice': '格利维采皮亚斯特', 'Korona Kielce': '凯尔采科罗纳', 'Ruch Chorzow': '霍茹夫鲁赫', 'LKS Lodz': '罗兹LKS',

    'Sparta Prague': '布拉格斯巴达', 'AC Sparta Prague': '布拉格斯巴达', 'Slavia Prague': '布拉格斯拉维亚', 'SK Slavia Prague': '布拉格斯拉维亚',
    'Viktoria Plzen': '比尔森胜利', 'FC Viktoria Plzen': '比尔森胜利', 'Banik Ostrava': '俄斯特拉发巴尼克', 'Slovacko': '斯洛瓦茨科',
    'Mlada Boleslav': '博莱斯拉夫', 'FK Jablonec': '亚布洛内茨', 'Jablonec': '亚布洛内茨', 'Slovan Liberec': '利贝雷茨',
    'Teplice': '特普利采', 'Sigma Olomouc': '奥洛穆茨', 'Bohemians 1905': '波希米亚人1905', 'Dukla Prague': '布拉格杜克拉',

    # ================== 🌍 北欧 / 奥地利 / 瑞士 ==================
    'Red Bull Salzburg': '萨尔茨堡红牛', 'RB Salzburg': '萨尔茨堡红牛', 'FC Salzburg': '萨尔茨堡红牛', 'Sturm Graz': '格拉茨风暴', 'SK Sturm Graz': '格拉茨风暴',
    'Rapid Vienna': '维也纳快速', 'SK Rapid Wien': '维也纳快速', 'LASK Linz': 'LASK林茨', 'LASK': 'LASK林茨', 
    'Wolfsberger AC': '沃尔夫斯贝格', 'Wolfsberg': '沃尔夫斯贝格', 'Austria Vienna': '奥地利维也纳', 
    'Austria Klagenfurt': '奥地利克拉根福', 'Blau-Weiss Linz': '蓝白林茨', 'SCR Altach': '阿尔特阿赫', 'TSV Hartberg': '哈特贝格',
    
    'Young Boys': '伯尔尼年轻人', 'BSC Young Boys': '伯尔尼年轻人', 'Basel': '巴塞尔', 'FC Basel': '巴塞尔',
    'FC Zurich': '苏黎世', 'Zurich': '苏黎世', 'Servette': '塞尔维特', 'FC Servette': '塞尔维特', 
    'Lugano': '卢加诺', 'FC Lugano': '卢加诺', 'Lucerne': '卢塞恩', 'FC Luzern': '卢塞恩', 
    'St. Gallen': '圣加仑', 'FC St. Gallen': '圣加仑', 'Sion': '锡永', 'FC Sion': '锡永', 
    'Grasshopper': '草蜢', 'Grasshopper Zurich': '草蜢', 'Lausanne-Sport': '洛桑体育', 'Lausanne': '洛桑体育',
    'Yverdon-Sport': '伊韦尔东', 'Yverdon': '伊韦尔东', 'FC Winterthur': '温特图尔', 'Winterthur': '温特图尔', 'FC Thun': '图恩', 'Thun': '图恩',
    
    'Malmo FF': '马尔默', 'Malmo': '马尔默', 'AIK': 'AIK索尔纳', 'AIK Stockholm': 'AIK索尔纳', 'Djurgardens IF': '佐加顿斯', 'Djurgarden': '佐加顿斯',
    'Hammarby IF': '哈马比', 'Hammarby': '哈马比', 'IFK Goteborg': 'IFK哥德堡', 'Goteborg': 'IFK哥德堡', 'Helsingborg': '赫尔辛堡',
    'IF Elfsborg': '埃尔夫斯堡', 'Elfsborg': '埃尔夫斯堡', 'IK Sirius': '天狼星', 'Sirius': '天狼星', 'IFK Norrkoping': '北雪平', 'Norrkoping': '北雪平',
    'Bodo/Glimt': '博多闪耀', 'Bodo Glimt': '博多闪耀', 'Molde': '莫尔德', 'Molde FK': '莫尔德', 'Rosenborg': '罗森博格',
    'Rosenborg BK': '罗森博格', 'Viking FK': '维京', 'Viking': '维京', 'Lillestrom': '利勒斯特罗姆', 'Lillestrom SK': '利勒斯特罗姆',
    'SK Brann': '布兰', 'Brann': '布兰', 'Tromso': '特罗姆瑟', 'Tromso IL': '特罗姆瑟', 'Valerenga': '瓦勒伦加', 'Fredrikstad': '费德列斯达',
    'FC Copenhagen': '哥本哈根', 'Copenhagen': '哥本哈根', 'Brondby IF': '布隆德比', 'Brondby': '布隆德比', 'FC Midtjylland': '中日德兰', 'Midtjylland': '中日德兰',
    'AGF Aarhus': '奥胡斯', 'AGF': '奥胡斯', 'Silkeborg IF': '锡尔克堡', 'Silkeborg': '锡尔克堡', 'FC Nordsjaelland': '北西兰', 'Nordsjaelland': '北西兰',

    # ================== 🌍 土耳其 / 希腊 / 以色列 / 塞浦路斯 ==================
    'Galatasaray': '加拉塔萨雷', 'Galatasaray SK': '加拉塔萨雷', 'Fenerbahce': '费内巴切', 'Fenerbahce SK': '费内巴切', 
    'Besiktas': '贝西克塔斯', 'Besiktas JK': '贝西克塔斯', 'Trabzonspor': '特拉布宗体育', 'Trabzonspor AŞ': '特拉布宗体育',
    'Basaksehir': '伊斯坦布尔巴萨克塞尔', 'Istanbul Basaksehir': '伊斯坦布尔巴萨克塞尔', 'Adana Demirspor': '阿达纳德米尔体育',
    'Kasimpasa': '卡斯帕萨', 'Kasimpasa SK': '卡斯帕萨', 'Kayserispor': '开塞利体育', 'Antalyaspor': '安塔利亚体育',
    'Alanyaspor': '阿拉尼亚体育', 'Konyaspor': '科尼亚体育', 'Sivasspor': '锡瓦斯体育', 'Samsunspor': '萨姆松体育', 'Rizespor': '里泽体育',
    'Ankaragucu': '安卡拉古库', 'Gaziantep FK': '加济安泰普', 'Fatih Karagumruk': '法蒂赫卡拉古姆鲁克', 'Pendikspor': '彭迪克体育',
    'Hatayspor': '哈塔伊体育', 'Istanbulspor': '伊斯坦布尔体育',

    'Olympiacos': '奥林匹亚科斯', 'Olympiacos FC': '奥林匹亚科斯', 'Panathinaikos': '帕纳辛奈科斯', 'Panathinaikos FC': '帕纳辛奈科斯',
    'AEK Athens': '雅典AEK', 'AEK': '雅典AEK', 'PAOK': '塞萨洛尼基', 'PAOK Salonika': '塞萨洛尼基', 'Aris': '阿里斯', 'Aris Thessaloniki': '阿里斯',
    'OFI Crete': 'OFI克里特', 'OFI': 'OFI克里特', 'Panserraikos': '潘塞雷科斯', 'Asteras Tripolis': '特里波利斯', 'Atromitos': '阿特罗米托斯',
    'Volos NFC': '沃洛斯', 'Kifisia': '基菲夏', 'Panetolikos': '帕纳托利克斯', 'PAS Giannina': '吉安尼纳',

    'Maccabi Tel Aviv': '特拉维夫马卡比', 'Maccabi Haifa': '海法马卡比', 'Hapoel Be\'er Sheva': '贝尔谢巴夏普尔', 'Hapoel Be\'er': '贝尔谢巴夏普尔',
    'Beitar Jerusalem': '耶路撒冷比达', 'Hapoel Haifa': '海法夏普尔', 'Hapoel Tel Aviv': '特拉维夫夏普尔', 
    'Maccabi Netanya': '内坦亚马卡比', 'Bnei Sakhnin': '萨克宁', 'Ashdod': '阿舒多', 'Hapoel Jerusalem': '耶路撒冷夏普尔',
    'Maccabi Bnei Reineh': '马卡比贝内雷内', 'Hapoel Petah Tikva': '彼达提克瓦夏普尔', 'Maccabi Petah Tikva': '彼达提克瓦马卡比',

    'APOEL Nicosia': 'APOEL尼科西亚', 'APOEL': 'APOEL尼科西亚', 'Omonia Nicosia': '奥莫尼亚', 'Omonia': '奥莫尼亚',
    'AEK Larnaca': '拉纳卡AEK', 'Aris Limassol': '利马索尔阿里斯', 'Pafos FC': '帕福斯', 'Pafos': '帕福斯', 'Apollon Limassol': '利马索尔阿波罗',
    'Anorthosis Famagusta': '法马古斯塔阿诺索西斯', 'Nea Salamis': '新萨拉米斯', 'Doxa Katokopias': '多克萨', 'Karmiotissa': '卡尔米奥蒂萨',

    # ================== 🌍 中亚 / 高加索 / 巴尔干地区 ==================
    'Qarabag FK': '卡拉巴赫', 'Qarabag': '卡拉巴赫', 'Sabah FK': '萨巴巴库', 'Sabah': '萨巴巴库', 'Neftci Baku': '巴库石油工人',
    'Astana': '阿斯塔纳', 'FC Astana': '阿斯塔纳', 'Kairat Almaty': '阿拉木图凯拉特', 'Kairat': '阿拉木图凯拉特', 'Aktobe': '阿克托比',
    'Ararat-Armenia': '亚拉腊-亚美尼亚', 'Ararat Armenia': '亚拉腊-亚美尼亚', 'Pyunik': '叶里温凤凰', 'Urartu': '乌拉尔图',
    'Dinamo Zagreb': '萨格勒布迪纳摩', 'GNK Dinamo Zagreb': '萨格勒布迪纳摩', 'Hajduk Split': '哈伊杜克', 'Hajduk': '哈伊杜克', 'Rijeka': '里耶卡',
    'Red Star Belgrade': '贝尔格莱德红星', 'Crvena Zvezda': '贝尔格莱德红星', 'Partizan Belgrade': '贝尔格莱德游击', 'Partizan': '贝尔格莱德游击',
    'Levski Sofia': '索菲亚列夫斯基', 'Levski': '索菲亚列夫斯基', 'Ludogorets Razgrad': '卢多戈雷茨', 'Ludogorets': '卢多戈雷茨',
    'Sheriff Tiraspol': '蒂拉斯波尔警长', 'Sheriff': '蒂拉斯波尔警长', 'Slovan Bratislava': '布拉迪斯拉发', 'Slovan': '布拉迪斯拉发',
    'Ferencvaros': '费伦茨瓦罗斯', 'Ferencvarosi TC': '费伦茨瓦罗斯', 'NK Celje': '采列', 'Celje': '采列', 
    'Rakow Czestochowa': '琴斯托霍瓦', 'Rakow': '琴斯托霍瓦', 'Jagiellonia Bialystok': '乔治罗尼亚', 'Jagiellonia': '乔治罗尼亚',
    'Lech Poznan': '莱赫波兹南', 'Lech': '莱赫波兹南', 'Legia Warsaw': '华沙莱吉亚', 'Legia': '华沙莱吉亚',

    # ================== 🌍 其他欧战常客及洲际球队 ==================
    'Club Brugge': '布鲁日', 'Club Brugge KV': '布鲁日', 'Anderlecht': '安德莱赫特', 'RSC Anderlecht': '安德莱赫特', 
    'Genk': '亨克', 'KRC Genk': '亨克', 'Union St. Gilloise': '圣吉尔联', 'Union SG': '圣吉尔联', 'Union St.-Gilloise': '圣吉尔联', 'Union Saint-Gilloise': '圣吉尔联',
    'Antwerp': '安特卫普', 'Royal Antwerp': '安特卫普', 'Gent': '根特', 'KAA Gent': '根特', 'Standard Liege': '标准列日', 'Standard': '标准列日',
    'Benfica': '本菲卡', 'SL Benfica': '本菲卡', 'Porto': '波尔图', 'FC Porto': '波尔图', 'Sporting CP': '葡萄牙体育', 'Sporting Lisbon': '葡萄牙体育',
    'Sporting Braga': '布拉加', 'Braga': '布拉加', 'SC Braga': '布拉加', 'Vitoria Guimaraes': '吉马良斯', 'Guimaraes': '吉马良斯',
    'Celtic': '凯尔特人', 'Celtic FC': '凯尔特人', 'Rangers': '格拉斯哥流浪者', 'Rangers FC': '格拉斯哥流浪者',
    'Montevideo City Torque': '蒙得维的亚城力矩', 'Atletico Mineiro': '米内罗竞技', 'Atletico Nacional': '国民竞技', 'Deportivo Pasto': '帕斯托体育',
    'Brisbane Roar': '布里斯班狮吼', 'Perth Glory': '珀斯光荣', 'Melbourne City': '墨尔本城', 'Melbourne Victory': '墨尔本胜利', 'Sydney FC': '悉尼FC'
}

def translate_team_name(name):
    if not isinstance(name, str): return name
    cleaned_name = remove_accents(name.replace(" and ", " & ").strip())
    return TEAM_MAPPING.get(cleaned_name, cleaned_name)
