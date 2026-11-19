from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import requests

from src.config import AppConfig, USER_AGENT

BUILTIN_GRANTS: list[dict[str, Any]] = [
    {
        "name": "国家自然科学基金青年科学基金项目（C类）",
        "funder": "国家自然科学基金委员会 (NSFC)",
        "stage": "Early-Career / Postdoc",
        "region": "China",
        "amount": "约 30 万元人民币",
        "deadline": "每年 3 月集中接收",
        "eligibility": "具有博士学位或高级职称，男性未满35周岁、女性未满38周岁（以当年指南为准）",
        "tags": "All Disciplines; Basic Research",
        "url": "https://www.nsfc.gov.cn/",
        "description": "支持青年科学技术人员在科学基金资助范围内自主选题，开展基础研究工作。",
        "source": "精选基金库",
    },
    {
        "name": "中国博士后科学基金面上资助",
        "funder": "中国博士后科学基金会",
        "stage": "Postdoc",
        "region": "China",
        "amount": "自然科学 8 万元 / 社科 5 万元",
        "deadline": "每年 3 月与 9 月两批次",
        "eligibility": "在站博士后研究人员（进站 18 个月内可申请）",
        "tags": "Postdoc; All Disciplines",
        "url": "https://jj.chinapostdoctor.org.cn/",
        "description": "资助在站博士后开展自主创新研究。",
        "source": "精选基金库",
    },
    {
        "name": "Marie Skłodowska-Curie Actions (MSCA) Postdoctoral Fellowships",
        "funder": "European Commission (Horizon Europe)",
        "stage": "Postdoc",
        "region": "Europe / Global",
        "amount": "全额薪资+生活与科研津贴（2年）",
        "deadline": "每年 9 月中旬",
        "eligibility": "拥有博士学位且博士后科研经历不超过 8 年，需满足跨国流动规则（Mobility Rule）",
        "tags": "Postdoc; Mobility; All Disciplines",
        "url": "https://marie-sklodowska-curie-actions.github.io/",
        "description": "欧盟最著名的博士后个人资助项目，面向全球各学科优秀青年博士。",
        "source": "精选基金库",
    },
    {
        "name": "ERC Starting Grant",
        "funder": "European Research Council",
        "stage": "Early-Career Faculty",
        "region": "Europe",
        "amount": "最高 150 万欧元（5年）",
        "deadline": "每年 10 月前后",
        "eligibility": "获博士学位后 2–7 年，已展现独立科研领导力与高水平成果",
        "tags": "PI; Independent Lab; Frontier Research",
        "url": "https://erc.europa.eu/",
        "description": "支持极具潜力的青年PI在欧洲建立独立研究团队。",
        "source": "精选基金库",
    },
    {
        "name": "Humboldt Research Fellowship for Postdocs",
        "funder": "Alexander von Humboldt Foundation",
        "stage": "Postdoc",
        "region": "Europe (Germany)",
        "amount": "每月约 2670 欧元+差旅补贴",
        "deadline": "全年滚动受理",
        "eligibility": "获博士学位不超过 4 年，需找到德国东道主教授（Host）",
        "tags": "Postdoc; Germany; All Disciplines",
        "url": "https://www.humboldt-foundation.de/",
        "description": "资助全球优秀青年学者赴德国高校或科研机构开展 6–24 个月合作研究。",
        "source": "精选基金库",
    },
    {
        "name": "JSPS Postdoctoral Fellowship (Standard)",
        "funder": "Japan Society for the Promotion of Science",
        "stage": "Postdoc",
        "region": "Asia (Japan)",
        "amount": "每月 36.2 万日元+科研启动费",
        "deadline": "每年分批次受理",
        "eligibility": "获博士学位不超过 6 年，需日本接收单位合作学者共同申请",
        "tags": "Postdoc; Japan; International",
        "url": "https://www.jsps.go.jp/",
        "description": "日本学术振兴会面向海外优秀青年博士后的标准资助计划。",
        "source": "精选基金库",
    },
    {
        "name": "NIH K99/R00 Pathway to Independence Award",
        "funder": "National Institutes of Health (NIH)",
        "stage": "Postdoc / Early-Career",
        "region": "US",
        "amount": "K99约10万美元/年，R00最高24.9万美元/年",
        "deadline": "每年 2月 / 6月 / 10月",
        "eligibility": "申请时博士后研究经历不超过 4 年，适合准备过渡到独立PI的生命科学/医学学者",
        "tags": "Biomedical; Life Sciences; Transition",
        "url": "https://grants.nih.gov/",
        "description": "助力博士后向独立教职PI过渡的黄金衔接基金。",
        "source": "精选基金库",
    },
    {
        "name": "Google PhD Fellowship",
        "funder": "Google Research",
        "stage": "PhD",
        "region": "Global",
        "amount": "覆盖学费、生活津贴及导师对接（2–3年）",
        "deadline": "每年 4–5 月开放院校提名",
        "eligibility": "在读全职博士生，研究方向属于 AI、机器学习、系统、安全、量子计算等",
        "tags": "PhD; AI; CS; Industry Fellowship",
        "url": "https://research.google/programs-and-conferences/phd-fellowship/",
        "description": "面向全球顶尖计算机及人工智能方向博士生的知名企业奖学金。",
        "source": "精选基金库",
    },
    {
        "name": "Microsoft Research PhD Fellowship",
        "funder": "Microsoft Research",
        "stage": "PhD",
        "region": "US / Asia / Global",
        "amount": "含全额学费与研究津贴",
        "deadline": "每年按地区开放院校提名",
        "eligibility": "研究方向与计算机科学、AI、科学计算、人机交互相关的博士生",
        "tags": "PhD; AI; CS; Industry",
        "url": "https://www.microsoft.com/en-us/research/",
        "description": "微软研究院博士生奖学金计划。",
        "source": "精选基金库",
    },
    {
        "name": "Hong Kong RGC Postdoctoral Fellowship Scheme (PDFS)",
        "funder": "Research Grants Council (RGC) Hong Kong",
        "stage": "Postdoc",
        "region": "China (Hong Kong)",
        "amount": "每年约 43 万港币薪资+差旅津贴",
        "deadline": "每年 10–12 月院校推荐",
        "eligibility": "即将或近三年内获得博士学位的全球优秀青年学者",
        "tags": "Postdoc; Hong Kong; All Disciplines",
        "url": "https://www.ugc.edu.hk/",
        "description": "香港研资局博士后研究资助计划，支持赴港八大高校开展研究。",
        "source": "精选基金库",
    },
    {
        "name": "Newton International Fellowships",
        "funder": "The Royal Society / British Academy",
        "stage": "Postdoc",
        "region": "Europe (UK)",
        "amount": "每年 4.2 万英镑免税津贴+科研费（2年）",
        "deadline": "每年 3 月前后",
        "eligibility": "非英国国籍且获得博士学位不超过 7 年，需英国接收机构合作者",
        "tags": "Postdoc; UK; Natural Sciences",
        "url": "https://royalsociety.org/",
        "description": "英国皇家学会面向海外优秀博士后的全额资助计划。",
        "source": "精选基金库",
    },
    {
        "name": "腾讯「科学探索奖」（Xplorer Prize）",
        "funder": "新基石科学基金会",
        "stage": "Early-Career Faculty",
        "region": "China",
        "amount": "总计 300 万元人民币（分5年，可自由支配）",
        "deadline": "每年 1–4 月申报",
        "eligibility": "45 周岁及以下，在中国内地及港澳地区全职工作的青年科学家",
        "tags": "Early-Career; Basic Science; Frontier",
        "url": "https://xplorerprize.org/",
        "description": "面向基础科学和前沿技术领域青年科技工作者的公益性奖励项目。",
        "source": "精选基金库",
    },
]


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
    if csv_path and os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, on_bad_lines="skip").fillna("")
            out: list[dict[str, Any]] = []
            for row in df.to_dict(orient="records"):
                norm = _normalize_grant_row(row)
                if norm:
                    out.append(norm)
            if out:
                return out
        except Exception:
            pass
    return list(BUILTIN_GRANTS)


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
        df = pd.read_csv(uploaded_file, on_bad_lines="skip").fillna("")
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