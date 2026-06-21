import streamlit as st
from dataclasses import dataclass
from typing import Optional, List
import requests
import json
from datetime import datetime, timezone, timedelta

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
# 球队英文名 → 中文名翻译表（可自行扩充）
# ==================================================

TEAM_TRANSLATION = {
    # 英超
    "Manchester City": "曼城",
    "Manchester United": "曼联",
    "Liverpool": "利物浦",
    "Chelsea": "切尔西",
    "Arsenal": "阿森纳",
    "Tottenham Hotspur": "热刺",
    "Newcastle United": "纽卡斯尔联",
    "Brighton and Hove Albion": "布莱顿",
    "Aston Villa": "阿斯顿维拉",
    "West Ham United": "西汉姆联",
    "Crystal Palace": "水晶宫",
    "Fulham": "富勒姆",
    "Wolverhampton Wanderers": "狼队",
    "Everton": "埃弗顿",
    "Nottingham Forest": "诺丁汉森林",
    "Brentford": "布伦特福德",
    "Leeds United": "利兹联",
    "Leicester City": "莱斯特城",
    "Southampton": "南安普顿",
    "Bournemouth": "伯恩茅斯",
    # 西甲
    "Real Madrid": "皇马",
    "Barcelona": "巴萨",
    "Atletico Madrid": "马竞",
    "Sevilla": "塞维利亚",
    "Real Betis": "贝蒂斯",
    "Real Sociedad": "皇家社会",
    "Villarreal": "比利亚雷亚尔",
    "Athletic Club": "毕尔巴鄂竞技",
    "Valencia": "瓦伦西亚",
    # 意甲
    "Juventus": "尤文图斯",
    "Inter Milan": "国际米兰",
    "AC Milan": "AC米兰",
    "Napoli": "那不勒斯",
    "AS Roma": "罗马",
    "Lazio": "拉齐奥",
    "Atalanta": "亚特兰大",
    "Fiorentina": "佛罗伦萨",
    # 德甲
    "Bayern Munich": "拜仁慕尼黑",
    "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "莱比锡红牛",
    "Bayer Leverkusen": "勒沃库森",
    "Eintracht Frankfurt": "法兰克福",
    # 法甲
    "Paris Saint-Germain": "巴黎圣日耳曼",
    "Olympique Marseille": "马赛",
    "Olympique Lyonnais": "里昂",
    "AS Monaco": "摩纳哥",
    # 国家队（世界杯等）
    "Netherlands": "荷兰",
    "Sweden": "瑞典",
    "Germany": "德国",
    "Ivory Coast": "科特迪瓦",
    "Ecuador": "厄瓜多尔",
    "Curacao": "库拉索",
    "Tunisia": "突尼斯",
    "Japan": "日本",
    "Spain": "西班牙",
    "Saudi Arabia": "沙特阿拉伯",
    "Belgium": "比利时",
    "Iran": "伊朗",
    "Uruguay": "乌拉圭",
    "Cape Verde": "佛得角",
    "New Zealand": "新西兰",
    "Egypt": "埃及",
    "France": "法国",
    "England": "英格兰",
    "Brazil": "巴西",
    "Argentina": "阿根廷",
    "Portugal": "葡萄牙",
    "Croatia": "克罗地亚",
    "Morocco": "摩洛哥",
    "Senegal": "塞内加尔",
    "United States": "美国",
    "Mexico": "墨西哥",
    # 继续添加...
}

def translate_team(name: str) -> str:
    """英文队名转中文，找不到则保持原样"""
    return TEAM_TRANSLATION.get(name, name)


# ==================================================
# 分析函数
# ==================================================

def score_match(m: Match):
    score = 5
    if abs(m.drift) >= 1:
        score -= 3
    elif abs(m.drift) >= 0.5:
        score -= 2
    elif abs(m.drift) >= 0.25:
        score -= 1
    if abs(m.total_drift) >= 0.75:
        score -= 2
    elif abs(m.total_drift) >= 0.5:
        score -= 1
    if m.handicap_live <= -2 and abs(m.drift) >= 0.5:
        score -= 2
    if score >= 7:
        level = "A"
    elif score >= 5:
        level = "B"
    elif score >= 3:
        level = "C"
    else:
        level = "D"
    return score, level


