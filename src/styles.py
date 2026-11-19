from __future__ import annotations

import html
import os
from typing import Any

import streamlit as st


def _render_html(raw_html: str) -> None:
    """剥离行首缩进与空行，防止 Streamlit Markdown 将 HTML 误判为缩进代码块。"""
    cleaned = "\n".join(line.lstrip() for line in raw_html.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


def find_qr_image_path() -> str | None:
    candidates = [
        "assets/coffee_qr.png",
        "assets/coffee_qr.jpg",
        "assets/coffee_qr.jpeg",
        "assets/coffee_qr.webp",
        "coffee_qr.png",
        "coffee_qr.jpg",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def inject_custom_css() -> None:
    _render_html(
        """
        <style>
        .stApp {
            background-color: #F8FAFC;
            color: #0F172A;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
            max-width: 1220px;
        }
        section[data-testid="stSidebar"] {
            background-color: #F1F5F9;
            border-right: 1px solid #E2E8F0;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: #EEF2FF;
            padding: 6px;
            border-radius: 14px;
            border: 1px solid #E0E7FF;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            border-radius: 10px;
            padding: 0 16px;
            font-weight: 600;
            color: #475569;
            border: none !important;
            background-color: transparent;
            transition: all 0.2s ease;
        }
        .stTabs [aria-selected="true"] {
            background-color: #FFFFFF !important;
            color: #1E3A8A !important;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
        }
        .stTabs [data-baseweb="tab-highlight"] {
            display: none;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0 !important;
            border-radius: 14px !important;
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.03);
            transition: box-shadow 0.15s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: 0 6px 20px rgba(30, 58, 138, 0.07);
        }
        .stButton > button, .stLinkButton > a, .stDownloadButton > button {
            border-radius: 10px !important;
            font-weight: 500 !important;
            transition: all 0.15s ease !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #1E3A8A 0%, #4F46E5 100%) !important;
            border: none !important;
            color: #FFFFFF !important;
        }
        .rf-hero {
            background: linear-gradient(135deg, #0F172A 0%, #1E293B 55%, #312E81 100%);
            border-radius: 18px;
            padding: 24px 28px;
            color: #F8FAFC;
            margin-bottom: 18px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
        }
        .rf-hero-pill {
            display: inline-block;
            background: rgba(99, 102, 241, 0.25);
            border: 1px solid rgba(165, 180, 252, 0.35);
            color: #C7D2FE;
            font-size: 12px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 999px;
            margin-bottom: 10px;
        }
        .rf-hero h1 {
            margin: 0 0 8px 0;
            font-size: 27px;
            font-weight: 700;
            color: #FFFFFF;
        }
        .rf-hero p {
            margin: 0;
            font-size: 14.5px;
            color: #CBD5E1;
            line-height: 1.55;
        }
        .rf-kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 18px;
            align-items: stretch;
        }
        @media (max-width: 900px) {
            .rf-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        .rf-kpi-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-top: 3px solid #4F46E5;
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
        }
        .rf-kpi-label { font-size: 12.5px; color: #64748B; font-weight: 600; margin-bottom: 4px; }
        .rf-kpi-val { font-size: 20px; font-weight: 700; color: #0F172A; }
        .rf-kpi-sub { font-size: 11.5px; color: #94A3B8; margin-top: 2px; }
        .rf-badges { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 8px; }
        .rf-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            line-height: 1.5;
        }
        .rf-badge-preprint { background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A; }
        .rf-badge-pub { background: #E0E7FF; color: #1E40AF; border: 1px solid #C7D2FE; }
        .rf-badge-prov { background: #F1F5F9; color: #475569; border: 1px solid #E2E8F0; }
        .rf-badge-grade-ab { background: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0; }
        .rf-badge-grade-cd { background: #F3F4F6; color: #4B5563; border: 1px solid #E5E7EB; }
        .rf-badge-trl { background: #FCE7F3; color: #9D174D; border: 1px solid #FBCFE8; }
        .rf-badge-job { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
        .rf-badge-score-hi { background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }
        .rf-badge-score-mid { background: #FEF9C3; color: #854D0E; border: 1px solid #FDE047; }
        .rf-badge-grant { background: #EDE9FE; color: #5B21B6; border: 1px solid #DDD6FE; }
        .rf-card-title {
            font-size: 17px;
            font-weight: 700;
            color: #0F172A;
            text-decoration: none;
            line-height: 1.4;
            display: block;
            margin-bottom: 6px;
        }
        .rf-card-title:hover { color: #4F46E5; text-decoration: underline; }
        .rf-meta { font-size: 13px; color: #475569; margin-bottom: 10px; line-height: 1.5; }
        .rf-support-box {
            background: linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%);
            border: 1px solid #FDE68A;
            border-radius: 14px;
            padding: 16px 20px;
            color: #78350F;
        }
        .rf-collab-box {
            background: linear-gradient(135deg, #EFF6FF 0%, #EEF2FF 100%);
            border: 1px solid #BFDBFE;
            border-radius: 14px;
            padding: 16px 20px;
            color: #1E3A8A;
        }
        .rf-footer {
            margin-top: 28px;
            padding: 16px 20px;
            border-top: 1px solid #E2E8F0;
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            color: #64748B;
            font-size: 13px;
        }
        </style>
        """
    )


def render_hero_banner() -> None:
    _render_html(
        """
        <div class="rf-hero">
            <div class="rf-hero-pill">MODELSCOPE STUDIO · 科研情报 × 产业化信号 × 简历求职 × 基金资助</div>
            <h1>🔬 科研前沿 × 产业化与学术发展聚合器</h1>
            <p>追踪今日预印本前沿、评估商业潜力与 TRL 就绪度，上传 CV 自动匹配高校/研发岗位，并一站发现与追踪科研基金资助。</p>
        </div>
        """
    )


def render_kpi_cards(items: list[dict[str, str]]) -> None:
    cards = []
    for it in items:
        color = html.escape(it.get("color", "#4F46E5"))
        label = html.escape(it["label"])
        value = html.escape(it["value"])
        sub = html.escape(it.get("sub", ""))
        cards.append(
            f'<div class="rf-kpi-card" style="border-top-color:{color};">'
            f'<div class="rf-kpi-label">{label}</div>'
            f'<div class="rf-kpi-val">{value}</div>'
            f'<div class="rf-kpi-sub">{sub}</div>'
            f'</div>'
        )
    _render_html(f'<div class="rf-kpi-grid">{"".join(cards)}</div>')


def render_paper_header_html(
    paper: dict[str, Any], trl_info: dict[str, Any] | None, compot_loaded: bool
) -> None:
    is_pre = paper.get("is_preprint", False)
    badge_cls = "rf-badge-preprint" if is_pre else "rf-badge-pub"
    badge_text = html.escape(paper.get("source_badge", "学术文献"))
    providers = html.escape(" + ".join(paper.get("providers", [])))

    badges = [
        f'<span class="rf-badge {badge_cls}">{badge_text}</span>',
        f'<span class="rf-badge rf-badge-prov">{providers}</span>',
    ]

    grade = paper.get("compot_grade") or (trl_info or {}).get("commercial_grade")
    if grade:
        g_cls = "rf-badge-grade-ab" if grade in ("A", "B") else "rf-badge-grade-cd"
        score_txt = f" ({paper['compot_score']})" if paper.get("compot_score") is not None else " (AI)"
        badges.append(
            f'<span class="rf-badge {g_cls}">商业潜力 {html.escape(str(grade))}{html.escape(score_txt)}</span>'
        )
    elif compot_loaded:
        badges.append('<span class="rf-badge rf-badge-grade-cd">暂无预计算评分</span>')

    if trl_info and trl_info.get("trl"):
        badges.append(f'<span class="rf-badge rf-badge-trl">TRL {int(trl_info["trl"])}/9</span>')

    title = html.escape(paper.get("title", "Untitled"))
    url = paper.get("url") or paper.get("pdf_url") or ""
    if url:
        title_html = f'<a class="rf-card-title" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{title}</a>'
    else:
        title_html = f'<div class="rf-card-title">{title}</div>'

    authors_str = html.escape(", ".join(paper.get("authors", [])[:4]) or "未知作者")
    insts = paper.get("institutions") or []
    inst_html = f" &nbsp;·&nbsp; 🏛️ {html.escape(', '.join(insts[:2]))}" if insts else ""
    pub_date = html.escape(paper.get("pub_date") or "未知日期")
    citations = int(paper.get("citation_count") or 0)

    _render_html(
        f'<div class="rf-badges">{"".join(badges)}</div>'
        f'{title_html}'
        f'<div class="rf-meta">👤 {authors_str}{inst_html} &nbsp;·&nbsp; 📅 {pub_date} &nbsp;·&nbsp; 📈 引用 <b>{citations}</b></div>'
    )


def render_job_header_html(job: dict[str, Any]) -> None:
    source = html.escape(job.get("source", "岗位库"))
    category = html.escape(job.get("category", "Academic / R&D"))
    badges = [
        f'<span class="rf-badge rf-badge-job">{source}</span>',
        f'<span class="rf-badge rf-badge-pub">{category}</span>',
    ]
    if job.get("ai_match_score") is not None:
        sc = int(job["ai_match_score"])
        sc_cls = "rf-badge-score-hi" if sc >= 70 else "rf-badge-score-mid"
        badges.append(f'<span class="rf-badge {sc_cls}">CV 匹配度 {sc}%</span>')

    title = html.escape(job.get("title", "Untitled Position"))
    url = job.get("url") or ""
    if url:
        title_html = f'<a class="rf-card-title" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{title}</a>'
    else:
        title_html = f'<div class="rf-card-title">{title}</div>'

    inst = html.escape(job.get("institution", ""))
    loc = html.escape(job.get("location", ""))
    salary = html.escape(job.get("salary", ""))
    deadline = html.escape(job.get("deadline", ""))
    tags = html.escape(job.get("tags", ""))
    tags_html = f" &nbsp;·&nbsp; 🔖 <code>{tags}</code>" if tags else ""

    _render_html(
        f'<div class="rf-badges">{"".join(badges)}</div>'
        f'{title_html}'
        f'<div class="rf-meta">🏛️ <b>{inst}</b> &nbsp;·&nbsp; 📍 {loc} &nbsp;·&nbsp; 💰 {salary} &nbsp;·&nbsp; ⏰ 截止：{deadline}{tags_html}</div>'
    )


def render_grant_header_html(grant: dict[str, Any]) -> None:
    source = html.escape(grant.get("source", "精选基金库"))
    stage = html.escape(grant.get("stage", "Postdoc"))
    region = html.escape(grant.get("region", "Global"))
    name = html.escape(grant.get("name", "Untitled Grant"))
    url = grant.get("url") or ""
    if url:
        title_html = f'<a class="rf-card-title" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{name}</a>'
    else:
        title_html = f'<div class="rf-card-title">{name}</div>'

    funder = html.escape(grant.get("funder", ""))
    amount = html.escape(grant.get("amount", ""))
    deadline = html.escape(grant.get("deadline", ""))
    elig = html.escape(grant.get("eligibility", ""))

    _render_html(
        f'<div class="rf-badges">'
        f'<span class="rf-badge rf-badge-grant">{source}</span>'
        f'<span class="rf-badge rf-badge-pub">{stage}</span>'
        f'<span class="rf-badge rf-badge-prov">{region}</span>'
        f'</div>'
        f'{title_html}'
        f'<div class="rf-meta">🏛️ <b>{funder}</b> &nbsp;·&nbsp; 💵 {amount} &nbsp;·&nbsp; ⏰ 周期/截止：{deadline}<br/>📋 <b>申请资格：</b>{elig}</div>'
    )


def render_footer_html(email: str) -> None:
    safe_email = html.escape(email)
    _render_html(
        f'<div class="rf-footer">'
        f'<div>🔬 <b>科研前沿 × 产业化与学术发展聚合器</b> · ModelScope Studio Edition</div>'
        f'<div>☕ 请作者喝咖啡 · 🤝 合作邮箱：<a href="mailto:{safe_email}">{safe_email}</a></div>'
        f'</div>'
    )