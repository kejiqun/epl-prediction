import unicodedata

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

TEAM_MAPPING = {
    # ================== 英格兰 ==================
    'Arsenal': '阿森纳', 'Arsenal FC': '阿森纳', 'Aston Villa': '阿斯顿维拉', 'Aston Villa FC': '阿斯顿维拉', 
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯', 'Brentford': '布伦特福德', 'Brentford FC': '布伦特福德',
    'Brighton & Hove Albion': '布莱顿', 'Brighton': '布莱顿', 'Brighton & Hove Albion FC': '布莱顿', 'Chelsea': '切尔西', 'Chelsea FC': '切尔西', 
    'Crystal Palace': '水晶宫', 'Crystal Palace FC': '水晶宫', 'Everton': '埃弗顿', 'Everton FC': '埃弗顿', 'Fulham': '富勒姆', 'Fulham FC': '富勒姆',
    'Ipswich Town': '伊普斯维奇', 'Ipswich': '伊普斯维奇', 'Ipswich Town FC': '伊普斯维奇', 'Leicester City': '莱斯特城', 'Leicester': '莱斯特城', 'Leicester City FC': '莱斯特城',
    'Liverpool': '利物浦', 'Liverpool FC': '利物浦', 'Manchester City': '曼城', 'Man City': '曼城', 'Manchester City FC': '曼城',
    'Manchester United': '曼联', 'Man Utd': '曼联', 'Man United': '曼联', 'Manchester United FC': '曼联', 'Newcastle United': '纽卡斯尔联', 'Newcastle': '纽卡斯尔联', 'Newcastle United FC': '纽卡斯尔联',
    'Nottingham Forest': '诺丁汉森林', 'Nott\'m Forest': '诺丁汉森林', 'Nottingham Forest FC': '诺丁汉森林', 'Southampton': '南安普顿', 'Southampton FC': '南安普顿',
    'Tottenham Hotspur': '热刺', 'Tottenham': '热刺', 'Spurs': '热刺', 'Tottenham Hotspur FC': '热刺', 'West Ham United': '西汉姆联', 'West Ham': '西汉姆联', 'West Ham United FC': '西汉姆联',
    'Wolverhampton Wanderers': '狼队', 'Wolves': '狼队', 'Wolverhampton': '狼队', 'Wolverhampton Wanderers FC': '狼队',
    'Leeds United': '利兹联', 'Leeds': '利兹联', 'Leeds United FC': '利兹联', 'Burnley': '伯恩利', 'Burnley FC': '伯恩利', 'Sheffield United': '谢菲尔德联', 'Sheffield United FC': '谢菲尔德联', 
    'Luton Town': '卢顿', 'Luton': '卢顿', 'Luton Town FC': '卢顿', 'Sunderland': '桑德兰', 'Sunderland AFC': '桑德兰', 'Middlesbrough': '米德尔斯堡', 'Middlesbrough FC': '米德尔斯堡', 
    'West Bromwich Albion': '西布罗姆维奇', 'West Brom': '西布罗姆维奇', 'Norwich City': '诺维奇', 'Norwich': '诺维奇', 'Norwich City FC': '诺维奇', 
    'Hull City': '赫尔城', 'Hull': '赫尔城', 'Hull City AFC': '赫尔城', 'Coventry City': '考文垂', 'Coventry': '考文垂', 'Coventry City FC': '考文垂',
    'Watford': '沃特福德', 'Watford FC': '沃特福德', 'Bristol City': '布里斯托尔城', 'Swansea City': '斯旺西', 'Cardiff City': '卡迪夫城',
    'Preston North End': '普雷斯顿', 'Millwall': '米尔沃尔', 'Queens Park Rangers': '女王公园巡游者', 'QPR': '女王公园巡游者',
    'Stoke City': '斯托克城', 'Blackburn Rovers': '布莱克本', 'Sheffield Wednesday': '谢周三', 'Plymouth Argyle': '普利茅斯', 'Derby County': '德比郡',
    'Birmingham City': '伯明翰', 'Huddersfield Town': '哈德斯菲尔德', 'Charlton Athletic': '查尔顿', 'Bolton Wanderers': '博尔顿',
    
    # ================== 德国 ==================
    'Bayern Munich': '拜仁慕尼黑', 'Bayern': '拜仁慕尼黑', 'Borussia Dortmund': '多特蒙德', 'Dortmund': '多特蒙德', 'Bayer Leverkusen': '勒沃库森', 'Leverkusen': '勒沃库森', 
    'RB Leipzig': '莱比锡红牛', 'Leipzig': '莱比锡红牛', 'VfB Stuttgart': '斯图加特', 'Stuttgart': '斯图加特', 'Eintracht Frankfurt': '法兰克福', 'Frankfurt': '法兰克福', 
    'SC Freiburg': '弗赖堡', 'Freiburg': '弗赖堡', 'TSG Hoffenheim': '霍芬海姆', 'Hoffenheim': '霍芬海姆', 'FC Augsburg': '奥格斯堡', 'Augsburg': '奥格斯堡', 
    'Werder Bremen': '云达不莱梅', 'Bremen': '云达不莱梅', 'VfL Wolfsburg': '沃尔夫斯堡', 'Wolfsburg': '沃尔夫斯堡', 'Borussia Monchengladbach': '门兴格拉德巴赫', 'Gladbach': '门兴格拉德巴赫',
    'Mainz 05': '美因茨', 'Mainz': '美因茨', 'Union Berlin': '柏林联合', '1. FC Union Berlin': '柏林联合', 'VfL Bochum': '波鸿', 'Bochum': '波鸿', 
    'FC Cologne': '科隆', 'Cologne': '科隆', '1. FC Heidenheim': '海登海姆', 'Heidenheim': '海登海姆', 'Darmstadt 98': '达姆施塔特', 'Darmstadt': '达姆施塔特', 
    'Schalke 04': '沙尔克04', 'Schalke': '沙尔克04', 'Hamburger SV': '汉堡', 'Hamburg': '汉堡', 'Fortuna Dusseldorf': '杜塞尔多夫', 'Dusseldorf': '杜塞尔多夫',
    'Hannover 96': '汉诺威96', 'Hannover': '汉诺威96', '1. FC Nurnberg': '纽伦堡', 'Nurnberg': '纽伦堡', 'Hertha BSC': '柏林赫塔', 'Hertha': '柏林赫塔', 
    'SC Paderborn 07': '帕德博恩', 'Paderborn': '帕德博恩', 'Greuther Furth': '菲尔特', 'Furth': '菲尔特', 'Holstein Kiel': '基尔', 'Kiel': '基尔', 
    'Karlsruher SC': '卡尔斯鲁厄', 'Karlsruhe': '卡尔斯鲁厄', 'SV Elversberg': '艾禾斯堡', 'Elversberg': '艾禾斯堡', 'Wehen Wiesbaden': '威斯巴登', 'Wiesbaden': '威斯巴登',

    # ================== 意大利 ==================
    'Inter Milan': '国际米兰', 'Inter': '国际米兰', 'AC Milan': 'AC米兰', 'Milan': 'AC米兰', 'Juventus': '尤文图斯', 'Juventus FC': '尤文图斯', 
    'Napoli': '那不勒斯', 'Atalanta': '亚特兰大', 'AS Roma': '罗马', 'Roma': '罗马', 'Lazio': '拉齐奥', 'SS Lazio': '拉齐奥', 'Fiorentina': '佛罗伦萨',
    'Bologna': '博洛尼亚', 'Torino': '都灵', 'Monza': '蒙扎', 'Genoa': '热那亚', 'Lecce': '莱切', 'Sassuolo': '萨索洛', 'Udinese': '乌迪内斯', 'Cagliari': '卡利亚里', 
    'Empoli': '恩波利', 'Hellas Verona': '维罗纳', 'Verona': '维罗纳', 'Frosinone': '弗洛西诺内', 'Salernitana': '萨勒尼塔纳', 'Como': '科莫', 'Parma': '帕尔马', 
    'Venezia': '威尼斯', 'Cremonese': '克雷莫内塞', 'Sampdoria': '桑普多利亚', 'Palermo': '巴勒莫', 'Bari': '巴里', 'Pisa': '比萨',

    # ================== 西班牙 ==================
    'Real Madrid': '皇家马德里', 'Real Madrid CF': '皇家马德里', 'Barcelona': '巴塞罗那', 'FC Barcelona': '巴塞罗那', 'Atletico Madrid': '马德里竞技', 'Atletico': '马德里竞技', 
    'Girona': '赫罗纳', 'Girona FC': '赫罗纳', 'Athletic Bilbao': '毕尔巴鄂竞技', 'Athletic Club': '毕尔巴鄂竞技', 'Real Sociedad': '皇家社会', 'Real Betis': '皇家贝蒂斯', 
    'Villarreal': '比利亚雷亚尔', 'Valencia': '瓦伦西亚', 'Valencia CF': '瓦伦西亚', 'Sevilla': '塞维利亚', 'Sevilla FC': '塞维利亚', 'Osasuna': '奥萨苏纳', 'Getafe': '赫塔菲', 
    'Celta Vigo': '塞尔塔', 'Mallorca': '马洛卡', 'Las Palmas': '拉斯帕尔马斯', 'Rayo Vallecano': '巴列卡诺', 'Alaves': '阿拉维斯', 'Cadiz': '加的斯', 'Granada': '格拉纳达', 
    'Almeria': '阿尔梅里亚', 'Leganes': '莱加内斯', 'Real Valladolid': '巴拉多利德', 'Valladolid': '巴拉多利德', 'Espanyol': '西班牙人', 'Levante': '莱万特', 'Malaga': '马拉加', 
    'Deportivo La Coruna': '拉科鲁尼亚', 'Deportivo': '拉科鲁尼亚', 'Racing Santander': '桑坦德竞技', 'Elche': '埃尔切', 'Real Zaragoza': '皇家萨拉戈萨', 'Sporting Gijon': '希洪竞技',

    # ================== 法国 ==================
    'Paris Saint-Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼', 'Marseille': '马赛', 'Olympique Marseille': '马赛', 'Monaco': '摩纳哥', 'AS Monaco': '摩纳哥', 
    'Lille': '里尔', 'Lille OSC': '里尔', 'Nice': '尼斯', 'OGC Nice': '尼斯', 'Lens': '朗斯', 'RC Lens': '朗斯', 'Rennes': '雷恩', 'Stade Rennais': '雷恩', 
    'Lyon': '里昂', 'Olympique Lyonnais': '里昂', 'Reims': '兰斯', 'Montpellier': '蒙彼利埃', 'Toulouse': '图卢兹', 'Strasbourg': '斯特拉斯堡', 'Nantes': '南特',
    'Brest': '布雷斯特', 'Le Havre': '勒阿弗尔', 'Metz': '梅斯', 'Lorient': '洛里昂', 'Clermont Foot': '克莱蒙', 'Clermont': '克莱蒙', 'Saint-Etienne': '圣埃蒂安', 
    'AS Saint-Etienne': '圣埃蒂安', 'Auxerre': '欧塞尔', 'Angers': '昂热', 'SCO Angers': '昂热', 'Bordeaux': '波尔多', 'Girondins Bordeaux': '波尔多',

    # ================== 欧战常客 ==================
    'Ajax': '阿贾克斯', 'Ajax Amsterdam': '阿贾克斯', 'PSV Eindhoven': '埃因霍温', 'PSV': '埃因霍温', 'Feyenoord': '费耶诺德', 'Feyenoord Rotterdam': '费耶诺德', 
    'AZ Alkmaar': '阿尔克马尔', 'AZ': '阿尔克马尔', 'FC Twente': '特温特', 'Twente': '特温特', 'NEC Nijmegen': '奈梅亨', 'NEC': '奈梅亨', 'N.E.C.': '奈梅亨', 
    'Benfica': '本菲卡', 'SL Benfica': '本菲卡', 'Porto': '波尔图', 'FC Porto': '波尔图', 'Sporting CP': '葡萄牙体育', 'Sporting Lisbon': '葡萄牙体育', 'Braga': '布拉加', 'SC Braga': '布拉加',
    'Club Brugge': '布鲁日', 'Club Brugge KV': '布鲁日', 'Anderlecht': '安德莱赫特', 'RSC Anderlecht': '安德莱赫特', 'Genk': '亨克', 'KRC Genk': '亨克', 
    'Union St. Gilloise': '圣吉尔联', 'Union SG': '圣吉尔联', 'Union St.-Gilloise': '圣吉尔联', 'Union Saint-Gilloise': '圣吉尔联',
    'Celtic': '凯尔特人', 'Celtic FC': '凯尔特人', 'Rangers': '格拉斯哥流浪者', 'Rangers FC': '格拉斯哥流浪者',
    'Galatasaray': '加拉塔萨雷', 'Galatasaray SK': '加拉塔萨雷', 'Fenerbahce': '费内巴切', 'Fenerbahce SK': '费内巴切', 'Besiktas': '贝西克塔斯', 'Besiktas JK': '贝西克塔斯',
    'Red Bull Salzburg': '萨尔茨堡红牛', 'RB Salzburg': '萨尔茨堡红牛', 'FC Salzburg': '萨尔茨堡红牛', 'Sturm Graz': '格拉茨风暴', 'SK Sturm Graz': '格拉茨风暴',
    'Young Boys': '伯尔尼年轻人', 'BSC Young Boys': '伯尔尼年轻人', 'Basel': '巴塞尔', 'FC Basel': '巴塞尔', 'Copenhagen': '哥本哈根', 'FC Copenhagen': '哥本哈根', 
    'Midtjylland': '中日德兰', 'FC Midtjylland': '中日德兰', 'Slavia Prague': '布拉格斯拉维亚', 'SK Slavia Prague': '布拉格斯拉维亚', 'Sparta Prague': '布拉格斯巴达', 
    'Viktoria Plzen': '比尔森胜利', 'FC Viktoria Plzen': '比尔森胜利', 'Shakhtar Donetsk': '顿涅茨克矿工', 'FC Shakhtar Donetsk': '顿涅茨克矿工', 'Dynamo Kyiv': '基辅迪纳摩',
    'Bodo/Glimt': '博多闪耀', 'Molde': '莫尔德', 'Molde FK': '莫尔德', 'Rosenborg': '罗森博格', 'Viking FK': '维京', 'Viking': '维京',
    'Dinamo Zagreb': '萨格勒布迪纳摩', 'GNK Dinamo Zagreb': '萨格勒布迪纳摩', 'Red Star Belgrade': '贝尔格莱德红星', 'Crvena Zvezda': '贝尔格莱德红星',
    'Maccabi Tel Aviv': '特拉维夫马卡比', 'Maccabi Haifa': '海法马卡比', 'Hapoel Be\'er': '贝尔谢巴夏普尔', 'Hapoel Be\'er Sheva': '贝尔谢巴夏普尔',
    'Qarabag FK': '卡拉巴赫', 'Qarabag': '卡拉巴赫', 'Slovan Bratislava': '布拉迪斯拉发', 'Ferencvaros': '费伦茨瓦罗斯', 'Ferencváros': '费伦茨瓦罗斯',
    'Lech Poznan': '莱赫波兹南', 'Legia Warsaw': '华沙莱吉亚', 'Jagiellonia Bialystok': '乔治罗尼亚', 'Jagiellonia': '乔治罗尼亚',
    'Ludogorets': '卢多戈雷茨', 'Astana': '阿斯塔纳', 'Kairat Almaty': '阿拉木图凯拉特', 'Ararat-Armenia': '亚拉腊-亚美尼亚', 'Ararat Armenia': '亚拉腊-亚美尼亚',
    'NK Celje': '采列', 'Celje': '采列', 'Levski Sofia': '索菲亚列夫斯基', 'Levski': '索菲亚列夫斯基', 'Torreense': '托伦斯', 'CD Torreense': '托伦斯',

    # ================== 其他 ==================
    'Montevideo City Torque': '蒙得维的亚城力矩', 'Atletico Mineiro': '米内罗竞技', 'Atletico Nacional': '国民竞技', 'Deportivo Pasto': '帕斯托体育',
    'Brisbane Roar': '布里斯班狮吼', 'Perth Glory': '珀斯光荣', 'Melbourne City': '墨尔本城', 'Melbourne Victory': '墨尔本胜利', 'Sydney FC': '悉尼FC'
}

def translate_team_name(name):
    if not isinstance(name, str): return name
    cleaned_name = remove_accents(name.replace(" and ", " & ").strip())
    return TEAM_MAPPING.get(cleaned_name, cleaned_name)
