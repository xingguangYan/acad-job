from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
import streamlit as st

from src.academic_api import (
    fetch_active_institutions_for_topic,
    fetch_citation_network,
    fetch_similar_papers,
    search_latest_frontier_papers,
)
from src.config import AppConfig, LLM_PRESETS
from src.cv_matcher import extract_text_from_cv_file
from src.grant_signals import (
    fetch_openalex_funders,
    filter_grants,
    parse_uploaded_grants_file,
)
from src.industrial_signals import assess_trl_via_apify
from src.job_signals import filter_jobs, parse_uploaded_jobs_file
from src.llm_client import (
    get_llm_settings,
    llm_analyze_job_fit,
    llm_assess_trl,
    llm_batch_rank_jobs,
    llm_check_grant_eligibility,
    llm_generate_cover_letter,
    llm_parse_cv,
    llm_summarize_paper,
    test_llm_connection,
)
from src.styles import (
    _render_html,
    find_qr_image_path,
    render_grant_header_html,
    render_job_header_html,
    render_paper_header_html,
)

AUTHOR_EMAIL = "xingguangyan0703@gmail.com"

TRL_LABELS = {
    1: "TRL 1 · 基础原理观察",
    2: "TRL 2 · 技术概念提出",
    3: "TRL 3 · 关键功能验证",
    4: "TRL 4 · 实验室环境验证",
    5: "TRL 5 · 相关环境验证",
    6: "TRL 6 · 相关环境原型演示",
    7: "TRL 7 · 实际环境系统演示",
    8: "TRL 8 · 实际系统定型测试",
    9: "TRL 9 · 商业化成熟应用",
}


def _on_preset_change() -> None:
    preset_name = st.session_state.get("ui_llm_preset", "")
    preset = LLM_PRESETS.get(preset_name, {})
    if preset.get("base_url"):
        st.session_state["ui_llm_base_url"] = preset["base_url"]
    if preset.get("model"):
        st.session_state["ui_llm_model"] = preset["model"]


def _format_cv_profile_text() -> str:
    cv = st.session_state.get("cv_parsed_profile")
    if not isinstance(cv, dict):
        return ""
    areas = ", ".join(cv.get("research_areas") or [])
    skills = ", ".join(cv.get("skills") or [])
    return (
        f"Stage: {cv.get('career_stage', '')}; "
        f"PhD Years: {cv.get('years_after_phd', '')}; "
        f"Areas: {areas}; Skills: {skills}; "
        f"Highlights: {cv.get('highlights', '')}"
    )


def render_sidebar_config() -> dict[str, str]:
    with st.sidebar:
        st.markdown("### ⚙️ 云端引擎与 API 配置")
        st.caption("🔒 隐私安全承诺：所有 API Key 与上传的 CV 仅存于当前浏览器内存，每次刷新网页不会保存任何敏感信息。")

        with st.expander("🤖 大模型 API（CV解析 / AI精读 / TRL / 基金核验）", expanded=True):
            st.selectbox(
                "服务商预设",
                options=list(LLM_PRESETS.keys()),
                key="ui_llm_preset",
                on_change=_on_preset_change,
            )
            if "ui_llm_base_url" not in st.session_state:
                st.session_state["ui_llm_base_url"] = "https://api-inference.modelscope.cn/v1"
            if "ui_llm_model" not in st.session_state:
                st.session_state["ui_llm_model"] = "Qwen/Qwen2.5-72B-Instruct"

            st.text_input("Base URL", key="ui_llm_base_url", placeholder="https://api-inference.modelscope.cn/v1")
            st.text_input("Model ID", key="ui_llm_model", placeholder="Qwen/Qwen2.5-72B-Instruct")
            st.text_input("API Key / 魔搭 Token", key="ui_llm_api_key", type="password", placeholder="sk-... 或 ms-...")

            llm_cfg = get_llm_settings(st.session_state)
            if st.button("测试模型连通性", key="test_llm_conn_btn", use_container_width=True):
                with st.spinner("正在测试连接…"):
                    ok, msg = test_llm_connection(llm_cfg)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

            if llm_cfg["api_key"]:
                st.success("大模型已就绪")
            else:
                st.info("填入 Key 后可解锁 CV 解析、智能匹配与资格核验。")

        with st.expander("🔑 可选：学术 & TRL 数据源密钥", expanded=False):
            st.text_input("Semantic Scholar Key", key="ui_s2_key", type="password")
            st.text_input("Apify API Token", key="ui_apify_token", type="password")
            st.text_input("OpenAlex API Key", key="ui_openalex_key", type="password")

        history: list[str] = st.session_state.get("search_history", [])
        if history:
            st.divider()
            st.markdown("**🕒 本次检索历史**")
            for h in reversed(history[-5:]):
                st.caption(f"• {h}")

        st.divider()
        with st.container(border=True):
            st.markdown("**☕ 请作者喝杯咖啡**")
            st.caption("如果这个工具对你的科研或求职有帮助，欢迎扫码支持！")
            qr_path = find_qr_image_path()
            if qr_path:
                st.image(qr_path, width=180, caption="扫码支持持续开发")
            else:
                st.caption("（提示：请将收款二维码保存为 `assets/coffee_qr.png`）")
            st.markdown(f"**🤝 合作联系：** [{AUTHOR_EMAIL}](mailto:{AUTHOR_EMAIL})")

    return get_llm_settings(st.session_state)


