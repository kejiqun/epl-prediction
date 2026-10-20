# config.py - 系统全局配置文件

# 联赛配置：名称、ESPN代码、Odds API代码、对应的历史数据文件
LEAGUES = {
    "英超": {
        "espn_code": "eng.1",
        "odds_api_code": "soccer_epl",
        "hist_file": "epl_matches_10y.csv"
    },
    "西甲": {
        "espn_code": "esp.1",
        "odds_api_code": "soccer_spain_la_liga",
        "hist_file": None  # 暂时没有历史数据，未来补齐
    },
    "德甲": {
        "espn_code": "ger.1",
        "odds_api_code": "soccer_germany_bundesliga",
        "hist_file": None
    },
    "意甲": {
        "espn_code": "ita.1",
        "odds_api_code": "soccer_italy_serie_a",
        "hist_file": None
    },
    "欧冠": {
        "espn_code": "uefa.champions",
        "odds_api_code": "soccer_uefa_champs_league",
        "hist_file": None
    },
    "欧联": {
        "espn_code": "uefa.europa",
        "odds_api_code": "soccer_uefa_europa_league",
        "hist_file": None
    }
}

# 基础参数
RECEIVER_EMAIL = "308730509@qq.com"
MAX_GOALS = 5
