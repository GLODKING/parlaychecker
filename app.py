import streamlit as st
from dataclasses import dataclass
from typing import Optional, List
import requests
import json
from datetime import datetime, timezone, timedelta
from itertools import combinations

# ==================================================
# 数据结构
# ==================================================

@dataclass
class Match:
    name: str
    match_date: Optional[str] = None

    handicap_open: float = 0.0
    handicap_live: float = 0.0

    total_open: float = 2.5
    total_live: float = 2.5

    corner_open: Optional[float] = None
    corner_live: Optional[float] = None
    corner_half: Optional[float] = None

    actual_result: Optional[str] = None
    actual_goals: Optional[int] = None
    actual_corners: Optional[int] = None

    @property
    def drift(self):
        return self.handicap_live - self.handicap_open

    @property
    def total_drift(self):
        return self.total_live - self.total_open

    @property
    def corner_change(self):
        if self.corner_open is None or self.corner_live is None:
            return 0
        return self.corner_live - self.corner_open

    @property
    def goal_tendency(self):
        if self.handicap_live <= -1.25 and self.total_open >= 2.75:
            return "big"
        if self.handicap_live >= -0.75 and self.total_open <= 2.5:
            return "small"
        return "neutral"


# ==================================================
# 联赛映射
# ==================================================

LEAGUE_MAP = {
    "英超": "soccer_epl",
    "西甲": "soccer_spain_la_liga",
    "意甲": "soccer_italy_serie_a",
    "德甲": "soccer_germany_bundesliga",
    "法甲": "soccer_france_ligue_one",
    "欧冠": "soccer_uefa_champs_league",
    "欧联杯": "soccer_uefa_europa_league",
    "世界杯": "soccer_fifa_world_cup",
}

# ==================================================
# 球队英文名 → 中文名翻译表（已大幅扩充）
# ==================================================