def render_daily_frontier(
    buckets: dict[str, list[dict[str, Any]]],
    warnings: list[str],
    config: AppConfig | None = None,
    key_prefix: str = "frontier",
) -> None:
    st.subheader("📰 今日前沿（Daily Frontier）")
    if warnings:
        st.caption(" · ".join(warnings))

    if config is not None:
        fc1, fc2, fc3 = st.columns([3.2, 1.3, 1.1])
        with fc1:
            f_query = st.text_input(
                "🔍 实时检索最新前沿论文（支持英文关键词，按发布日期倒序）",
                placeholder="例如：embodied AI, perovskite, CRISPR, reasoning model",
                key=f"{key_prefix}_search_q",
            )
        with fc2:
            f_days = st.selectbox(
                "时间窗口",
                [7, 30, 90],
                index=1,
                format_func=lambda d: f"近 {d} 天",
                key=f"{key_prefix}_days",
            )
        with fc3:
            st.write("")
            st.write("")
            f_btn = st.button("获取最新论文", type="primary", use_container_width=True, key=f"{key_prefix}_btn")

        if f_btn and f_query.strip():
            with st.spinner(f"正在检索近 {f_days} 天「{f_query.strip()}」最新前沿…"):
                st.session_state[f"{key_prefix}_results"] = search_latest_frontier_papers(
                    f_query.strip(), config, days=f_days
                )

        f_results = st.session_state.get(f"{key_prefix}_results")
        if f_results is not None:
            st.markdown(f"**🔎 实时最新前沿结果（共 {len(f_results)} 篇，按日期倒序）：**")
            if not f_results:
                st.info("该时间窗口内未找到匹配新论文，建议放宽至近 30/90 天或使用英文关键词。")
            for item in f_results[:15]:
                with st.container(border=True):
                    title_md = f"[{item['title']}]({item['url']})" if item.get("url") else item["title"]
                    st.markdown(f"**`{item['source']}` {title_md}**")
                    st.caption(f"📅 {item.get('published', '')} · 👤 {', '.join(item.get('authors', []))}")
                    if item.get("summary"):
                        st.write(item["summary"] + "...")
            st.divider()

    cols = st.columns(2)
    for idx, (label, papers) in enumerate(buckets.items()):
        with cols[idx % 2]:
            with st.expander(f"📌 {label} ({len(papers)})", expanded=False):
                if not papers:
                    st.info("暂无最新条目或数据源限流。")
                    continue
                for p in papers:
                    authors_str = ", ".join(p.get("authors", [])[:3])
                    st.markdown(f"**[{p['title']}]({p['url']})**" if p.get("url") else f"**{p['title']}**")
                    st.caption(f"{p.get('published', '')} · {authors_str}")
                    if p.get("summary"):
                        st.write(p["summary"] + "...")
                    st.divider()


def render_trl_scale(trl_result: dict[str, Any]) -> None:
    trl_num = trl_result.get("trl")
    if trl_num is not None:
        st.progress(trl_num / 9.0, text=TRL_LABELS.get(trl_num, f"TRL {trl_num}/9"))
    else:
        st.info("已返回评估结果：")
    if trl_result.get("summary"):
        st.caption(trl_result["summary"])


