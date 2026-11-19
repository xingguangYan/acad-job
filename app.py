from __future__ import annotations

import pandas as pd
import streamlit as st

from src.academic_api import fetch_daily_frontier, search_academic_papers
from src.config import DOMAIN_OPTIONS, HOT_TOPICS, load_config
from src.grant_signals import load_static_grants
from src.industrial_signals import (
    attach_commercial_potential,
    fetch_arxiv_90d_trend,
    fetch_patentsview_signal,
    load_commercial_potential_index,
)
from src.job_signals import fetch_live_academic_job_feeds, load_static_jobs
from src.styles import inject_custom_css, render_footer_html, render_hero_banner, render_kpi_cards
from src.ui_components import (
    AUTHOR_EMAIL,
    render_daily_frontier,
    render_grants_tab,
    render_jobs_tab,
    render_paper_card,
    render_sidebar_config,
    render_support_and_collab_section,
    render_topic_overview,
)

st.set_page_config(
    page_title="科研前沿 × 产业化 × 学术求职与基金聚合器",
    page_icon="🔬",
    layout="wide",
)

inject_custom_css()

llm_cfg = render_sidebar_config()
config = load_config(st.session_state)


@st.cache_resource(show_spinner=False)
def get_compot_index(csv_path: str):
    return load_commercial_potential_index(csv_path)


@st.cache_resource(show_spinner=False)
def get_static_jobs(csv_path: str):
    return load_static_jobs(csv_path)


@st.cache_resource(show_spinner=False)
def get_static_grants(csv_path: str):
    return load_static_grants(csv_path)


@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_daily_frontier():
    return fetch_daily_frontier(config)


@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_rss_jobs():
    return fetch_live_academic_job_feeds(timeout=config.request_timeout)


@st.cache_data(ttl=1800, show_spinner=False)
def get_cached_topic_signals(query: str):
    trend = []
    patent = {"available": False, "reason": "未启用"}
    try:
        trend = fetch_arxiv_90d_trend(query, config)
    except Exception:
        trend = []
    try:
        patent = fetch_patentsview_signal(query, config)
    except Exception:
        patent = {"available": False, "reason": "PatentsView 未启用"}
    return trend, patent


compot_index = get_compot_index(config.compot_csv_path)
static_jobs = get_static_jobs(config.jobs_csv_path)
static_grants = get_static_grants(config.grants_csv_path)
rss_jobs, rss_warnings = get_cached_rss_jobs()
all_base_jobs = static_jobs + rss_jobs

render_hero_banner()
render_kpi_cards(
    [
        {
            "label": "学术与商业潜力库",
            "value": f"{len(compot_index):,} DOI",
            "sub": "OpenAlex + S2 + arXiv 实时检索",
            "color": "#4F46E5",
        },
        {
            "label": "在线学术/研发岗位",
            "value": f"{len(all_base_jobs)} 条",
            "sub": "支持 CV 上传与 AI 自动匹配",
            "color": "#10B981",
        },
        {
            "label": "青年科研基金库",
            "value": f"{len(static_grants)} 项",
            "sub": "Fundlark 资格核验 + 进度追踪",
            "color": "#8B5CF6",
        },
        {
            "label": "云端大模型引擎",
            "value": "🟢 已就绪" if llm_cfg.get("api_key") else "🟡 待填 Key",
            "sub": "会话结束即焚，绝不保留密钥",
            "color": "#16A34A" if llm_cfg.get("api_key") else "#F59E0B",
        },
    ]
)

tab_search, tab_jobs, tab_grants, tab_frontier, tab_about = st.tabs(
    ["🔍 检索与发现", "💼 工作（含CV匹配）", "💰 基金与资助", "📰 今日前沿", "☕ 支持与合作"]
)

with tab_frontier:
    with st.spinner("正在拉取 arXiv / bioRxiv / medRxiv 今日最新预印本…"):
        buckets, frontier_warnings = get_cached_daily_frontier()
    render_daily_frontier(buckets, frontier_warnings)

