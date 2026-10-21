import unicodedata

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

TEAM_MAPPING = {
    # ================= 英超及英冠升降机 =================
    'Arsenal': '阿森纳', 'Arsenal FC': '阿森纳', 'Aston Villa': '阿斯顿维拉', 'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯',
    'Brentford': '布伦特福德', 'Brighton': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Chelsea': '切尔西', 'Crystal Palace': '水晶宫', 'Everton': '埃弗顿', 'Fulham': '富勒姆',
    'Ipswich': '伊普斯维奇', 'Ipswich Town': '伊普斯维奇', 'Leicester': '莱斯特城', 'Leicester City': '莱斯特城', 'Liverpool': '利物浦', 'Man City': '曼城', 'Manchester City': '曼城',
    'Man Utd': '曼联', 'Man United': '曼联', 'Manchester United': '曼联', 'Newcastle': '纽卡斯尔联', 'Newcastle United': '纽卡斯尔联',
    'Nott\'m Forest': '诺丁汉森林', 'Nottingham Forest': '诺丁汉森林', 'Southampton': '南安普顿', 'Spurs': '热刺', 'Tottenham': '热刺', 'Tottenham Hotspur': '热刺',
    'West Ham': '西汉姆联', 'West Ham United': '西汉姆联', 'Wolves': '狼队', 'Wolverhampton': '狼队', 'Wolverhampton Wanderers': '狼队',
    'Leeds United': '利兹联', 'Leeds': '利兹联', 'Hull City': '赫尔城', 'Hull': '赫尔城', 'Coventry City': '考文垂', 'Coventry': '考文垂',
    'Sunderland': '桑德兰', 'Burnley': '伯恩利', 'Sheffield United': '谢菲尔德联', 'Luton': '卢顿', 'Luton Town': '卢顿', 'Watford': '沃特福德', 'Norwich': '诺维奇', 'Norwich City': '诺维奇',
    'Fleetwood Town': '弗利特伍德', 'Bradford City': '布拉德福德', 'Peterborough United': '彼得堡联',

    # ================= 西甲 =================
    'Real Madrid': '皇家马德里', 'Barcelona': '巴塞罗那', 'Atletico Madrid': '马德里竞技', 'Girona': '赫罗纳',
    'Athletic Bilbao': '毕尔巴鄂竞技', 'Athletic Club': '毕尔巴鄂竞技', 'Real Sociedad': '皇家社会', 'Real Betis': '皇家贝蒂斯',
    'Villarreal': '比利亚雷亚尔', 'Valencia': '瓦伦西亚', 'Sevilla': '塞维利亚', 'Osasuna': '奥萨苏纳', 'Getafe': '赫塔菲',
    'Celta Vigo': '塞尔塔', 'Mallorca': '马洛卡', 'Las Palmas': '拉斯帕尔马斯', 'Rayo Vallecano': '巴列卡诺', 'Alaves': '阿拉维斯',
    'Cadiz': '加的斯', 'Granada': '格拉纳达', 'Almeria': '阿尔梅里亚', 'Levante': '莱万特', 'Malaga': '马拉加', 'Deportivo': '拉科鲁尼亚',

    # ================= 德甲 =================
    'Bayern Munich': '拜仁慕尼黑', 'Borussia Dortmund': '多特蒙德', 'Bayer Leverkusen': '勒沃库森', 'RB Leipzig': '莱比锡红牛',
    'VfB Stuttgart': '斯图加特', 'Eintracht Frankfurt': '法兰克福', 'SC Freiburg': '弗赖堡', 'TSG Hoffenheim': '霍芬海姆',
    'FC Augsburg': '奥格斯堡', 'Werder Bremen': '云达不莱梅', 'VfL Wolfsburg': '沃尔夫斯堡', 'Borussia Monchengladbach': '门兴格拉德巴赫',
    'Mainz': '美因茨', 'Mainz 05': '美因茨', 'Union Berlin': '柏林联合', 'VfL Bochum': '波鸿', 'FC Cologne': '科隆', 'Heidenheim': '海登海姆',
    'Darmstadt': '达姆施塔特', 'Schalke 04': '沙尔克04', 'Hamburg SV': '汉堡', 'SV Elversberg': '艾禾斯堡',

    # ================= 意甲 =================
    'Inter Milan': '国际米兰', 'Inter': '国际米兰', 'AC Milan': 'AC米兰', 'Milan': 'AC米兰', 'Juventus': '尤文图斯',
    'Napoli': '那不勒斯', 'Atalanta': '亚特兰大', 'AS Roma': '罗马', 'Roma': '罗马', 'Lazio': '拉齐奥', 'Fiorentina': '佛罗伦萨',
    'Bologna': '博洛尼亚', 'Torino': '都灵', 'Monza': '蒙扎', 'Genoa': '热那亚', 'Lecce': '莱切', 'Sassuolo': '萨索洛',
    'Udinese': '乌迪内斯', 'Cagliari': '卡利亚里', 'Empoli': '恩波利', 'Verona': '维罗纳', 'Frosinone': '弗洛西诺内', 'Salernitana': '萨勒尼塔纳',

    # ================= 法甲 =================
    'Paris Saint-Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼', 'Marseille': '马赛', 'Monaco': '摩纳哥',
    'Lille': '里尔', 'Nice': '尼斯', 'Lens': '朗斯', 'Rennes': '雷恩', 'Lyon': '里昂', 'Reims': '兰斯',
    'Montpellier': '蒙彼利埃', 'Toulouse': '图卢兹', 'Strasbourg': '斯特拉斯堡', 'Nantes': '南特', 'Brest': '布雷斯特', 'Le Havre': '勒阿弗尔', 'Como': '科莫',

    # ================= 欧战与南美/澳超常客 =================
    'Ajax': '阿贾克斯', 'PSV': '埃因霍温', 'PSV Eindhoven': '埃因霍温', 'Feyenoord': '费耶诺德', 'AZ Alkmaar': '阿尔克马尔', 'Twente': '特温特',
    'Benfica': '本菲卡', 'Porto': '波尔图', 'FC Porto': '波尔图', 'Sporting CP': '葡萄牙体育', 'Sporting Lisbon': '葡萄牙体育', 'Braga': '布拉加',
    'Celtic': '凯尔特人', 'Rangers': '格拉斯哥流浪者', 'Galatasaray': '加拉塔萨雷', 'Fenerbahce': '费内巴切', 'Besiktas': '贝西克塔斯',
    'Club Brugge': '布鲁日', 'Anderlecht': '安德莱赫特', 'Genk': '亨克', 'Union St. Gilloise': '圣吉尔联', 'Union SG': '圣吉尔联',
    'Red Bull Salzburg': '萨尔茨堡红牛', 'RB Salzburg': '萨尔茨堡红牛', 'FC Salzburg': '萨尔茨堡红牛', 'Sturm Graz': '格拉茨风暴', 'Young Boys': '伯尔尼年轻人', 'Basel': '巴塞尔',
    'Olympiacos': '奥林匹亚科斯', 'Panathinaikos': '帕纳辛奈科斯', 'AEK Athens': '雅典AEK', 'Copenhagen': '哥本哈根', 'FC Copenhagen': '哥本哈根', 'Midtjylland': '中日德兰',
    'Slavia Prague': '布拉格斯拉维亚', 'Sparta Prague': '布拉格斯巴达', 'Viktoria Plzen': '比尔森胜利', 'Shakhtar Donetsk': '顿涅茨克矿工', 'Dynamo Kyiv': '基辅迪纳摩',
    'Bodo/Glimt': '博多闪耀', 'Dinamo Zagreb': '萨格勒布迪纳摩', 'Red Star Belgrade': '贝尔格莱德红星', 'Crvena Zvezda': '贝尔格莱德红星',
    'Maccabi Tel Aviv': '特拉维夫马卡比', 'Maccabi Haifa': '海法马卡比', 'Qarabag FK': '卡拉巴赫', 'Qarabag': '卡拉巴赫', 'Slovan Bratislava': '布拉迪斯拉发', 'Sabah FK': '萨巴巴库',
    'Viking FK': '维京', 'Viking': '维京', 'Molde': '莫尔德', 'Rosenborg': '罗森博格', 'Malmo FF': '马尔默', 'AIK': 'AIK索尔纳',
    'Montevideo City Torque': '蒙得维的亚城力矩', 'Atletico Mineiro': '米内罗竞技', 'Atletico Nacional': '国民竞技', 'Deportivo Pasto': '帕斯托体育',
    'Brisbane Roar': '布里斯班狮吼', 'Perth Glory': '珀斯光荣', 'Brondby': '布隆德比'
}

def translate_team_name(name):
    if not isinstance(name, str): return name
    cleaned_name = remove_accents(name.replace(" and ", " & ").strip())
    return TEAM_MAPPING.get(cleaned_name, cleaned_name)