TEAM_TRANSLATION = {
    # 英超
    "Manchester City": "曼城", "Manchester United": "曼联", "Liverpool": "利物浦",
    "Chelsea": "切尔西", "Arsenal": "阿森纳", "Tottenham Hotspur": "热刺",
    "Newcastle United": "纽卡斯尔联", "Brighton and Hove Albion": "布莱顿",
    "Aston Villa": "阿斯顿维拉", "West Ham United": "西汉姆联",
    "Crystal Palace": "水晶宫", "Fulham": "富勒姆",
    "Wolverhampton Wanderers": "狼队", "Everton": "埃弗顿",
    "Nottingham Forest": "诺丁汉森林", "Brentford": "布伦特福德",
    "Leeds United": "利兹联", "Leicester City": "莱斯特城",
    "Southampton": "南安普顿", "Bournemouth": "伯恩茅斯",
    "Burnley": "伯恩利", "Sheffield United": "谢菲尔德联",
    "Luton Town": "卢顿", "Ipswich Town": "伊普斯维奇",
    # 西甲
    "Real Madrid": "皇马", "Barcelona": "巴萨", "Atletico Madrid": "马竞",
    "Sevilla": "塞维利亚", "Real Betis": "贝蒂斯", "Real Sociedad": "皇家社会",
    "Villarreal": "比利亚雷亚尔", "Athletic Club": "毕尔巴鄂竞技",
    "Valencia": "瓦伦西亚", "Osasuna": "奥萨苏纳", "Celta Vigo": "塞尔塔",
    "Rayo Vallecano": "巴列卡诺", "Getafe": "赫塔费", "Espanyol": "西班牙人",
    "Alaves": "阿拉维斯", "Granada": "格拉纳达", "Cadiz": "加的斯",
    "Mallorca": "马洛卡", "Girona": "赫罗纳", "Las Palmas": "拉斯帕尔马斯",
    # 意甲
    "Juventus": "尤文图斯", "Inter Milan": "国际米兰", "AC Milan": "AC米兰",
    "Napoli": "那不勒斯", "AS Roma": "罗马", "Lazio": "拉齐奥",
    "Atalanta": "亚特兰大", "Fiorentina": "佛罗伦萨", "Bologna": "博洛尼亚",
    "Torino": "都灵", "Genoa": "热那亚", "Monza": "蒙扎",
    "Udinese": "乌迪内斯", "Sassuolo": "萨索洛", "Empoli": "恩波利",
    "Lecce": "莱切", "Verona": "维罗纳", "Salernitana": "萨勒尼塔纳",
    "Cagliari": "卡利亚里", "Frosinone": "弗罗西诺内",
    # 德甲
    "Bayern Munich": "拜仁慕尼黑", "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "莱比锡红牛", "Bayer Leverkusen": "勒沃库森",
    "Eintracht Frankfurt": "法兰克福", "VfL Wolfsburg": "沃尔夫斯堡",
    "Borussia Monchengladbach": "门兴格拉德巴赫", "SC Freiburg": "弗赖堡",
    "TSG Hoffenheim": "霍芬海姆", "FC Augsburg": "奥格斯堡",
    "Mainz 05": "美因茨", "Werder Bremen": "云达不莱梅",
    "VfB Stuttgart": "斯图加特", "Union Berlin": "柏林联合",
    "FC Cologne": "科隆", "Bochum": "波鸿", "Heidenheim": "海登海姆",
    "Darmstadt 98": "达姆施塔特",
    # 法甲
    "Paris Saint-Germain": "巴黎圣日耳曼", "Olympique Marseille": "马赛",
    "Olympique Lyonnais": "里昂", "AS Monaco": "摩纳哥",
    "Lens": "朗斯", "Rennes": "雷恩", "Lille": "里尔",
    "Nice": "尼斯", "Strasbourg": "斯特拉斯堡", "Montpellier": "蒙彼利埃",
    "Toulouse": "图卢兹", "Nantes": "南特", "Reims": "兰斯",
    "Brest": "布雷斯特", "Clermont Foot": "克莱蒙", "Lorient": "洛里昂",
    "Auxerre": "欧塞尔", "Metz": "梅斯", "Le Havre": "勒阿弗尔",
    # 其他欧洲俱乐部
    "Porto": "波尔图", "Benfica": "本菲卡", "Sporting CP": "葡萄牙体育",
    "Ajax": "阿贾克斯", "PSV Eindhoven": "埃因霍温", "Feyenoord": "费耶诺德",
    "Celtic": "凯尔特人", "Rangers": "流浪者",
    "Shakhtar Donetsk": "顿涅茨克矿工", "Dynamo Kyiv": "基辅迪纳摩",
    "Galatasaray": "加拉塔萨雷", "Fenerbahce": "费内巴切", "Besiktas": "贝西克塔斯",
    "Club Brugge": "布鲁日", "Anderlecht": "安德莱赫特",
    "Red Bull Salzburg": "萨尔茨堡红牛", "Slavia Prague": "布拉格斯拉维亚",
    "Sparta Prague": "布拉格斯巴达", "Dinamo Zagreb": "萨格勒布迪纳摩",
    "Ferencvaros": "费伦茨瓦罗斯", "Young Boys": "年轻人", "FC Basel": "巴塞尔",
    "Olympiacos": "奥林匹亚科斯", "Panathinaikos": "帕纳辛奈科斯", "AEK Athens": "雅典AEK",
    # 南美俱乐部
    "Flamengo": "弗拉门戈", "Palmeiras": "帕尔梅拉斯", "Sao Paulo": "圣保罗",
    "River Plate": "河床", "Boca Juniors": "博卡青年",
    "Nacional": "民族", "Penarol": "佩纳罗尔",
    # 国家队
    "Netherlands": "荷兰", "Sweden": "瑞典", "Germany": "德国",
    "France": "法国", "England": "英格兰", "Spain": "西班牙",
    "Italy": "意大利", "Portugal": "葡萄牙", "Belgium": "比利时",
    "Croatia": "克罗地亚", "Denmark": "丹麦", "Switzerland": "瑞士",
    "Serbia": "塞尔维亚", "Poland": "波兰", "Ukraine": "乌克兰",
    "Austria": "奥地利", "Hungary": "匈牙利", "Norway": "挪威",
    "Scotland": "苏格兰", "Wales": "威尔士", "Turkey": "土耳其",
    "Greece": "希腊", "Russia": "俄罗斯", "Czech Republic": "捷克",
    "Slovakia": "斯洛伐克", "Slovenia": "斯洛文尼亚",
    "Bosnia and Herzegovina": "波黑", "Albania": "阿尔巴尼亚",
    "North Macedonia": "北马其顿", "Israel": "以色列",
    "Iceland": "冰岛", "Republic of Ireland": "爱尔兰",
    "Northern Ireland": "北爱尔兰", "Romania": "罗马尼亚",
    "Bulgaria": "保加利亚", "Montenegro": "黑山",
    "Finland": "芬兰", "Armenia": "亚美尼亚", "Georgia": "格鲁吉亚",
    "Estonia": "爱沙尼亚", "Latvia": "拉脱维亚", "Lithuania": "立陶宛",
    "Belarus": "白俄罗斯", "Moldova": "摩尔多瓦",
    "Azerbaijan": "阿塞拜疆", "Kazakhstan": "哈萨克斯坦",
    "Luxembourg": "卢森堡", "Malta": "马耳他", "Andorra": "安道尔",
    "San Marino": "圣马力诺", "Liechtenstein": "列支敦士登",
    "Faroe Islands": "法罗群岛", "Gibraltar": "直布罗陀",
    "Kosovo": "科索沃",
    # 南美
    "Brazil": "巴西", "Argentina": "阿根廷", "Uruguay": "乌拉圭",
    "Colombia": "哥伦比亚", "Chile": "智利", "Peru": "秘鲁",
    "Ecuador": "厄瓜多尔", "Venezuela": "委内瑞拉", "Bolivia": "玻利维亚",
    "Paraguay": "巴拉圭",
    # 非洲
    "Senegal": "塞内加尔", "Morocco": "摩洛哥", "Tunisia": "突尼斯",
    "Cameroon": "喀麦隆", "Ghana": "加纳", "Nigeria": "尼日利亚",
    "Ivory Coast": "科特迪瓦", "Egypt": "埃及", "Algeria": "阿尔及利亚",
    "South Africa": "南非", "Mali": "马里", "Burkina Faso": "布基纳法索",
    "DR Congo": "刚果民主共和国", "Congo": "刚果",
    "Guinea": "几内亚", "Zambia": "赞比亚", "Uganda": "乌干达",
    "Cape Verde": "佛得角", "Gabon": "加蓬", "Benin": "贝宁",
    "Tanzania": "坦桑尼亚", "Angola": "安哥拉", "Mozambique": "莫桑比克",
    "Namibia": "纳米比亚", "Sudan": "苏丹", "Libya": "利比亚",
    "Ethiopia": "埃塞俄比亚", "Kenya": "肯尼亚",
    # 亚洲
    "Japan": "日本", "South Korea": "韩国", "Iran": "伊朗",
    "Saudi Arabia": "沙特阿拉伯", "Australia": "澳大利亚",
    "Qatar": "卡塔尔", "United Arab Emirates": "阿联酋",
    "China": "中国", "Jordan": "约旦", "Iraq": "伊拉克",
    "Uzbekistan": "乌兹别克斯坦", "Syria": "叙利亚", "Oman": "阿曼",
    "Lebanon": "黎巴嫩", "Bahrain": "巴林", "Palestine": "巴勒斯坦",
    "Kuwait": "科威特", "Yemen": "也门", "Tajikistan": "塔吉克斯坦",
    "Kyrgyzstan": "吉尔吉斯斯坦", "Turkmenistan": "土库曼斯坦",
    "India": "印度", "Thailand": "泰国", "Vietnam": "越南",
    "Indonesia": "印度尼西亚", "Malaysia": "马来西亚",
    "Singapore": "新加坡", "Philippines": "菲律宾",
    "North Korea": "朝鲜", "Hong Kong": "中国香港",
    # 中北美洲
    "United States": "美国", "Mexico": "墨西哥", "Costa Rica": "哥斯达黎加",
    "Canada": "加拿大", "Panama": "巴拿马", "Jamaica": "牙买加",
    "Honduras": "洪都拉斯", "El Salvador": "萨尔瓦多",
    "Guatemala": "危地马拉", "Trinidad and Tobago": "特立尼达和多巴哥",
    "Haiti": "海地", "Dominican Republic": "多米尼加共和国",
    "Cuba": "古巴", "Nicaragua": "尼加拉瓜",
    # 大洋洲
    "New Zealand": "新西兰", "Fiji": "斐济", "Tahiti": "塔希提",
    "Solomon Islands": "所罗门群岛", "Papua New Guinea": "巴布亚新几内亚",
    "New Caledonia": "新喀里多尼亚",
}