with tab_search:
    with st.expander("📰 今日前沿速览（arXiv / bioRxiv / medRxiv 每日开场信号）", expanded=False):
        buckets, frontier_warnings = get_cached_daily_frontier()
        render_daily_frontier(buckets, frontier_warnings)

    st.markdown("**🔥 热门研究方向快查：**")
    hot_cols = st.columns(len(HOT_TOPICS))
    clicked_hot = None
    for idx, topic in enumerate(HOT_TOPICS):
        if hot_cols[idx].button(topic, key=f"hot_{idx}", use_container_width=True):
            clicked_hot = topic

    with st.form("search_form", clear_on_submit=False):
        col_q, col_d, col_btn = st.columns([4, 1.5, 1])
        with col_q:
            query_input = st.text_input(
                "检索主题（支持中英文自然语言，英文学术关键词命中率更佳）",
                value=clicked_hot or st.session_state.get("current_query", ""),
                placeholder="例如：perovskite solar cells 或 钙钛矿光伏",
            )
        with col_d:
            domain_input = st.selectbox("领域筛选", options=list(DOMAIN_OPTIONS.keys()), index=0)
        with col_btn:
            st.write("")
            st.write("")
            submitted = st.form_submit_button("开始检索", use_container_width=True, type="primary")

    run_query = clicked_hot or (query_input.strip() if submitted and query_input.strip() else "")
    if run_query:
        st.session_state["current_query"] = run_query
        history: list[str] = st.session_state.setdefault("search_history", [])
        if run_query not in history:
            history.append(run_query)

        with st.spinner(f"正在检索「{run_query}」并注入产业化信号…"):
            papers, search_warnings = search_academic_papers(run_query, domain_input, config)
            attach_commercial_potential(papers, compot_index)
            trend_data, patent_data = get_cached_topic_signals(run_query)

        st.session_state["search_results"] = papers
        st.session_state["search_warnings"] = search_warnings
        st.session_state["trend_data"] = trend_data
        st.session_state["patent_data"] = patent_data

    results = st.session_state.get("search_results", [])
    warnings = st.session_state.get("search_warnings", [])
    active_query = st.session_state.get("current_query", "")

    for w in warnings:
        st.warning(w)

    if active_query and not results:
        st.info("未找到匹配文献，建议尝试英文关键词或切换领域为“全部”。")

    if results:
        export_df = pd.DataFrame(
            [
                {
                    "title": r["title"],
                    "source_badge": r["source_badge"],
                    "pub_date": r["pub_date"],
                    "citations": r["citation_count"],
                    "doi": r["doi"],
                    "compot_grade": r.get("compot_grade") or "",
                    "url": r["url"],
                }
                for r in results
            ]
        )
        c_cnt, c_exp = st.columns([4, 1])
        with c_cnt:
            st.subheader(f"检索结果（共 {len(results)} 篇，已去重合并）")
        with c_exp:
            st.download_button(
                "导出 CSV",
                data=export_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"frontier_{active_query[:24]}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        for idx, paper in enumerate(results):
            render_paper_card(paper, idx, config, llm_cfg, compot_loaded=bool(compot_index))

        st.divider()
        render_topic_overview(
            active_query,
            results,
            st.session_state.get("trend_data", []),
            st.session_state.get("patent_data", {}),
        )

with tab_jobs:
    render_jobs_tab(all_base_jobs, rss_warnings, config, llm_cfg)

with tab_grants:
    render_grants_tab(static_grants, config, llm_cfg)

with tab_about:
    render_support_and_collab_section()
    st.divider()
    st.subheader("🔧 运行环境与数据状态")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("商业潜力切片条目", len(compot_index))
    s2.metric("本地精选岗位数", len(static_jobs))
    s3.metric("基金与资助项目数", len(static_grants))
    s4.metric("实时订阅岗位数", len(rss_jobs))

render_footer_html(AUTHOR_EMAIL)