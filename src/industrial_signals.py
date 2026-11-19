from __future__ import annotations

import os
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from src.academic_api import normalize_doi
from src.config import AppConfig, USER_AGENT


def score_to_grade(score: float | None) -> str:
    if score is None:
        return ""
    if score >= 0.75:
        return "A"
    if score >= 0.50:
        return "B"
    if score >= 0.25:
        return "C"
    return "D"


def load_commercial_potential_index(csv_path: str) -> dict[str, dict[str, Any]]:
    """Load precomputed commercial potential CSV (doi, compot, scipot) into an O(1) dict."""
    if not csv_path or not os.path.exists(csv_path):
        return {}
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return {}

    cols = {c.lower().strip(): c for c in df.columns}
    if "doi" not in cols or "compot" not in cols:
        return {}

    doi_col = cols["doi"]
    compot_col = cols["compot"]
    scipot_col = cols.get("scipot")

    index: dict[str, dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        raw_doi = getattr(row, doi_col, None)
        doi = normalize_doi(str(raw_doi) if raw_doi is not None else "")
        if not doi:
            continue
        try:
            compot_val = float(getattr(row, compot_col))
        except (TypeError, ValueError):
            continue
        scipot_val = None
        if scipot_col:
            try:
                scipot_val = float(getattr(row, scipot_col))
            except (TypeError, ValueError):
                scipot_val = None

        index[doi] = {
            "compot": round(compot_val, 3),
            "scipot": round(scipot_val, 3) if scipot_val is not None else None,
            "grade": score_to_grade(compot_val),
        }
    return index


def attach_commercial_potential(
    papers: list[dict[str, Any]], compot_index: dict[str, dict[str, Any]]
) -> None:
    for paper in papers:
        doi = paper.get("doi") or ""
        hit = compot_index.get(doi) if doi else None
        if hit:
            paper["compot_grade"] = hit["grade"]
            paper["compot_score"] = hit["compot"]
            paper["scipot_score"] = hit["scipot"]
        else:
            paper["compot_grade"] = None
            paper["compot_score"] = None
            paper["scipot_score"] = None


def assess_trl_via_apify(
    technology_name: str, description: str, config: AppConfig
) -> dict[str, Any]:
    """Call Apify Technology Readiness Assessment Actor on demand."""
    if not config.apify_api_token:
        raise RuntimeError("未配置 APIFY_API_TOKEN 环境变量")

    actor_id = config.apify_trl_actor_id
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {
        "technology": technology_name,
        "topic": technology_name,
        "query": technology_name,
        "description": description[:1200],
    }
    resp = requests.post(
        url,
        params={"token": config.apify_api_token},
        json=payload,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=45,
    )
    resp.raise_for_status()
    items = resp.json()
    if not items or not isinstance(items, list):
        raise ValueError("Apify 返回结果为空")

    first = items[0] if isinstance(items[0], dict) else {}
    # Normalize common TRL field variations across Apify TRL/Tech Scouting actors
    raw_trl = (
        first.get("trl")
        or first.get("TRL")
        or first.get("trl_level")
        or first.get("technology_readiness_level")
        or first.get("readinessLevel")
    )
    trl_num = None
    if raw_trl is not None:
        digits = "".join(ch for ch in str(raw_trl) if ch.isdigit())
        if digits:
            trl_num = max(1, min(9, int(digits[0])))

    summary = (
        first.get("verdict")
        or first.get("summary")
        or first.get("rationale")
        or first.get("assessment")
        or first.get("reasoning")
        or "已完成云端 TRL 评估。"
    )
    return {
        "trl": trl_num,
        "summary": str(summary)[:500],
        "raw": first,
    }


def fetch_arxiv_90d_trend(query: str, config: AppConfig) -> list[dict[str, Any]]:
    """Fetch up to 120 recent arXiv matches for a topic and bucket by week over last 90 days."""
    q_encoded = urllib.parse.quote(f"all:{query}")
    url = (
        f"https://export.arxiv.org/api/query?search_query={q_encoded}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results=120"
    )
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=config.request_timeout)
    resp.raise_for_status()

    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).date()
    week_counts: Counter[str] = Counter()

    for entry in root.findall("a:entry", ns):
        pub_el = entry.find("a:published", ns)
        if pub_el is None or not pub_el.text:
            continue
        try:
            dt = datetime.strptime(pub_el.text[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if dt < cutoff:
            continue
        # Group by Monday of each week for clean trend display
        week_start = dt - timedelta(days=dt.weekday())
        week_counts[week_start.isoformat()] += 1

    return [
        {"week": wk, "papers": week_counts[wk]}
        for wk in sorted(week_counts.keys())
    ]


def fetch_patentsview_signal(query: str, config: AppConfig) -> dict[str, Any]:
    """Optional USPTO PatentsView v1 patent count over the last 3 years."""
    if not config.patentsview_api_key:
        return {"available": False, "reason": "未配置 PATENTSVIEW_API_KEY"}

    since_date = (datetime.now(timezone.utc) - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    q_json = {
        "_and": [
            {"_gte": {"patent_date": since_date}},
            {"_text_any": {"patent_title": query}},
        ]
    }
    resp = requests.get(
        "https://search.patentsview.org/api/v1/patent/",
        params={
            "q": str(q_json).replace("'", '"'),
            "f": '["patent_id","patent_title","patent_date"]',
            "o": '{"size":1}',
        },
        headers={"X-Api-Key": config.patentsview_api_key, "User-Agent": USER_AGENT},
        timeout=config.request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "available": True,
        "total_hits": data.get("total_hits", 0),
        "since": since_date,
    }