def render_paper_card(
    paper: dict[str, Any],
    idx: int,
    config: AppConfig,
    llm_cfg: dict[str, str],
    compot_loaded: bool,
) -> None:
    uid = paper["uid"]
    k_uid = f"{idx}_{uid[:24]}"
    trl_cache: dict[str, Any] = st.session_state.setdefault("trl_cache", {})
    ai_sum_cache: dict[str, str] = st.session_state.setdefault("ai_sum_cache", {})
    sim_cache: dict[str, Any] = st.session_state.setdefault("similar_cache", {})
    cit_cache: dict[str, Any] = st.session_state.setdefault("citation_cache", {})

    with st.container(border=True):
        render_paper_header_html(paper, trl_cache.get(uid), compot_loaded)

        if paper.get("tldr"):
            st.info(f"**TLDR：** {paper['tldr']}")
        elif paper.get("abstract"):
            with st.expander("查看摘要", expanded=False):
                st.write(paper["abstract"])

        b1, b2, b3, b4, b5 = st.columns([1.2, 1.2, 1.1, 1.1, 1.2])
        with b1:
            if st.button("深度评估 TRL", key=f"trl_btn_{k_uid}", use_container_width=True):
                with st.spinner("正在评估技术就绪度…"):
                    desc = paper.get("tldr") or paper.get("abstract") or paper["title"]
                    if config.apify_api_token:
                        try:
                            trl_cache[uid] = assess_trl_via_apify(paper["title"], desc, config)
                        except Exception:
                            trl_cache[uid] = {"error": "Apify TRL 接口暂不可用，请稍后重试"}
                    elif llm_cfg.get("api_key"):
                        try:
                            trl_cache[uid] = llm_assess_trl(paper["title"], desc, llm_cfg)
                        except Exception as exc:
                            trl_cache[uid] = {"error": f"大模型 TRL 评估失败：{type(exc).__name__}"}
                    else:
                        trl_cache[uid] = {
                            "error": "未配置 APIFY_API_TOKEN 或大模型 API。请在左侧边栏「🤖 大模型 API」填入 Key 即可开启 TRL 评估！"
                        }

        with b2:
            if st.button("🤖 AI 精读", key=f"aisum_btn_{k_uid}", use_container_width=True):
                if not llm_cfg.get("api_key"):
                    ai_sum_cache[uid] = "⚠️ 请先在左侧边栏「🤖 大模型 API」填入您的 API Key。"
                else:
                    with st.spinner("AI 正在提炼创新点与产业应用…"):
                        try:
                            abs_txt = paper.get("abstract") or paper.get("tldr") or paper["title"]
                            ai_sum_cache[uid] = llm_summarize_paper(paper["title"], abs_txt, llm_cfg)
                        except Exception as exc:
                            ai_sum_cache[uid] = f"⚠️ AI 精读失败：{type(exc).__name__}"

        with b3:
            if st.button("相似论文", key=f"sim_btn_{k_uid}", use_container_width=True):
                with st.spinner("正在检索相似论文…"):
                    try:
                        sim_cache[uid] = fetch_similar_papers(paper, config)
                    except Exception:
                        sim_cache[uid] = {"error": "相似论文接口限流或暂不可用"}

        with b4:
            if st.button("引用网络", key=f"cit_btn_{k_uid}", use_container_width=True):
                with st.spinner("正在加载引用关系…"):
                    try:
                        cit_cache[uid] = fetch_citation_network(paper, config)
                    except Exception:
                        cit_cache[uid] = {"error": "引用网络接口限流或暂不可用"}

        with b5:
            if paper.get("pdf_url"):
                st.link_button("📄 PDF 原文", paper["pdf_url"], use_container_width=True)
            elif st.button("💼 查相关岗位", key=f"joblink_{k_uid}", use_container_width=True):
                short_kw = " ".join(paper["title"].split()[:4])
                st.session_state["job_query_prefill"] = short_kw
                st.toast(f"已将「{short_kw}」同步至「💼 工作」栏目！")

        if uid in trl_cache:
            res = trl_cache[uid]
            if "error" in res:
                st.warning(res["error"])
            else:
                render_trl_scale(res)

        if ai_sum_cache.get(uid):
            st.success(ai_sum_cache[uid])

        if uid in sim_cache:
            sim_res = sim_cache[uid]
            with st.expander("相似论文推荐", expanded=True):
                if isinstance(sim_res, dict) and "error" in sim_res:
                    st.warning(sim_res["error"])
                elif not sim_res:
                    st.caption("未检索到相似论文。")
                else:
                    for sp in sim_res:
                        sp_title = sp.get("title", "Untitled")
                        sp_url = sp.get("url", "")
                        st.markdown(
                            f"- [{sp_title}]({sp_url}) ({sp.get('year', '')} · 引用 {sp.get('citationCount', 0)})"
                            if sp_url else f"- {sp_title} ({sp.get('year', '')})"
                        )

        if uid in cit_cache:
            cit_res = cit_cache[uid]
            with st.expander("引用网络（施引 & 参考文献）", expanded=True):
                if "error" in cit_res:
                    st.warning(cit_res["error"])
                else:
                    c_col, r_col = st.columns(2)
                    with c_col:
                        st.markdown("**近期施引论文**")
                        for cp in cit_res.get("citations", []) or []:
                            cp_title = cp.get("title", "Untitled")
                            cp_url = cp.get("url", "")
                            st.markdown(
                                f"- [{cp_title}]({cp_url}) ({cp.get('year', '')})"
                                if cp_url else f"- {cp_title} ({cp.get('year', '')})"
                            )
                        if not cit_res.get("citations"):
                            st.caption("暂无记录")
                    with r_col:
                        st.markdown("**参考文献**")
                        for rp in cit_res.get("references", []) or []:
                            rp_title = rp.get("title", "Untitled")
                            rp_url = rp.get("url", "")
                            st.markdown(
                                f"- [{rp_title}]({rp_url}) ({rp.get('year', '')})"
                                if rp_url else f"- {rp_title} ({rp.get('year', '')})"
                            )
                        if not cit_res.get("references"):
                            st.caption("暂无记录")