def translate_team(name: str) -> str:
    return TEAM_TRANSLATION.get(name, name)


# ==================================================
# 分析函数
# ==================================================

def score_match(m: Match):
    score = 5
    if abs(m.drift) >= 1: score -= 3
    elif abs(m.drift) >= 0.5: score -= 2
    elif abs(m.drift) >= 0.25: score -= 1
    if abs(m.total_drift) >= 0.75: score -= 2
    elif abs(m.total_drift) >= 0.5: score -= 1
    if m.handicap_live <= -2 and abs(m.drift) >= 0.5: score -= 2
    return score

def score_to_level(score):
    if score >= 7: return "A"
    elif score >= 5: return "B"
    elif score >= 3: return "C"
    else: return "D"

def corner_style(m: Match):
    if m.corner_open is None: return "无数据"
    if m.handicap_live <= -1 and m.corner_half is not None and m.corner_half >= 4.5:
        return "压制型大角"
    if m.corner_open >= 9.5 and m.corner_live >= 9.5:
        return "对攻型大角"
    if m.corner_open <= 8.5 and m.corner_half is not None and m.corner_half <= 4:
        return "控球型小角"
    return "混沌盘"

def auto_fix(m: Match):
    if m.handicap_live <= -2:
        if abs(m.drift) >= 0.5: return "⚠️过热盘"
        return "4-6球"
    elif m.handicap_live <= -1: return "2-3球"
    else: return "胜/让平"

