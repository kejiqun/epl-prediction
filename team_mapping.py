import unicodedata

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

TEAM_MAPPING = {
    # 英超及英冠
    'Arsenal': '阿森纳', 'Chelsea': '切尔西', 'Liverpool': '利物浦', 'Man City': '曼城', 'Man Utd': '曼联', 'Newcastle': '纽卡斯尔联',
    'Leeds': '利兹联', 'Burnley': '伯恩利', 'Sheffield United': '谢菲尔德联', 'Luton': '卢顿', 'Sunderland': '桑德兰', 'Middlesbrough': '米德尔斯堡',
    'Aston Villa': '阿斯顿维拉', 'Bournemouth': '伯恩茅斯', 'Brentford': '布伦特福德', 'Brighton': '布莱顿', 'Crystal Palace': '水晶宫',
    'Everton': '埃弗顿', 'Fulham': '富勒姆', 'Ipswich': '伊普斯维奇', 'Leicester': '莱斯特城', 'Nottingham Forest': '诺丁汉森林',
    'Southampton': '南安普敦', 'Tottenham': '热刺', 'Tottenham Hotspur': '热刺', 'West Ham': '西汉姆联', 'Wolves': '狼队', 'Wolverhampton': '狼队',
    'Manchester City': '曼城', 'Manchester United': '曼联', 'Newcastle United': '纽卡斯尔联', 'West Ham United': '西汉姆联',

    # 西甲
    'Real Madrid': '皇家马德里', 'Barcelona': '巴塞罗那', 'Atletico Madrid': '马德里竞技', 'Girona': '赫罗纳', 'Athletic Bilbao': '毕尔巴鄂竞技', 'Athletic Club': '毕尔巴鄂竞技',
    'Sevilla': '塞维利亚', 'Valencia': '瓦伦西亚', 'Villarreal': '比利亚雷亚尔', 'Real Sociedad': '皇家社会', 'Real Betis': '皇家贝蒂斯',
    'Osasuna': '奥萨苏纳', 'Celta Vigo': '塞尔塔', 'Rayo Vallecano': '巴列卡诺', 'Mallorca': '马洛卡', 'Getafe': '赫塔菲',
    'Alaves': '阿拉维斯', 'Las Palmas': '拉斯帕尔马斯', 'Espanyol': '西班牙人', 'Valladolid': '瓦拉多利德', 'Leganes': '莱加内斯',

    # 德甲/德乙
    'Bayern Munich': '拜仁慕尼黑', 'Borussia Dortmund': '多特蒙德', 'Bayer Leverkusen': '勒沃库森', 'RB Leipzig': '莱比锡红牛',
    'VfB Stuttgart': '斯图加特', 'Eintracht Frankfurt': '法兰克福', 'Hoffenheim': '霍芬海姆', 'Freiburg': '弗赖堡', 'Union Berlin': '柏林联合',
    'Borussia Monchengladbach': '门兴格拉德巴赫', 'Wolfsburg': '沃尔夫斯堡', 'Mainz': '美因茨', 'Augsburg': '奥格斯堡', 'Werder Bremen': '云达不莱梅',
    'Bochum': '波鸿', 'Heidenheim': '海登海姆', 'St. Pauli': '圣保利', 'Holstein Kiel': '基尔',

    # 意甲/意乙
    'Inter Milan': '国际米兰', 'Inter': '国际米兰', 'AC Milan': 'AC米兰', 'Milan': 'AC米兰', 'Juventus': '尤文图斯', 'Napoli': '那不勒斯', 
    'Atalanta': '亚特兰大', 'Roma': '罗马', 'Lazio': '拉齐奥', 'Fiorentina': '佛罗伦萨', 'Bologna': '博洛尼亚',
    'Torino': '都灵', 'Genoa': '热那亚', 'Udinese': '乌迪内斯', 'Monza': '蒙扎', 'Lecce': '莱切', 'Cagliari': '卡利亚里',
    'Verona': '维罗纳', 'Hellas Verona': '维罗纳', 'Empoli': '恩波利', 'Parma': '帕尔马', 'Como': '科莫', 'Venezia': '威尼斯',

    # 法甲
    'Paris Saint Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼', 'Marseille': '马赛', 'Monaco': '摩纳哥', 'Lille': '里尔', 'Lyon': '里昂',
    'Nice': '尼斯', 'Lens': '朗斯', 'Rennes': '雷恩', 'Reims': '兰斯', 'Toulouse': '图卢兹', 'Montpellier': '蒙彼利埃',
    'Strasbourg': '斯特拉斯堡', 'Nantes': '南特', 'Brest': '布雷斯特', 'Le Havre': '勒阿弗尔', 'Auxerre': '欧塞尔', 'Angers': '昂热', 'Saint-Etienne': '圣埃蒂安',

    # 北欧三国 (瑞典超、挪超、丹超)
    'Malmo FF': '马尔默', 'AIK': '索尔纳', 'Djurgarden': '佐加顿斯', 'Hacken': '赫根', 'IFK Goteborg': '哥德堡',
    'Bodo/Glimt': '博多格林特', 'Molde': '莫尔德', 'Rosenborg': '罗森博格', 'Brann': '布兰', 'Viking': '维京',
    'Copenhagen': '哥本哈根', 'FC Midtjylland': '中日德兰', 'Brondby': '布隆德比', 'AGF': '奥胡斯', 'Nordsjaelland': '北西兰',

    # 欧战常见
    'Celtic': '凯尔特人', 'Rangers': '格拉斯哥流浪者', 'Benfica': '本菲卡', 'Porto': '波尔图', 'Sporting CP': '葡萄牙体育',
    'Ajax': '阿贾克斯', 'PSV': '埃因霍温', 'Feyenoord': '费耶诺德', 'Club Brugge': '布鲁日', 'Galatasaray': '加拉塔萨雷',
    'Fenerbahce': '费内巴切', 'Olympiacos': '奥林匹亚科斯', 'Shakhtar Donetsk': '顿涅茨克矿工'
}

def translate_team_name(english_name):
    if not isinstance(english_name, str):
        return english_name
        
    name = english_name.strip()
    
    # 1. 先直接匹配
    if name in TEAM_MAPPING:
        return TEAM_MAPPING[name]
        
    # 2. 如果没匹配上，去除重音符号后再匹配 (处理 Atlético 变成 Atletico 的问题)
    clean_name = remove_accents(name)
    if clean_name in TEAM_MAPPING:
        return TEAM_MAPPING[clean_name]
        
    # 3. 如果还是没有，只能返回原英文名
    return name