def render_topic_overview(
    query: str,
    papers: list[dict[str, Any]],
    trend_data: list[dict[str, Any]],
    patent_data: dict[str, Any],
) -> None:
    st.subheader(f"📊 方向概览：{query}")

    scored = [p for p in papers if p.get("compot_grade")]
    ab_count = sum(1 for p in scored if p["compot_grade"] in ("A", "B"))
    ab_ratio = f"{(ab_count / len(scored) * 100):.0f}%" if scored else "待补充CSV"
    preprint_count = sum(1 for p in papers if p.get("is_preprint"))
    total_cites = sum(p.get("citation_count") or 0 for p in papers)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("去重后相关论文", len(papers))
    m2.metric("预印本占比", f"{(preprint_count / len(papers) * 100):.0f}%" if papers else "0%")
    m3.metric("商业潜力 A/B 占比", ab_ratio)
    m4.metric(
        "近 3 年美国专利数" if patent_data.get("available") else "累计总引用量",
        patent_data.get("total_hits", 0) if patent_data.get("available") else total_cites,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**近 90 天 arXiv 趋势**")
        if trend_data:
            st.line_chart(pd.DataFrame(trend_data).set_index("week"))
        else:
            st.caption("近 90 天暂无足够 arXiv 样本。")
    with c2:
        st.markdown("**发表年份分布**")
        years = [str(p["year"]) for p in papers if p.get("year")]
        if years:
            st.bar_chart(pd.Series(years).value_counts().sort_index())
        else:
            st.caption("暂无年份数据。")
    with c3:
        st.markdown("**商业潜力 / 活跃机构 TOP**")
        if scored:
            grade_counts = pd.Series([p["compot_grade"] for p in scored]).value_counts().reindex(
                ["A", "B", "C", "D"], fill_value=0
            )
            st.bar_chart(grade_counts)
        else:
            inst_list = [inst for p in papers for inst in p.get("institutions", [])]
            if inst_list:
                top_insts = Counter(inst_list).most_common(6)
                st.dataframe(
                    pd.DataFrame(top_insts, columns=["活跃机构", "出现次数"]),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.caption("暂无机构或商业潜力样本。")


def render_cv_panel(llm_cfg: dict[str, str], all_jobs: list[dict[str, Any]]) -> None:
    """CV 简历上传解析与自动工作匹配面板（含隐私安全提示与 API 前置引导）。"""
    with st.expander("📄 上传个人 CV 简历 · AI 解析并自动匹配岗位（安全提示：刷新网页不保留数据）", expanded=True):
        st.info(
            "🔒 **隐私与安全声明**：为了保障您的隐私与密钥安全，本应用无后台数据库，**每次刷新或关闭网页后，不会保存您的 API Key、简历文件及解析内容**。"
            " 使用 AI 解析简历前，请先在 **左侧边栏「🤖 大模型 API」** 填入您自己的 API Key。"
        )

        if not llm_cfg.get("api_key"):
            st.warning("⚠️ 检测到您尚未在左侧边栏填入大模型 API Key：请先在左侧填入 Key（如魔搭免费 Token 或 DeepSeek Key），再点击「🤖 AI 解析 CV 简历」。")

        c_up, c_paste = st.columns([1, 1.2])
        with c_up:
            cv_file = st.file_uploader(
                "上传您的 CV 简历（支持 PDF / DOCX / TXT / MD）",
                type=["pdf", "docx", "txt", "md"],
                key="cv_file_uploader",
            )
        with c_paste:
            cv_manual_text = st.text_area(
                "或直接粘贴简历核心文本（教育背景、论文列表、技能栈）",
                height=100,
                placeholder="例如：PhD in Materials Science, 3 papers on perovskite solar cells, skilled in DFT & Python...",
                key="cv_manual_text",
            )

        b_parse, b_match, b_clear = st.columns([1.3, 1.6, 0.9])
        with b_parse:
            if st.button("🤖 AI 解析 CV 简历", key="cv_parse_btn", type="primary", use_container_width=True):
                if not llm_cfg.get("api_key"):
                    st.error("请先在左侧边栏「🤖 大模型 API」填入您的 API Key，再执行解析！")
                else:
                    try:
                        raw_cv = extract_text_from_cv_file(cv_file) if cv_file is not None else cv_manual_text.strip()
                        if not raw_cv:
                            st.warning("请先上传 CV 文件或粘贴简历文本。")
                        else:
                            st.session_state["cv_extracted_text"] = raw_cv
                            with st.spinner("正在提取简历并调用您配置的大模型安全解析…"):
                                parsed = llm_parse_cv(raw_cv, llm_cfg)
                            st.session_state["cv_parsed_profile"] = parsed
                            st.success(f"CV 解析成功（{parsed.get('parse_mode', '完成')}）！已在当前会话提取您的科研画像。")
                    except Exception as exc:
                        st.error(f"CV 解析失败：{exc}")

        with b_match:
            if st.button("🎯 根据 CV 自动匹配并排序岗位", key="cv_match_btn", use_container_width=True):
                profile_txt = _format_cv_profile_text() or cv_manual_text.strip() or st.session_state.get("current_query", "")
                if not profile_txt:
                    st.warning("请先解析 CV 或填写背景关键词后再执行自动匹配。")
                else:
                    with st.spinner("正在计算岗位与您简历的匹配度并重排…"):
                        st.session_state["cv_matched_jobs"] = llm_batch_rank_jobs(profile_txt, all_jobs, llm_cfg)
                    st.success("已完成岗位智能匹配排序！下方列表已按匹配度从高到低展示。")

        with b_clear:
            if st.button("🗑️ 清空 CV", key="cv_clear_btn", use_container_width=True):
                for k in ("cv_parsed_profile", "cv_matched_jobs", "cv_extracted_text"):
                    st.session_state.pop(k, None)
                st.rerun()

        if st.session_state.get("cv_extracted_text"):
            extracted = st.session_state["cv_extracted_text"]
            with st.expander(f"👀 查看从文件中提取的纯文本预览（共 {len(extracted)} 字符）", expanded=False):
                st.text(extracted[:2500])

        parsed_cv = st.session_state.get("cv_parsed_profile")
        if isinstance(parsed_cv, dict):
            st.markdown(f"##### ✨ 已解析科研求职画像（`{parsed_cv.get('parse_mode', '已解析')}` · 仅本次会话有效）")
            p1, p2, p3 = st.columns(3)
            p1.markdown(f"**当前阶段：** {parsed_cv.get('career_stage', '-')}")
            p2.markdown(f"**博士毕业年限：** {parsed_cv.get('years_after_phd', '-')}")
            p3.markdown(f"**建议岗位：** {', '.join(parsed_cv.get('target_roles') or [])}")
            st.markdown(f"**研究方向：** {', '.join(parsed_cv.get('research_areas') or [])}")
            st.markdown(f"**核心技能：** {', '.join(parsed_cv.get('skills') or [])}")
            if parsed_cv.get("highlights"):
                st.caption(f"代表性亮点：{parsed_cv['highlights']}")


def render_jobs_tab(
    base_jobs: list[dict[str, Any]],
    rss_warnings: list[str],
    config: AppConfig,
    llm_cfg: dict[str, str],
) -> None:
    st.subheader("💼 学术与产业研发求职聚合（含 CV 智能匹配）")
    st.caption("支持上传个人 CV 一键解析与匹配排序，整合精选岗位库、Nature Careers / EURAXESS 实时订阅及 acad-job 数据导入。")

    for w in rss_warnings:
        st.caption(f"ℹ️ {w}")

    uploaded_jobs = st.session_state.get("uploaded_jobs", [])
    all_jobs = uploaded_jobs + base_jobs

    render_cv_panel(llm_cfg, all_jobs)

    with st.expander("📤 导入自定义岗位数据（兼容 acad-job 导出的 CSV / JSON）", expanded=False):
        uploaded = st.file_uploader("拖入 CSV 或 JSON 文件，立即合并至岗位池", type=["csv", "json"], key="acad_job_uploader")
        if uploaded is not None:
            try:
                imported = parse_uploaded_jobs_file(uploaded)
                st.session_state["uploaded_jobs"] = imported
                st.success(f"成功导入 {len(imported)} 条岗位！")
            except Exception as exc:
                st.error(f"解析失败：{exc}")

    active_job_pool = st.session_state.get("cv_matched_jobs") or all_jobs

    col_kw, col_cat, col_loc = st.columns([3, 1.5, 1.5])
    with col_kw:
        default_jq = st.session_state.pop("job_query_prefill", st.session_state.get("job_kw", ""))
        job_kw = st.text_input("岗位关键词筛选（如 AI, postdoc, battery, 教授）", value=default_jq, key="job_kw")
    with col_cat:
        job_cat = st.selectbox("岗位类型", ["全部", "Faculty", "Postdoc", "PhD", "Research", "R&D"], key="job_cat")
    with col_loc:
        job_loc = st.selectbox("地区", ["全部", "China", "Hong Kong", "US", "Europe", "Global"], key="job_loc")

    default_profile = _format_cv_profile_text() or st.session_state.get("current_query", "")
    research_profile = st.text_input(
        "当前用于单岗分析的背景画像（解析 CV 后自动填充，也可手动微调）",
        value=default_profile,
        placeholder="例如：perovskite solar cells, device physics, Python, DFT",
        key="job_profile_input",
    )

    filtered = filter_jobs(active_job_pool, job_kw, job_cat, job_loc)

    jm1, jm2, jm3 = st.columns(3)
    jm1.metric("筛选命中岗位", len(filtered))
    jm2.metric("岗位池总量", len(all_jobs))
    jm3.metric("CV 自动匹配状态", "✅ 已按 CV 排序" if st.session_state.get("cv_matched_jobs") else "待触发")

    sub_list, sub_labs = st.tabs(["📋 在招岗位列表", "🏛️ OpenAlex 活跃课题组雷达（套磁线索）"])

    with sub_list:
        if not filtered:
            st.info("当前筛选条件下暂无岗位，请放宽关键词或导入新的 CSV/JSON。")
        fit_cache: dict[str, tuple[bool, str]] = st.session_state.setdefault("job_fit_cache", {})
        letter_cache: dict[str, str] = st.session_state.setdefault("job_letter_cache", {})

        for idx, job in enumerate(filtered[:40]):
            j_uid = f"{idx}_{job['title'][:20]}"
            with st.container(border=True):
                render_job_header_html(job)
                if job.get("ai_match_reason"):
                    st.caption(f"🎯 **匹配摘要：** {job['ai_match_reason']}")
                if job.get("description"):
                    with st.expander("查看岗位详情", expanded=False):
                        st.write(job["description"])

                jb1, jb2, jb3 = st.columns([1.4, 1.5, 1.1])
                with jb1:
                    if st.button("🤖 深度匹配分析", key=f"fit_{j_uid}", use_container_width=True):
                        with st.spinner("正在分析岗位匹配度…"):
                            fit_cache[j_uid] = llm_analyze_job_fit(
                                research_profile, job["title"], job["institution"], job.get("description", ""), llm_cfg
                            )
                with jb2:
                    if st.button("✉️ 生成套磁信", key=f"cl_{j_uid}", use_container_width=True):
                        with st.spinner("正在生成套磁信草稿…"):
                            letter_cache[j_uid] = llm_generate_cover_letter(
                                research_profile, job["title"], job["institution"], job.get("description", ""), llm_cfg
                            )
                with jb3:
                    if job.get("url"):
                        st.link_button("🔗 申请直达", job["url"], use_container_width=True)

                if j_uid in fit_cache:
                    is_llm, msg = fit_cache[j_uid]
                    if is_llm:
                        st.success(msg)
                    else:
                        st.info(msg)
                if j_uid in letter_cache:
                    st.code(letter_cache[j_uid], language="markdown")

    with sub_labs:
        radar_topic = st.text_input(
            "输入目标研究方向，检索近两年发文最活跃的高校/实验室",
            value=job_kw or st.session_state.get("current_query", "") or "perovskite solar cells",
            key="radar_topic_input",
        )
        if st.button("检索活跃课题组", type="primary", key="radar_search_btn"):
            with st.spinner("正在查询 OpenAlex 近两年机构发表数据…"):
                try:
                    st.session_state["radar_insts"] = fetch_active_institutions_for_topic(radar_topic, config)
                except Exception as exc:
                    st.warning(f"查询失败：{exc}")
        if st.session_state.get("radar_insts"):
            st.dataframe(st.session_state["radar_insts"], hide_index=True, use_container_width=True)


def render_grants_tab(
    base_grants: list[dict[str, Any]],
    config: AppConfig,
    llm_cfg: dict[str, str],
) -> None:
    """Fundlark 风格科研基金、Fellowship 发现、AI 资格核验与申请追踪器。"""
    st.subheader("💰 科研基金与青年资助聚合（灵感源自 Fundlark）")
    st.caption("面向博士生（PhD）、博士后（Postdoc）与青年学者（Early-Career）：一站检索资助目录、用自有大模型核验申请资格并追踪申报进度。")

    with st.expander("📤 导入自定义基金目录（支持 CSV / JSON 扩展）", expanded=False):
        g_up = st.file_uploader("拖入基金目录 CSV / JSON 文件", type=["csv", "json"], key="grant_file_uploader")
        if g_up is not None:
            try:
                imported = parse_uploaded_grants_file(g_up)
                st.session_state["uploaded_grants"] = imported
                st.success(f"成功导入 {len(imported)} 条基金项目！")
            except Exception as exc:
                st.error(f"解析失败：{exc}")

    all_grants = st.session_state.get("uploaded_grants", []) + base_grants
    tracker: list[dict[str, Any]] = st.session_state.setdefault("grant_tracker", [])

    sub_catalog, sub_tracker, sub_funders = st.tabs(
        [
            f"🔎 基金与 Fellowship 目录 ({len(all_grants)})",
            f"📌 我的申请追踪器 ({len(tracker)})",
            "🌐 OpenAlex 全球资助机构查询",
        ]
    )

    with sub_catalog:
        gc1, gc2, gc3 = st.columns([2.6, 1.5, 1.5])
        with gc1:
            g_kw = st.text_input("检索基金关键词（留空查看全部，如 MSCA, NSFC, Postdoc, AI）", key="grant_kw")
        with gc2:
            g_stage = st.selectbox("适用阶段", ["全部", "PhD", "Postdoc", "Early-Career"], key="grant_stage")
        with gc3:
            g_region = st.selectbox("资助地区", ["全部", "China", "Europe", "US", "Asia", "Global"], key="grant_region")

        applicant_bg = st.text_input(
            "你的背景信息（用于 AI 核验申请资格；上传解析 CV 后将自动带入）",
            value=_format_cv_profile_text(),
            placeholder="例如：2025年毕业博士，目前第1年博士后，方向为钙钛矿电池，中国籍",
            key="grant_applicant_bg",
        )

        filtered_grants = filter_grants(all_grants, g_kw, g_stage, g_region)
        elig_cache: dict[str, tuple[bool, str]] = st.session_state.setdefault("grant_elig_cache", {})
        tracked_names = {t["name"] for t in tracker}

        if not filtered_grants:
            st.info("当前筛选条件下暂无基金项目，请放宽条件或清空关键词。")

        for idx, grant in enumerate(filtered_grants):
            g_uid = f"{idx}_{grant['name'][:18]}"
            with st.container(border=True):
                render_grant_header_html(grant)
                if grant.get("description"):
                    st.caption(grant["description"])

                gb1, gb2, gb3 = st.columns([1.6, 1.4, 1.0])
                with gb1:
                    if st.button("🤖 AI 核验申请资格", key=f"elig_{g_uid}", use_container_width=True):
                        with st.spinner("正在核对基金资格与限制条款…"):
                            elig_cache[g_uid] = llm_check_grant_eligibility(applicant_bg, grant, llm_cfg)
                with gb2:
                    already = grant["name"] in tracked_names
                    btn_label = "✅ 已在追踪器中" if already else "⭐ 加入申请追踪"
                    if st.button(btn_label, key=f"trk_{g_uid}", disabled=already, use_container_width=True):
                        tracker.append(
                            {
                                "name": grant["name"],
                                "funder": grant["funder"],
                                "deadline": grant["deadline"],
                                "status": "待评估",
                                "notes": "",
                                "url": grant.get("url", ""),
                            }
                        )
                        st.toast(f"已将「{grant['name']}」加入申请追踪器！")
                        st.rerun()
                with gb3:
                    if grant.get("url"):
                        st.link_button("🔗 官方指南", grant["url"], use_container_width=True)

                if g_uid in elig_cache:
                    is_llm, msg = elig_cache[g_uid]
                    if is_llm:
                        st.success(msg)
                    else:
                        st.info(msg)

    with sub_tracker:
        st.caption("🔒 说明：追踪器保存在当前浏览器会话中，离开/刷新前请点击下方「导出追踪记录 CSV」备份进度，下次可一键导入恢复。")
        t_col1, t_col2 = st.columns([1.2, 1.8])
        with t_col1:
            if tracker:
                df_trk = pd.DataFrame(tracker)
                st.download_button(
                    "📥 导出追踪记录 CSV",
                    data=df_trk.to_csv(index=False).encode("utf-8-sig"),
                    file_name="fundlark_tracker.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        with t_col2:
            trk_up = st.file_uploader("恢复历史追踪 CSV", type=["csv"], key="trk_import_uploader", label_visibility="collapsed")
            if trk_up is not None and st.button("确认导入追踪记录", key="trk_import_btn"):
                try:
                    df_imp = pd.read_csv(trk_up).fillna("")
                    st.session_state["grant_tracker"] = df_imp.to_dict(orient="records")
                    st.success("已恢复追踪记录！")
                    st.rerun()
                except Exception as exc:
                    st.error(f"导入失败：{exc}")

        if not tracker:
            st.info("追踪器暂无记录，请在「🔎 基金与 Fellowship 目录」点击「⭐ 加入申请追踪」。")
        else:
            status_opts = ["待评估", "准备材料", "联系推荐人/东道主", "已提交", "已获批", "未通过"]
            for t_idx, item in enumerate(tracker):
                with st.container(border=True):
                    tc1, tc2, tc3, tc4 = st.columns([2.2, 1.3, 1.8, 0.7])
                    with tc1:
                        st.markdown(f"**{item['name']}**")
                        st.caption(f"{item['funder']} · 截止：{item['deadline']}")
                    with tc2:
                        cur_st = item.get("status", "待评估")
                        st_idx = status_opts.index(cur_st) if cur_st in status_opts else 0
                        item["status"] = st.selectbox(
                            "状态",
                            status_opts,
                            index=st_idx,
                            key=f"trk_status_{t_idx}",
                            label_visibility="collapsed",
                        )
                    with tc3:
                        item["notes"] = st.text_input(
                            "备注",
                            value=item.get("notes", ""),
                            placeholder="填写东道主/材料进度备注…",
                            key=f"trk_note_{t_idx}",
                            label_visibility="collapsed",
                        )
                    with tc4:
                        if st.button("🗑️", key=f"trk_del_{t_idx}", use_container_width=True):
                            tracker.pop(t_idx)
                            st.rerun()

    with sub_funders:
        funder_q = st.text_input(
            "检索全球科研资助机构（基于 OpenAlex Funders 免费实时数据）",
            value="National Science Foundation",
            key="oa_funder_q",
        )
        if st.button("查询资助机构", type="primary", key="oa_funder_btn"):
            with st.spinner("正在查询 OpenAlex Funders…"):
                try:
                    st.session_state["oa_funders_res"] = fetch_openalex_funders(funder_q, config)
                except Exception as exc:
                    st.warning(f"查询失败：{exc}")
        if st.session_state.get("oa_funders_res"):
            st.dataframe(
                st.session_state["oa_funders_res"],
                column_config={"官方主页": st.column_config.LinkColumn("官方主页")},
                hide_index=True,
                use_container_width=True,
            )


def render_support_and_collab_section() -> None:
    st.subheader("☕ 支持作者 & 🤝 商务/科研合作")
    c_coffee, c_collab = st.columns([1, 1.35])

    with c_coffee:
        with st.container(border=True):
            _render_html(
                '<div class="rf-support-box">'
                '<h4 style="margin:0 0 6px 0;">☕ 请作者喝一杯咖啡</h4>'
                '<p style="margin:0;font-size:13.5px;">'
                '本工具开源免费维护，帮助科研人员追踪前沿论文、匹配工作岗位与规划基金资助。欢迎扫码请作者喝杯咖啡！'
                '</p></div>'
            )
            st.write("")
            qr_path = find_qr_image_path()
            if qr_path:
                col_l, col_img, col_r = st.columns([1, 2, 1])
                with col_img:
                    st.image(qr_path, use_container_width=True, caption="扫码请作者喝杯咖啡 ☕")
            else:
                st.warning("尚未检测到二维码图片：请将您的收款二维码上传到仓库 `assets/coffee_qr.png`。")

    with c_collab:
        with st.container(border=True):
            _render_html(
                f'<div class="rf-collab-box">'
                f'<h4 style="margin:0 0 8px 0;">🤝 科研合作 · 数据对接 · 定制开发</h4>'
                f'<p style="margin:0 0 10px 0;font-size:14px;line-height:1.6;">欢迎围绕以下方向来信交流与合作：</p>'
                f'<ul style="margin:0 0 12px 0;padding-left:18px;font-size:13.5px;line-height:1.7;">'
                f'<li><b>高校 / 实验室 / 招聘平台</b>：学术岗位与资助数据对接与定制化展示</li>'
                f'<li><b>科技成果转化 / 投研团队</b>：特定学科产业化信号、专利与 TRL 情报流水线</li>'
                f'<li><b>AI + 科研工具开发</b>：CV 智能匹配、RAG 文献分析与科研 Agent 定制</li>'
                f'</ul>'
                f'<p style="margin:0;font-size:14px;">📩 <b>联系邮箱：</b>'
                f'<a href="mailto:{AUTHOR_EMAIL}" style="color:#1D4ED8;font-weight:700;">{AUTHOR_EMAIL}</a></p>'
                f'</div>'
            )
            st.write("")
            st.link_button(f"✉️ 发送邮件联系作者 ({AUTHOR_EMAIL})", f"mailto:{AUTHOR_EMAIL}", use_container_width=True)