def corner_style(m: Match):
    if m.corner_open is None:
        return "无数据"
    if m.handicap_live <= -1 and m.corner_half is not None and m.corner_half >= 4.5:
        return "压制型大角"
    if m.corner_open >= 9.5 and m.corner_live >= 9.5:
        return "对攻型大角"
    if m.corner_open <= 8.5 and m.corner_half is not None and m.corner_half <= 4:
        return "控球型小角"
    return "混沌盘"


def auto_fix(m: Match):
    if m.handicap_live <= -2:
        if abs(m.drift) >= 0.5:
            return "⚠️过热盘（建议回避）"
        return "4-6球"
    elif m.handicap_live <= -1:
        return "2-3球"
    else:
        return "胜 / 让平"


def detect_resonance(matches: List[Match]):
    big = small = 0
    for m in matches:
        if m.goal_tendency == "big":
            big += 1
        elif m.goal_tendency == "small":
            small += 1
    warnings = []
    if big >= 3:
        warnings.append(f"⚠️ 大球共振风险（{big}/4 场倾向大球）")
    if small >= 3:
        warnings.append(f"⚠️ 小球共振风险（{small}/4 场倾向小球）")
    return warnings


def bankroll_advice(avg_score):
    if avg_score >= 7:
        return "建议仓位：8%-10%"
    elif avg_score >= 5:
        return "建议仓位：5%-6%"
    else:
        return "建议仓位：2%-3%"


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
# The Odds API 拉取（带日期 + 中文翻译）
# ==================================================

def fetch_odds_from_api(api_key, league_cn):
    sport = LEAGUE_MAP.get(league_cn)
    if not sport:
        st.error("不支持的联赛")
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "spreads,totals",
        "oddsFormat": "decimal"
    }
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
        if not home or not away:
            continue

        # 日期处理：转为北京时间 YYYY-MM-DD
        match_date = ""
        if commence:
            try:
                utc_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                beijing_time = utc_time.astimezone(timezone(timedelta(hours=8)))
                match_date = beijing_time.strftime("%Y-%m-%d")
            except:
                pass

        # 让球和大小球
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
# Streamlit 界面
# ==================================================

st.set_page_config(page_title="四串一体检器 Pro v3", page_icon="⚽", layout="wide")
st.title("⚽ 四串一体检器 Pro v3")
st.caption("盘口分析 / 角球分析 / 风险控制 / 赛后复盘（自动中文队名）")

mode = st.radio("选择模式", ["📝 赛前体检模式", "📊 赛后复盘模式"], horizontal=True)

# ---------- 一键导入 ----------
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
                    for i, m in enumerate(raw[:4]):
                        st.session_state[f"name{i}"] = m["name"]
                        st.session_state[f"date{i}"] = m["date"]
                        st.session_state[f"ho{i}"] = m["handicap_open"]
                        st.session_state[f"hl{i}"] = m["handicap_live"]
                        st.session_state[f"to{i}"] = m["total_open"]
                        st.session_state[f"tl{i}"] = m["total_live"]
                        st.session_state[f"co{i}"] = 9.0
                        st.session_state[f"cl{i}"] = 9.0
                        st.session_state[f"ch{i}"] = 4.0
                    st.success(f"已加载 {len(raw[:4])} 场比赛，已自动翻译中文队名")

st.divider()

# ---------- 角球开关 ----------
use_corner = st.checkbox("📐 启用角球分析", value=True)

# ---------- 四场比赛输入 ----------
matches = []
defaults = [
    ("比赛1", "", -0.75, -0.75, 2.75, 3.0, 9.5, 9.0, 4.5),
    ("比赛2", "", -1.0, -1.0, 2.5, 2.5, 9.5, 9.0, 4.5),
    ("比赛3", "", -1.5, -2.25, 2.75, 3.0, 9.0, 9.0, 4.0),
    ("比赛4", "", -0.5, -1.0, 2.25, 2.25, 8.5, 8.5, 3.5),
]

