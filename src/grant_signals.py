from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import requests

from src.config import AppConfig, USER_AGENT


def _normalize_grant_row(row: dict[str, Any], default_source: str = "精选基金库") -> dict[str, Any] | None:
    lower_map = {str(k).lower().strip(): v for k, v in row.items()}
    name = str(
        lower_map.get("name")
        or lower_map.get("title")
        or lower_map.get("grant_name")
        or ""
    ).strip()
    if not name or name.lower() == "nan":
        return None

    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            val = lower_map.get(k)
            if val is not None and str(val).strip() and str(val).strip().lower() != "nan":
                return str(val).strip()
        return default

    return {
        "name": name,
        "funder": pick("funder", "agency", "sponsor", "organization", default="资助机构"),
        "stage": pick("stage", "career_stage", "level", default="Postdoc / Early-Career"),
        "region": pick("region", "country", "location", default="Global"),
        "amount": pick("amount", "funding", "award", default="见官方资助细则"),
        "deadline": pick("deadline", "ddl", "cycle", default="年度周期 / 见官网"),
        "eligibility": pick("eligibility", "requirements", default="需满足所在阶段科研资历要求"),
        "tags": pick("tags", "field", "discipline", default="All Disciplines"),
        "url": pick("url", "link", "official_url", default=""),
        "description": pick("description", "summary", default=""),
        "source": pick("source", default=default_source),
    }


def load_static_grants(csv_path: str = "data/research_grants.csv") -> list[dict[str, Any]]:
    if not csv_path or not os.path.exists(csv_path):
        return []
    try:
        df = pd.read_csv(csv_path).fillna("")
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        norm = _normalize_grant_row(row)
        if norm:
            out.append(norm)
    return out


def parse_uploaded_grants_file(uploaded_file: Any) -> list[dict[str, Any]]:
    name = (uploaded_file.name or "").lower()
    raw_rows: list[dict[str, Any]] = []
    if name.endswith(".json"):
        payload = json.load(uploaded_file)
        if isinstance(payload, list):
            raw_rows = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            for key in ("grants", "fundings", "data", "items"):
                if isinstance(payload.get(key), list):
                    raw_rows = [r for r in payload[key] if isinstance(r, dict)]
                    break
    else:
        df = pd.read_csv(uploaded_file).fillna("")
        raw_rows = df.to_dict(orient="records")

    out: list[dict[str, Any]] = []
    for r in raw_rows:
        norm = _normalize_grant_row(r, default_source=f"导入:{uploaded_file.name}")
        if norm:
            out.append(norm)
    return out


def filter_grants(
    grants: list[dict[str, Any]],
    keyword: str = "",
    stage_filter: str = "全部",
    region_filter: str = "全部",
) -> list[dict[str, Any]]:
    kw = keyword.strip().lower()
    out: list[dict[str, Any]] = []
    for g in grants:
        if stage_filter != "全部" and stage_filter.lower() not in g["stage"].lower():
            continue
        if region_filter != "全部" and region_filter.lower() not in g["region"].lower():
            continue
        if kw:
            haystack = " ".join(
                [g["name"], g["funder"], g["stage"], g["region"], g["eligibility"], g["tags"], g["description"]]
            ).lower()
            if not all(part in haystack for part in kw.split()):
                continue
        out.append(g)
    return out


def fetch_openalex_funders(query: str, config: AppConfig, limit: int = 12) -> list[dict[str, Any]]:
    """通过 OpenAlex Funders 免费接口检索全球资助机构及其资助影响力。"""
    params: dict[str, Any] = {
        "search": query,
        "per-page": limit,
        "select": "id,display_name,country_code,homepage_url,works_count,cited_by_count,description",
    }
    if config.openalex_api_key:
        params["api_key"] = config.openalex_api_key

    resp = requests.get(
        "https://api.openalex.org/funders",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=config.request_timeout,
    )
    resp.raise_for_status()
    items = resp.json().get("results", [])

    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "资助机构": item.get("display_name") or "Unknown",
                "国家/地区": item.get("country_code") or "-",
                "资助产出论文数": item.get("works_count") or 0,
                "总被引次数": item.get("cited_by_count") or 0,
                "官方主页": item.get("homepage_url") or "",
                "简介": (item.get("description") or "")[:140],
            }
        )
    return rows