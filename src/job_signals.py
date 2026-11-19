from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

import pandas as pd
import requests

from src.config import USER_AGENT

ACADEMIC_RSS_FEEDS = {
    "Nature Careers": "https://www.nature.com/naturecareers/rss",
    "EURAXESS EU": "https://euraxess.ec.europa.eu/job-feed",
}


def _normalize_job_row(row: dict[str, Any], default_source: str = "岗位库") -> dict[str, Any] | None:
    lower_map = {str(k).lower().strip(): v for k, v in row.items()}
    title = str(
        lower_map.get("title")
        or lower_map.get("position")
        or lower_map.get("job_title")
        or lower_map.get("name")
        or ""
    ).strip()
    if not title or title.lower() == "nan":
        return None

    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            val = lower_map.get(k)
            if val is not None and str(val).strip() and str(val).strip().lower() != "nan":
                return str(val).strip()
        return default

    return {
        "title": title,
        "institution": pick("institution", "org", "organization", "university", "school", "company", default="科研机构/高校"),
        "location": pick("location", "country", "city", "region", default="未标注地区"),
        "category": pick("category", "job_type", "type", "rank", default="Academic / R&D"),
        "salary": pick("salary", "compensation", "stipend", default="面议 / 参照标准"),
        "deadline": pick("deadline", "closing_date", "ddl", "date", default="招满为止"),
        "tags": pick("tags", "field", "discipline", "keywords", default=""),
        "url": pick("url", "link", "apply_url", "source_url", default=""),
        "description": pick("description", "summary", "requirements", "detail", default=""),
        "source": pick("source", default=default_source),
    }


def load_static_jobs(csv_path: str = "data/academic_jobs.csv") -> list[dict[str, Any]]:
    if not csv_path or not os.path.exists(csv_path):
        return []
    try:
        df = pd.read_csv(csv_path).fillna("")
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        norm = _normalize_job_row(row, default_source="精选岗位库")
        if norm:
            out.append(norm)
    return out


def parse_uploaded_jobs_file(uploaded_file: Any) -> list[dict[str, Any]]:
    """兼容导入 acad-job 等外部爬虫导出的 CSV 或 JSON 文件。"""
    name = (uploaded_file.name or "").lower()
    raw_rows: list[dict[str, Any]] = []
    if name.endswith(".json"):
        payload = json.load(uploaded_file)
        if isinstance(payload, list):
            raw_rows = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            for key in ("jobs", "data", "results", "items"):
                if isinstance(payload.get(key), list):
                    raw_rows = [r for r in payload[key] if isinstance(r, dict)]
                    break
    else:
        df = pd.read_csv(uploaded_file).fillna("")
        raw_rows = df.to_dict(orient="records")

    parsed: list[dict[str, Any]] = []
    for r in raw_rows:
        norm = _normalize_job_row(r, default_source=f"导入:{uploaded_file.name}")
        if norm:
            parsed.append(norm)
    return parsed


def fetch_live_academic_job_feeds(timeout: int = 10) -> tuple[list[dict[str, Any]], list[str]]:
    jobs: list[dict[str, Any]] = []
    warnings: list[str] = []

    for feed_name, url in ACADEMIC_RSS_FEEDS.items():
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item")[:20]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
                desc = re.sub(r"\s+", " ", desc).strip()
                pub = (item.findtext("pubDate") or "")[:16]
                if title:
                    jobs.append(
                        {
                            "title": title,
                            "institution": feed_name,
                            "location": "International / Europe" if "EURAXESS" in feed_name else "Global",
                            "category": "Faculty / Postdoc / PhD",
                            "salary": "参照官方公告",
                            "deadline": pub or "见链接",
                            "tags": "Academic RSS",
                            "url": link,
                            "description": desc[:700],
                            "source": f"实时订阅·{feed_name}",
                        }
                    )
        except Exception:
            warnings.append(f"招聘实时订阅暂不可用：{feed_name}（已自动保留本地库岗位）")
    return jobs, warnings


def filter_jobs(
    jobs: list[dict[str, Any]],
    keyword: str = "",
    category_filter: str = "全部",
    location_filter: str = "全部",
) -> list[dict[str, Any]]:
    kw = keyword.strip().lower()
    out: list[dict[str, Any]] = []
    for job in jobs:
        if category_filter != "全部" and category_filter.lower() not in job["category"].lower() and category_filter.lower() not in job["title"].lower():
            continue
        if location_filter != "全部" and location_filter.lower() not in job["location"].lower():
            continue
        if kw:
            haystack = " ".join(
                [job["title"], job["institution"], job["location"], job["tags"], job["description"]]
            ).lower()
            if not all(part in haystack for part in kw.split()):
                continue
        out.append(job)
    return out