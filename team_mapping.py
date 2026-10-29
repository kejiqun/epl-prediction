import unicodedata

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

TEAM_MAPPING = {
    # 英超及英冠
    'Arsenal': '阿森纳', 'Chelsea': '切尔西', 'Liverpool': '利物浦', 'Man City': '曼城', 'Man Utd': '曼联', 'Newcastle': '纽卡斯尔联', 'Tottenham': '热刺', 'West Ham': '西汉姆联', 'Wolves': '狼队', 'Brighton': '布莱顿', 'Crystal Palace': '水晶宫', 'Everton': '埃弗顿', 'Fulham': '富勒姆', 'Aston Villa': '阿斯顿维拉', 'Bournemouth': '伯恩茅斯', 'Brentford': '布伦特福德', 'Leicester': '莱斯特城', 'Ipswich': '伊普斯维奇', 'Southampton': '南安普顿', 'Nott\'m Forest': '诺丁汉森林',
    'Leeds': '利兹联', 'Burnley': '伯恩利', 'Sheffield United': '谢菲尔德联', 'Luton': '卢顿', 'Sunderland': '桑德兰', 'Middlesbrough': '米德尔斯堡', 'West Brom': '西布罗姆维奇', 'Norwich': '诺维奇', 'Hull': '赫尔城', 'Coventry': '考文垂', 'Watford': '沃特福德', 'Bristol City': '布里斯托尔城', 'Swansea': '斯旺西', 'Cardiff': '卡迪夫城', 'Preston': '普雷斯顿', 'Millwall': '米尔沃尔', 'QPR': '女王公园巡游者', 'Stoke': '斯托克城', 'Blackburn': '布莱克本', 'Sheffield Wed': '谢周三', 'Plymouth': '普利茅斯', 'Derby': '德比郡', 'Birmingham': '伯明翰', 'Huddersfield': '哈德斯菲尔德', 'Charlton': '查尔顿', 'Bolton': '博尔顿',

    # 西甲
    'Real Madrid': '皇家马德里', 'Barcelona': '巴塞罗那', 'Atletico Madrid': '马德里竞技', 'Girona': '赫罗纳', 'Athletic Bilbao': '毕尔巴鄂竞技', 'Real Sociedad': '皇家社会', 'Real Betis': '皇家贝蒂斯', 'Villarreal': '比利亚雷亚尔', 'Valencia': '瓦伦西亚', 'Sevilla': '塞维利亚', 'Osasuna': '奥萨苏纳', 'Getafe': '赫塔菲', 'Celta Vigo': '塞尔塔', 'Mallorca': '马洛卡', 'Las Palmas': '拉斯帕尔马斯', 'Rayo Vallecano': '巴列卡诺', 'Alaves': '阿拉维斯', 'Cadiz': '加的斯', 'Granada': '格拉纳达', 'Almeria': '阿尔梅里亚', 'Leganes': '莱加内斯', 'Valladolid': '巴拉多利德', 'Espanyol': '西班牙人', 'Levante': '莱万特', 'Malaga': '马拉加', 'Deportivo': '拉科鲁尼亚', 'Racing Santander': '桑坦德竞技', 'Elche': '埃尔切', 'Zaragoza': '皇家萨拉戈萨', 'Sporting Gijon': '希洪竞技',

    # 德甲/德乙
    'Bayern Munich': '拜仁慕尼黑', 'Borussia Dortmund': '多特蒙德', 'Bayer Leverkusen': '勒沃库森', 'RB Leipzig': '莱比锡红牛', 'VfB Stuttgart': '斯图加特', 'Eintracht Frankfurt': '法兰克福', 'SC Freiburg': '弗赖堡', 'TSG Hoffenheim': '霍芬海姆', 'FC Augsburg': '奥格斯堡', 'Werder Bremen': '云达不莱梅', 'VfL Wolfsburg': '沃尔夫斯堡', 'Borussia Monchengladbach': '门兴格拉德巴赫', 'Mainz': '美因茨', 'Union Berlin': '柏林联合', 'VfL Bochum': '波鸿', 'FC Cologne': '科隆', 'Heidenheim': '海登海姆', 'Darmstadt': '达姆施塔特', 'Schalke 04': '沙尔克04', 'Hamburg': '汉堡', 'Dusseldorf': '杜塞尔多夫', 'Hannover': '汉诺威96', 'Nurnberg': '纽伦堡', 'Hertha': '柏林赫塔', 'Paderborn': '帕德博恩', 'Furth': '菲尔特', 'Kiel': '基尔', 'Karlsruhe': '卡尔斯鲁厄', 'Elversberg': '艾禾斯堡', 'Wiesbaden': '威斯巴登', 'Rostock': '罗斯托克', 'Bielefeld': '比勒菲尔德', 'St Pauli': '圣保利', 'Holstein Kiel': '基尔',

    # 意甲/意乙
    'Inter Milan': '国际米兰', 'AC Milan': 'AC米兰', 'Juventus': '尤文图斯', 'Napoli': '那不勒斯', 'Atalanta': '亚特兰大', 'AS Roma': '罗马', 'Lazio': '拉齐奥', 'Fiorentina': '佛罗伦萨', 'Bologna': '博洛尼亚', 'Torino': '都灵', 'Monza': '蒙扎', 'Genoa': '热那亚', 'Lecce': '莱切', 'Sassuolo': '萨索洛', 'Udinese': '乌迪内斯', 'Cagliari': '卡利亚里', 'Empoli': '恩波利', 'Verona': '维罗纳', 'Frosinone': '弗洛西诺内', 'Salernitana': '萨勒尼塔纳', 'Como': '科莫', 'Parma': '帕尔马', 'Venezia': '威尼斯', 'Cremonese': '克雷莫内塞', 'Sampdoria': '桑普多利亚', 'Palermo': '巴勒莫', 'Bari': '巴里', 'Pisa': '比萨',

    # 法甲/法乙
    'Paris Saint-Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼', 'Marseille': '马赛', 'Monaco': '摩纳哥', 'Lille': '里尔', 'Nice': '尼斯', 'Lens': '朗斯', 'Rennes': '雷恩', 'Lyon': '里昂', 'Reims': '兰斯', 'Montpellier': '蒙彼利埃', 'Toulouse': '图卢兹', 'Strasbourg': '斯特拉斯堡', 'Nantes': '南特', 'Brest': '布雷斯特', 'Le Havre': '勒阿弗尔', 'Metz': '梅斯', 'Lorient': '洛里昂', 'Clermont': '克莱蒙', 'Saint-Etienne': '圣埃蒂安', 'Auxerre': '欧塞尔', 'Angers': '昂热', 'Bordeaux': '波尔多', 'Amiens': '亚眠', 'Guingamp': '甘冈', 'Sochaux': '索肖', 'Caen': '卡昂', 'Bastia': '巴斯蒂亚', 'Ajaccio': '阿雅克肖', 'Grenoble': '格勒诺布尔', 'Pau': '波城', 'Rodez': '罗德兹', 'Dunkerque': '敦刻尔克', 'Concarneau': '孔卡尔诺', 'Valenciennes': '瓦伦谢纳', 'Troyes': '特鲁瓦', 'Quevilly-Rouen': '克维伊',

    # 北欧三国
    'Malmo': '马尔默', 'AIK': 'AIK索尔纳', 'Djurgarden': '佐加顿斯', 'Hammarby': '哈马比', 'Goteborg': 'IFK哥德堡', 'Helsingborg': '赫尔辛堡', 'Elfsborg': '埃尔夫斯堡', 'Sirius': '天狼星', 'Norrkoping': '北雪平',
    'Bodo/Glimt': '博多闪耀', 'Molde': '莫尔德', 'Rosenborg': '罗森博格', 'Viking': '维京', 'Lillestrom': '利勒斯特罗姆', 'Brann': '布兰', 'Tromso': '特罗姆瑟', 'Valerenga': '瓦勒伦加', 'Fredrikstad': '费德列斯达',
    'Copenhagen': '哥本哈根', 'Brondby': '布隆德比', 'Midtjylland': '中日德兰', 'AGF': '奥胡斯', 'Silkeborg': '锡尔克堡', 'Nordsjaelland': '北西兰', 'Randers': '兰纳斯', 'Viborg': '维堡', 'Vejle': '瓦埃勒',

    # 欧战常客及其他
    'Ajax': '阿贾克斯', 'PSV': '埃因霍温', 'Feyenoord': '费耶诺德', 'AZ Alkmaar': '阿尔克马尔', 'Twente': '特温特', 'NEC': '奈梅亨', 'Utrecht': '乌德勒支', 'Go Ahead Eagles': '前进之鹰', 'Sparta Rotterdam': '鹿特丹斯巴达', 'Heerenveen': '海伦芬', 'Zwolle': '兹沃勒', 'Sittard': '锡塔德幸运', 'Almere City': '阿尔梅勒城', 'Heracles': '赫拉克勒斯', 'Waalwijk': '瓦尔韦克', 'Vitesse': '维特斯', 'Excelsior': '埃克塞尔西奥', 'Volendam': '沃伦丹', 'Willem II': '威廉二世', 'Groningen': '格罗宁根', 'Roda JC': '罗达JC', 'Den Haag': '海牙', 'Venlo': '芬洛', 'Emmen': '埃门', 'Cambuur': '坎布尔',
    'Benfica': '本菲卡', 'Porto': '波尔图', 'Sporting CP': '葡萄牙体育', 'Braga': '布拉加', 'Vitoria Guimaraes': '吉马良斯',
    'Club Brugge': '布鲁日', 'Anderlecht': '安德莱赫特', 'Genk': '亨克', 'Union SG': '圣吉尔联', 'Antwerp': '安特卫普', 'Gent': '根特', 'Standard Liege': '标准列日',
    'Celtic': '凯尔特人', 'Rangers': '格拉斯哥流浪者',
    'Galatasaray': '加拉塔萨雷', 'Fenerbahce': '费内巴切', 'Besiktas': '贝西克塔斯', 'Trabzonspor': '特拉布宗体育',
    'Olympiacos': '奥林匹亚科斯', 'Panathinaikos': '帕纳辛奈科斯', 'AEK Athens': '雅典AEK', 'PAOK': '塞萨洛尼基',
    'Red Bull Salzburg': '萨尔茨堡红牛', 'Sturm Graz': '格拉茨风暴', 'Rapid Vienna': '维也纳快速', 'LASK': 'LASK林茨',
    'Young Boys': '伯尔尼年轻人', 'Basel': '巴塞尔', 'Servette': '塞尔维特', 'Lugano': '卢加诺', 'Lucerne': '卢塞恩', 'St. Gallen': '圣加仑', 'Sion': '锡永', 'Grasshopper': '草蜢', 'Lausanne': '洛桑体育',
    'Dinamo Zagreb': '萨格勒布迪纳摩', 'Red Star Belgrade': '贝尔格莱德红星', 'Partizan': '贝尔格莱德游击',
    'Shakhtar Donetsk': '顿涅茨克矿工', 'Dynamo Kyiv': '基辅迪纳摩',
    'Slavia Prague': '布拉格斯拉维亚', 'Sparta Prague': '布拉格斯巴达', 'Viktoria Plzen': '比尔森胜利',
    'Lech Poznan': '莱赫波兹南', 'Legia Warsaw': '华沙莱吉亚', 'Jagiellonia': '乔治罗尼亚',
    'Ferencvaros': '费伦茨瓦罗斯', 'Qarabag': '卡拉巴赫', 'Slovan Bratislava': '布拉迪斯拉发',
    'Maccabi Tel Aviv': '特拉维夫马卡比', 'Maccabi Haifa': '海法马卡比', 'Hapoel Be\'er Sheva': '贝尔谢巴夏普尔'
}

def translate_team_name(name):
    if not isinstance(name, str): return name
    cleaned_name = remove_accents(name.replace(" and ", " & ").strip())
    return TEAM_MAPPING.get(cleaned_name, cleaned_name)
