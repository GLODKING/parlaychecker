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
# 球队翻译
# ==================================================

TEAM_TRANSLATION = {
    "Manchester City": "曼城", "Manchester United": "曼联", "Liverpool": "利物浦",
    "Chelsea": "切尔西", "Arsenal": "阿森纳", "Tottenham Hotspur": "热刺",
    "Newcastle United": "纽卡斯尔联", "Brighton and Hove Albion": "布莱顿",
    "Aston Villa": "阿斯顿维拉", "West Ham United": "西汉姆联",
    "Crystal Palace": "水晶宫", "Fulham": "富勒姆",
    "Wolverhampton Wanderers": "狼队", "Everton": "埃弗顿",
    "Nottingham Forest": "诺丁汉森林", "Brentford": "布伦特福德",
    "Leeds United": "利兹联", "Leicester City": "莱斯特城",
    "Southampton": "南安普顿", "Bournemouth": "伯恩茅斯",
    "Real Madrid": "皇马", "Barcelona": "巴萨", "Atletico Madrid": "马竞",
    "Sevilla": "塞维利亚", "Real Betis": "贝蒂斯", "Real Sociedad": "皇家社会",
    "Villarreal": "比利亚雷亚尔", "Athletic Club": "毕尔巴鄂竞技",
    "Valencia": "瓦伦西亚",
    "Juventus": "尤文图斯", "Inter Milan": "国际米兰", "AC Milan": "AC米兰",
    "Napoli": "那不勒斯", "AS Roma": "罗马", "Lazio": "拉齐奥",
    "Atalanta": "亚特兰大", "Fiorentina": "佛罗伦萨",
    "Bayern Munich": "拜仁慕尼黑", "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "莱比锡红牛", "Bayer Leverkusen": "勒沃库森",
    "Eintracht Frankfurt": "法兰克福",
    "Paris Saint-Germain": "巴黎圣日耳曼", "Olympique Marseille": "马赛",
    "Olympique Lyonnais": "里昂", "AS Monaco": "摩纳哥",
    "Netherlands": "荷兰", "Sweden": "瑞典", "Germany": "德国",
    "Ivory Coast": "科特迪瓦", "Ecuador": "厄瓜多尔", "Curacao": "库拉索",
    "Tunisia": "突尼斯", "Japan": "日本", "Spain": "西班牙",
    "Saudi Arabia": "沙特阿拉伯", "Belgium": "比利时", "Iran": "伊朗",
    "Uruguay": "乌拉圭", "Cape Verde": "佛得角",
    "New Zealand": "新西兰", "Egypt": "埃及",
    "France": "法国", "England": "英格兰", "Brazil": "巴西",
    "Argentina": "阿根廷", "Portugal": "葡萄牙", "Croatia": "克罗地亚",
    "Morocco": "摩洛哥", "Senegal": "塞内加尔", "United States": "美国",
    "Mexico": "墨西哥",
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
# API 拉取
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
            except: pass
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
# 智能推荐最优四串一
# ==================================================

def find_best_parlay(all_matches: List[Match], top_n=4):
    """从所有比赛中选 top_n 个评分最高的比赛组合，返回最佳四串一列表"""
    scored = [(m, score_match(m)) for m in all_matches]
    scored.sort(key=lambda x: x[1], reverse=True)  # 高分在前
    # 排除 D 类
    filtered = [(m, s) for m, s in scored if s >= 3]
    best = filtered[:top_n]
    return [m for m, _ in best]


def find_all_valid_parlays(all_matches: List[Match], parlay_size=4):
    """返回所有不含 D 类的四串一组合，按总分降序排列"""
    scored = [(m, score_match(m)) for m in all_matches]
    # 排除 D 类
    valid = [(m, s) for m, s in scored if s >= 3]
    if len(valid) < parlay_size:
        return []
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
st.caption("支持任意场次 | 自动评分排序 | 智能推荐最佳串关")

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
                    st.session_state["api_matches"] = raw
                    st.session_state["match_count"] = len(raw)
                    st.success(f"已加载 {len(raw)} 场比赛（已翻译中文队名）")
                    st.rerun()

st.divider()

# ---------- 场次数量选择 ----------
if "match_count" not in st.session_state:
    st.session_state["match_count"] = 8  # 默认 8 场

match_count = st.number_input("今天有几场比赛？", min_value=2, max_value=20, value=st.session_state["match_count"], step=1)

# ---------- 角球开关 ----------
use_corner = st.checkbox("📐 启用角球分析", value=True)

# ---------- 读取 API 导入的数据 ----------
api_data = st.session_state.get("api_matches", [])

st.subheader("📝 比赛数据输入")

matches = []
for i in range(int(match_count)):
    with st.expander(f"比赛 {i+1}", expanded=(i < 4)):
        # 从 API 数据读取默认值
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

        col1, col2, col3, col4, col5 = st.columns(5)
        name = col1.text_input("比赛名称", def_name, key=f"name{i}")
        match_date = col2.text_input("日期", def_date, key=f"date{i}", placeholder="YYYY-MM-DD")
        h_open = col3.number_input("初盘让球", value=def_ho, step=0.25, key=f"ho{i}")
        h_live = col4.number_input("即时让球", value=def_hl, step=0.25, key=f"hl{i}")
        t_open = col5.number_input("大小球初盘", value=def_to, step=0.25, key=f"to{i}")

        col6, col7 = st.columns(2)
        t_live = col6.number_input("大小球即时盘", value=def_tl, step=0.25, key=f"tl{i}")

        if use_corner:
            colc1, colc2, colc3 = st.columns(3)
            c_open = colc1.number_input("角球初盘", value=def_co, step=0.5, key=f"co{i}")
            c_live = colc2.number_input("角球即时盘", value=def_cl, step=0.5, key=f"cl{i}")
            c_half = colc3.number_input("上半场角球", value=def_ch, step=0.5, key=f"ch{i}")
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

# ==================================================
# 分析按钮
# ==================================================

if st.button("🔍 开始分析全部比赛"):
    # 评分排序
    scored_list = [(m, score_match(m), score_to_level(score_match(m))) for m in matches]
    scored_list.sort(key=lambda x: x[1], reverse=True)

    st.header("📊 全部比赛评分排序")
    for m, s, lv in scored_list:
        date_str = f"({m.match_date})" if m.match_date else ""
        st.write(f"**{m.name}** {date_str} | 评分：{s} | 评级：{lv} | 修单：{auto_fix(m)}")

    st.divider()

    # 自动推荐最佳四串一
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

    # 所有有效串关排名
    all_combos = find_all_valid_parlays(matches)
    if all_combos:
        st.header("📋 所有有效四串一排名（前 5）")
        for idx, combo in enumerate(all_combos[:5]):
            total_s = sum(score_match(m) for m in combo)
            names = " | ".join([m.name for m in combo])
            st.write(f"**#{idx+1}** 评分：{total_s} → {names}")

    st.divider()

    # 角球风格
    if use_corner:
        st.header("📐 角球风格一览")
        for m in matches:
            st.write(f"**{m.name}** ：{corner_style(m)}")
        st.divider()

    # 复盘
    if mode == "📊 赛后复盘模式":
        st.header("📋 实际赛果记录")
        for m in matches:
            date_str = f"({m.match_date})" if m.match_date else ""
            result_names = {"home": "主胜", "draw": "平局", "away": "客胜"}
            actual = result_names.get(m.actual_result, "未填")
            goals = m.actual_goals if m.actual_goals is not None else "-"
            corners = m.actual_corners if m.actual_corners is not None else "-"
            st.write(f"**{m.name}** {date_str}：{actual}，进球 {goals}，角球 {corners}")

else:
    st.info("👆 设定比赛场次，填好数据后点击按钮生成报告。")