def detect_resonance(parlay_matches: List[Match]):
    big = small = 0
    for m in parlay_matches:
        if m.goal_tendency == "big": big += 1
        elif m.goal_tendency == "small": small += 1
    warnings = []
    if big >= 3: warnings.append(f"⚠️ 大球共振（{big}/4场）")
    if small >= 3: warnings.append(f"⚠️ 小球共振（{small}/4场）")
    return warnings

def bankroll_advice(avg_score):
    if avg_score >= 7: return "建议仓位：8%-10%"
    elif avg_score >= 5: return "建议仓位：5%-6%"
    else: return "建议仓位：2%-3%"


# ==================================================
# 复盘数据保存
# ==================================================

def save_replay_data(matches):
    replay = []
    for m in matches:
        replay.append({
            "name": m.name,
            "date": m.match_date,
            "handicap_open": m.handicap_open,
            "handicap_live": m.handicap_live,
            "total_open": m.total_open,
            "total_live": m.total_live,
            "corner_open": m.corner_open,
            "corner_live": m.corner_live,
            "corner_half": m.corner_half,
            "actual_result": m.actual_result,
            "actual_goals": m.actual_goals,
            "actual_corners": m.actual_corners,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
    return replay


# ==================================================
# The Odds API 拉取
# ==================================================

def fetch_odds_from_api(api_key, league_cn):
    sport = LEAGUE_MAP.get(league_cn)
    if not sport:
        st.error("不支持的联赛")
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {"apiKey": api_key, "regions": "eu", "markets": "spreads,totals", "oddsFormat": "decimal"}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            st.error(f"API 请求失败（{resp.status_code}）")
            return []
    except Exception as e:
        st.error(f"网络异常：{e}")
        return []
    data = resp.json()
    matches = []
    for game in data:
        home = game.get("home_team")
        away = game.get("away_team")
        commence = game.get("commence_time")
        if not home or not away: continue
        match_date = ""
        if commence:
            try:
                utc_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                beijing_time = utc_time.astimezone(timezone(timedelta(hours=8)))
                match_date = beijing_time.strftime("%Y-%m-%d")
            except:
                pass
        spreads = totals = None
        for book in game.get("bookmakers", []):
            for market in book.get("markets", []):
                if market["key"] == "spreads" and market.get("outcomes"):
                    spreads = market["outcomes"]
                elif market["key"] == "totals" and market.get("outcomes"):
                    totals = market["outcomes"]
        if spreads and totals:
            handicap = spreads[0].get("point", 0)
            total_line = totals[0].get("point", 2.5)
            matches.append({
                "name": f"{translate_team(home)} vs {translate_team(away)}",
                "date": match_date,
                "handicap_open": handicap,
                "handicap_live": handicap,
                "total_open": total_line,
                "total_live": total_line,
                "corner_open": None,
                "corner_live": None,
                "corner_half": None
            })
    return matches


# ==================================================
# 智能组串
# ==================================================

def find_best_parlay(all_matches: List[Match], top_n=4):
    scored = [(m, score_match(m)) for m in all_matches]
    scored.sort(key=lambda x: x[1], reverse=True)
    filtered = [(m, s) for m, s in scored if s >= 3]
    best = filtered[:top_n]
    return [m for m, _ in best]

def find_all_valid_parlays(all_matches: List[Match], parlay_size=4):
    scored = [(m, score_match(m)) for m in all_matches]
    valid = [(m, s) for m, s in scored if s >= 3]
    if len(valid) < parlay_size: return []
    combos = []
    for combo in combinations(valid, parlay_size):
        total = sum(s for _, s in combo)
        matches_in = [m for m, _ in combo]
        combos.append((total, matches_in))
    combos.sort(key=lambda x: x[0], reverse=True)
    return [matches for _, matches in combos]


# ==================================================
# Streamlit 界面
# ==================================================

st.set_page_config(page_title="多场一体检器 Pro", page_icon="⚽", layout="wide")
st.title("⚽ 多场一体检器 Pro")
st.caption("支持最多10场 | 自动评分排序 | 智能推荐最佳串关")

mode = st.radio("选择模式", ["📝 赛前体检模式", "📊 赛后复盘模式"], horizontal=True)

with st.expander("📡 一键导入比赛盘口（免费 API）", expanded=False):
    st.markdown("**说明：** 注册 [the-odds-api.com](https://the-odds-api.com) 获取 API Key")
    api_key = st.text_input("API Key", type="password")
    league_cn = st.selectbox("选择联赛", list(LEAGUE_MAP.keys()))
    if st.button("📥 自动加载盘口"):
        if not api_key:
            st.warning("请输入 API Key")
        else:
            with st.spinner("拉取中..."):
                raw = fetch_odds_from_api(api_key, league_cn)
                if raw:
                    limited = raw[:10]
                    st.session_state["api_matches"] = limited
                    st.session_state["match_count"] = min(len(limited), 10)
                    for i, m in enumerate(limited):
                        st.session_state[f"name{i}"] = m["name"]
                        st.session_state[f"date{i}"] = m["date"]
                        st.session_state[f"ho{i}"] = m["handicap_open"]
                        st.session_state[f"hl{i}"] = m["handicap_live"]
                        st.session_state[f"to{i}"] = m["total_open"]
                        st.session_state[f"tl{i}"] = m["total_live"]
                        st.session_state[f"co{i}"] = 9.0
                        st.session_state[f"cl{i}"] = 9.0
                        st.session_state[f"ch{i}"] = 4.0
                    st.success(f"已加载 {len(limited)} 场比赛（中文名已自动翻译）")
                    st.rerun()

st.divider()

if "match_count" not in st.session_state:
    st.session_state["match_count"] = 4
safe_count = min(st.session_state.get("match_count", 4), 10)

match_count = st.number_input("今天有几场比赛？", min_value=2, max_value=10, value=safe_count, step=1)
st.session_state["match_count"] = match_count

use_corner = st.checkbox("📐 启用角球分析", value=True)

api_data = st.session_state.get("api_matches", [])

st.subheader("📝 比赛数据输入")
matches = []

for i in range(match_count):
    with st.expander(f"比赛 {i+1}", expanded=(i < 4)):
        def_name = f"比赛{i+1}"
        def_date = ""
        def_ho, def_hl, def_to, def_tl = 0.0, 0.0, 2.5, 2.5
        def_co, def_cl, def_ch = 9.0, 9.0, 4.0
        if i < len(api_data):
            m = api_data[i]
            def_name = m["name"]
            def_date = m["date"]
            def_ho = m["handicap_open"]
            def_hl = m["handicap_live"]
            def_to = m["total_open"]
            def_tl = m["total_live"]

        if f"name{i}" not in st.session_state or not st.session_state[f"name{i}"]:
            st.session_state[f"name{i}"] = def_name
        if f"date{i}" not in st.session_state:
            st.session_state[f"date{i}"] = def_date
        if f"ho{i}" not in st.session_state:
            st.session_state[f"ho{i}"] = def_ho
        if f"hl{i}" not in st.session_state:
            st.session_state[f"hl{i}"] = def_hl
        if f"to{i}" not in st.session_state:
            st.session_state[f"to{i}"] = def_to
        if f"tl{i}" not in st.session_state:
            st.session_state[f"tl{i}"] = def_tl
        if use_corner:
            if f"co{i}" not in st.session_state:
                st.session_state[f"co{i}"] = def_co
            if f"cl{i}" not in st.session_state:
                st.session_state[f"cl{i}"] = def_cl
            if f"ch{i}" not in st.session_state:
                st.session_state[f"ch{i}"] = def_ch

        col1, col2, col3, col4, col5 = st.columns(5)
        name = col1.text_input("比赛名称", key=f"name{i}")
        match_date = col2.text_input("日期", key=f"date{i}", placeholder="YYYY-MM-DD")
        h_open = col3.number_input("初盘让球", step=0.25, key=f"ho{i}")
        h_live = col4.number_input("即时让球", step=0.25, key=f"hl{i}")
        t_open = col5.number_input("大小球初盘", step=0.25, key=f"to{i}")

        col6, col7 = st.columns(2)
        t_live = col6.number_input("大小球即时盘", step=0.25, key=f"tl{i}")

        if use_corner:
            colc1, colc2, colc3 = st.columns(3)
            c_open = colc1.number_input("角球初盘", step=0.5, key=f"co{i}")
            c_live = colc2.number_input("角球即时盘", step=0.5, key=f"cl{i}")
            c_half = colc3.number_input("上半场角球", step=0.5, key=f"ch{i}")
        else:
            c_open = c_live = c_half = None

        actual_result = None
        actual_goals = None
        actual_corners = None
        if mode == "📊 赛后复盘模式":
            col_r1, col_r2, col_r3 = st.columns(3)
            result_map = {"主胜": "home", "平局": "draw", "客胜": "away"}
            actual_result_str = col_r1.selectbox("赛果", list(result_map.keys()), key=f"res{i}")
            actual_result = result_map[actual_result_str]
            actual_goals = col_r2.number_input("实际进球", value=2, min_value=0, step=1, key=f"g{i}")
            actual_corners = col_r3.number_input("实际角球", value=9, min_value=0, step=1, key=f"crn{i}")

        matches.append(Match(
            name=name, match_date=match_date,
            handicap_open=h_open, handicap_live=h_live,
            total_open=t_open, total_live=t_live,
            corner_open=c_open, corner_live=c_live, corner_half=c_half,
            actual_result=actual_result, actual_goals=actual_goals, actual_corners=actual_corners
        ))

st.divider()

if st.button("🔍 开始分析全部比赛"):
    scored_list = [(m, score_match(m), score_to_level(score_match(m))) for m in matches]
    scored_list.sort(key=lambda x: x[1], reverse=True)
    st.header("📊 全部比赛评分排序")
    for m, s, lv in scored_list:
        date_str = f"({m.match_date})" if m.match_date else ""
        st.write(f"**{m.name}** {date_str} | 评分：{s} | 评级：{lv} | 修单：{auto_fix(m)}")
    st.divider()
    best_four = find_best_parlay(matches)
    st.header("🏆 系统推荐最优四串一")
    if len(best_four) < 4:
        st.warning(f"当前有效比赛不足 4 场（仅 {len(best_four)} 场符合要求）")
    else:
        total_parlay_score = sum(score_match(m) for m in best_four)
        avg_parlay_score = total_parlay_score / 4
        st.success(f"推荐 {len(best_four)} 场比赛，平均评分：{avg_parlay_score:.1f}")
        for m in best_four:
            st.write(f"✅ **{m.name}** | 评分：{score_match(m)} | {auto_fix(m)}")
        warnings = detect_resonance(best_four)
        if warnings:
            for w in warnings: st.warning(w)
        st.info(bankroll_advice(avg_parlay_score))
    st.divider()
    all_combos = find_all_valid_parlays(matches)
    if all_combos:
        st.header("📋 所有有效四串一排名（前 5）")
        for idx, combo in enumerate(all_combos[:5]):
            total_s = sum(score_match(m) for m in combo)
            names = " | ".join([m.name for m in combo])
            st.write(f"**#{idx+1}** 评分：{total_s} → {names}")
    st.divider()
    if use_corner:
        st.header("📐 角球风格一览")
        for m in matches:
            st.write(f"**{m.name}** ：{corner_style(m)}")
    if mode == "📊 赛后复盘模式":
        st.divider()
        st.header("📋 实际赛果记录")
        for m in matches:
            date_str = f"({m.match_date})" if m.match_date else ""
            result_names = {"home": "主胜", "draw": "平局", "away": "客胜"}
            actual = result_names.get(m.actual_result, "未填")
            goals = m.actual_goals if m.actual_goals is not None else "-"
            corners = m.actual_corners if m.actual_corners is not None else "-"
            st.write(f"**{m.name}** {date_str}：{actual}，进球 {goals}，角球 {corners}")
        if st.button("💾 保存复盘数据为 JSON"):
            replay_json = json.dumps(save_replay_data(matches), ensure_ascii=False, indent=2)
            st.download_button(
                label="下载复盘记录",
                data=replay_json,
                file_name=f"replay_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json"
            )
else:
    st.info("👆 设定比赛场次（2~10场），填好数据后点击按钮生成报告。")