for i in range(4):
    st.subheader(f"比赛 {i+1}")

    # 动态列
    if use_corner:
        colA, colB, colC, colD, colE, colF, colG, colH, colI = st.columns([1.2, 0.9, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8])
    else:
        colA, colB, colC, colD, colE, colF = st.columns([1.2, 0.9, 0.8, 0.8, 0.8, 0.8])

    # 取值
    name_val = st.session_state.get(f"name{i}", defaults[i][0])
    date_val = st.session_state.get(f"date{i}", defaults[i][1])
    ho_val = st.session_state.get(f"ho{i}", defaults[i][2])
    hl_val = st.session_state.get(f"hl{i}", defaults[i][3])
    to_val = st.session_state.get(f"to{i}", defaults[i][4])
    tl_val = st.session_state.get(f"tl{i}", defaults[i][5])

    name = colA.text_input("🏷️ 比赛名称", name_val, key=f"name{i}", help="建议中文，API导入已自动翻译")
    match_date = colB.text_input("📅 比赛日期", date_val, key=f"date{i}", placeholder="YYYY-MM-DD")

    h_open = colC.number_input("初盘让球", value=ho_val, step=0.25, key=f"ho{i}")
    h_live = colD.number_input("即时让球", value=hl_val, step=0.25, key=f"hl{i}")
    t_open = colE.number_input("大小球初盘", value=to_val, step=0.25, key=f"to{i}")
    t_live = colF.number_input("大小球即时盘", value=tl_val, step=0.25, key=f"tl{i}")

    if use_corner:
        co_val = st.session_state.get(f"co{i}", defaults[i][6])
        cl_val = st.session_state.get(f"cl{i}", defaults[i][7])
        ch_val = st.session_state.get(f"ch{i}", defaults[i][8])
        c_open = colG.number_input("角球初盘", value=co_val, step=0.5, key=f"co{i}")
        c_live = colH.number_input("角球即时盘", value=cl_val, step=0.5, key=f"cl{i}")
        c_half = colI.number_input("上半场角球", value=ch_val, step=0.5, key=f"ch{i}")
    else:
        c_open = c_live = c_half = None

    actual_result = None
    actual_goals = None
    actual_corners = None
    if mode == "📊 赛后复盘模式":
        st.caption("🏆 赛果输入（复盘用）")
        col_r1, col_r2, col_r3 = st.columns(3)
        result_map = {"主胜": "home", "平局": "draw", "客胜": "away"}
        actual_result_str = col_r1.selectbox("赛果", list(result_map.keys()), key=f"res{i}")
        actual_result = result_map[actual_result_str]
        actual_goals = col_r2.number_input("实际总进球", value=2, min_value=0, step=1, key=f"g{i}")
        actual_corners = col_r3.number_input("实际总角球", value=9, min_value=0, step=1, key=f"crn{i}")

    matches.append(
        Match(
            name=name,
            match_date=match_date,
            handicap_open=h_open,
            handicap_live=h_live,
            total_open=t_open,
            total_live=t_live,
            corner_open=c_open,
            corner_live=c_live,
            corner_half=c_half,
            actual_result=actual_result,
            actual_goals=actual_goals,
            actual_corners=actual_corners
        )
    )

st.divider()

# ==================================================
# 开始分析
# ==================================================

if st.button("🔍 开始体检"):
    total_score = 0
    A, B, C, D = [], [], [], []

    st.header("📊 风险评级")
    for m in matches:
        score, level = score_match(m)
        total_score += score
        suggestion = auto_fix(m)
        date_str = f"({m.match_date})" if m.match_date else ""
        st.write(f"**{m.name}** {date_str} ｜ 评分：{score} ｜ 评级：{level} ｜ 修单：{suggestion}")

        if level == "A": A.append(m.name)
        elif level == "B": B.append(m.name)
        elif level == "C": C.append(m.name)
        else: D.append(m.name)

    st.divider()
    st.header("📐 角球分析")
    if use_corner:
        for m in matches:
            st.write(f"**{m.name}** ： {corner_style(m)}")
    else:
        st.info("未启用角球分析")

    st.divider()
    st.header("⚠️ 共振检测")
    warnings = detect_resonance(matches)
    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success("未发现明显共振风险")

    st.divider()
    avg_score = total_score / 4
    st.header("🧾 总评")
    st.write(f"A类：{len(A)} 场")
    st.write(f"B类：{len(B)} 场")
    st.write(f"C类：{len(C)} 场")
    st.write(f"D类：{len(D)} 场")
    st.write(f"平均评分：{avg_score:.2f}")
    st.success(bankroll_advice(avg_score))

    if len(D) >= 1:
        st.error("🔴 建议放弃此单")
    elif len(C) >= 2:
        st.warning("🟠 风险偏高，建议修单")
    else:
        st.success("🟢 结构可接受")

    # 复盘额外展示
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
    st.info("👆 可手动输入或使用 API 一键导入，点击按钮生成报告。")