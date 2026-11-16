#!/usr/bin/env python3
"""Scaffold Phase 1 files for the academic job matcher skill."""

from __future__ import annotations

import argparse
from pathlib import Path


FILES = {
    "schema.py": r'''
"""Unified schemas for academic jobs and candidate profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, List, Optional

POSITION_LEVELS = [
    "RA",
    "Masters",
    "PhD",
    "Postdoc",
    "AssistantProf",
    "AssociateProf",
    "FullProf",
    "ResearchFellow",
    "ResearchScientist",
]


@dataclass
class Job:
    job_id: str
    source: str
    title: str
    position_level: str
    institution: str
    country: str
    city: str
    discipline: str
    deadline: Optional[str]
    posted_date: str
    url: str
    description_full: str
    requirements_extracted: List[str] = field(default_factory=list)
    funding_duration: Optional[str] = None
    match_score: Optional[int] = None
    match_reasons: Optional[List[str]] = field(default_factory=list)


@dataclass
class AcademicProfile:
    degrees: List[str] = field(default_factory=list)
    expected_graduation: Optional[str] = None
    research_areas: List[str] = field(default_factory=list)
    publication_count: int = 0
    first_or_corresponding_count: int = 0
    top_venues: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    position_level_range: List[str] = field(default_factory=list)
    accepted_countries: List[str] = field(default_factory=list)
    parsing_note: Optional[str] = None


def job_to_dict(job: Job) -> dict:
    return asdict(job)


def validate_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise ValueError("profile must be a JSON object")
    areas = profile.get("research_areas", [])
    if not isinstance(areas, list) or not (3 <= len(areas) <= 8):
        raise ValueError("research_areas must contain 3-8 items")
    levels = profile.get("position_level_range", [])
    if levels and not set(levels) <= set(POSITION_LEVELS):
        raise ValueError(f"position_level_range must be subset of {POSITION_LEVELS}")
'''
,
    "job_adapters/ajo.py": r'''
"""AcademicJobsOnline adapter for Phase 1."""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, List, Optional

import requests

from schema import Job

# CONFIGURE: verify the actual AcademicJobsOnline public JSON API endpoint.
AJO_API_URL = os.environ.get("AJO_API_URL", "https://api.academicjobsonline.org/v1/jobs")
# AJO requires 5 seconds/page crawl delay.
AJO_CRAWL_DELAY_SECONDS = float(os.environ.get("AJO_CRAWL_DELAY_SECONDS", "5"))


def fetch_ajo_jobs(params: Optional[dict] = None) -> List[Job]:
    """Fetch jobs from AJO and map them to the unified Job schema."""
    time.sleep(AJO_CRAWL_DELAY_SECONDS)
    response = requests.get(AJO_API_URL, params=params or {}, timeout=30)
    response.raise_for_status()
    data = response.json()

    items = data.get("jobs", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("Unexpected AJO response shape: expected a job list")

    jobs: List[Job] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id") or item.get("job_id") or ""
        jobs.append(
            Job(
                job_id=f"ajo:{raw_id}",
                source="AJO",
                title=item.get("title", ""),
                position_level=item.get("position_type", "Postdoc"),
                institution=item.get("institution", ""),
                country=item.get("country", ""),
                city=item.get("city", ""),
                discipline=item.get("discipline", ""),
                deadline=item.get("deadline"),
                posted_date=item.get("posted_date", date.today().isoformat()),
                url=item.get("url", ""),
                description_full=item.get("description_full", item.get("description", "")),
                requirements_extracted=item.get("requirements_extracted", []),
                funding_duration=item.get("funding_duration"),
            )
        )
    return jobs


def deduplicate(jobs: List[Job]) -> List[Job]:
    seen = set()
    unique: List[Job] = []
    for job in jobs:
        key = (job.source, job.job_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique
'''
,
    "cv_parser.py": r'''
"""Academic CV text extraction and ModelScope LLM structured parsing."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import pdfplumber
from docx import Document

from schema import AcademicProfile, validate_profile


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        texts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
        return "\n".join(texts)

    if suffix in {".docx", ".doc"}:
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)

    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(f"Unsupported resume file type: {suffix}")


def call_modelscope_api(prompt: str, resume_text: str) -> dict:
    """Call ModelScope Qwen API. CONFIGURE base URL and API key before live use."""
    base = os.environ.get("MODELSCOPE_API_BASE")
    api_key = os.environ.get("MODELSCOPE_API_KEY")
    if not base or not api_key:
        raise RuntimeError("ModelScope API is not configured")

    import requests

    payload = {
        "model": "Qwen/Qwen-...",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": resume_text},
        ],
        "response_format": {"type": "json_object"},
    }
    response = requests.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def fallback_parse(text: str, error: Exception) -> AcademicProfile:
    """Rule-based fallback when ModelScope parsing fails."""
    years = re.findall(r"\b(19|20)\d{2}\b", text)
    areas = []
    for keyword in ["LLM", "reasoning", "transcriptomics", "power systems", "NLP", "computer vision"]:
        if keyword.lower() in text.lower():
            areas.append(keyword)
    return AcademicProfile(
        degrees=[],
        expected_graduation=years[-1] if years else None,
        research_areas=areas[:8] or ["general"],
        parsing_note=f"ModelScope parsing failed ({error}); rule-based fallback used. Please review and correct.",
    )


def parse_academic_cv(file_path: str) -> AcademicProfile:
    text = extract_text(file_path)

    prompt = (
        "Extract structured academic profile JSON only. Fields: degrees, expected_graduation, "
        "research_areas (3-8 standardized tags), publication_count, first_or_corresponding_count, "
        "top_venues, skills, languages, position_level_range. No extra text."
    )

    try:
        data = call_modelscope_api(prompt, text)
        validate_profile(data)
        return AcademicProfile(**data)
    except Exception as exc:  # noqa: BLE001 - fallback is intentional
        return fallback_parse(text, exc)
'''
,
    "matcher.py": r'''
"""Hard filtering and explainable soft scoring for academic jobs."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Optional

from schema import AcademicProfile, Job, job_to_dict


def load_jobs(jobs_path: str | Path = "data/jobs.json") -> List[Job]:
    path = Path(jobs_path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return [Job(**item) for item in data]


def save_jobs(jobs: List[Job], jobs_path: str | Path = "data/jobs.json") -> None:
    path = Path(jobs_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump([job_to_dict(j) for j in jobs], fh, ensure_ascii=False, indent=2)


def _deadline_expired(deadline: Optional[str]) -> bool:
    if not deadline:
        return False
    try:
        return datetime.strptime(deadline, "%Y-%m-%d").date() < date.today()
    except ValueError:
        return False


def hard_filter(
    jobs: List[Job],
    profile: AcademicProfile,
    filters: Optional[dict] = None,
) -> List[Job]:
    filters = filters or {}
    levels = set(filters.get("position_levels") or profile.position_level_range or [])
    countries = set(filters.get("countries") or profile.accepted_countries or [])
    result: List[Job] = []

    for job in jobs:
        if levels and job.position_level not in levels:
            continue
        if countries and job.country and job.country not in countries:
            continue
        if _deadline_expired(job.deadline):
            continue
        result.append(job)
    return result


def _token_overlap(text_a: str, text_b: str) -> int:
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    return len(words_a & words_b)


def soft_score(job: Job, profile: AcademicProfile) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    haystack = " ".join(
        [job.title, job.description_full, " ".join(job.requirements_extracted)]
    )
    overlap = sum(
        _token_overlap(haystack, area) for area in profile.research_areas
    )
    if overlap:
        score += min(40, overlap * 8)
        reasons.append(f"研究方向与职位描述有 {overlap} 处术语重叠")

    if profile.publication_count:
        score += min(20, profile.publication_count * 4)
        reasons.append(f"您有 {profile.publication_count} 篇发表记录")
    if profile.first_or_corresponding_count:
        score += min(20, profile.first_or_corresponding_count * 6)
        reasons.append(f"其中 {profile.first_or_corresponding_count} 篇为一作/通讯")

    skill_overlap = _token_overlap(haystack, " ".join(profile.skills))
    if skill_overlap:
        score += min(20, skill_overlap * 5)
        reasons.append(f"技能匹配：{skill_overlap} 处")

    score = min(100, score)
    if not reasons:
        reasons.append("通过基础资格过滤，建议查看职位描述确认匹配度")
    return score, reasons


def search_academic_jobs(
    profile: AcademicProfile,
    filters: Optional[dict] = None,
    jobs_path: str | Path = "data/jobs.json",
) -> List[Job]:
    jobs = hard_filter(load_jobs(jobs_path), profile, filters)
    scored: List[tuple[int, Job]] = []
    for job in jobs:
        score, reasons = soft_score(job, profile)
        job.match_score = score
        job.match_reasons = reasons
        scored.append((score, job))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [job for _, job in scored]
'''
,
    "app.py": r'''
"""Gradio frontend for Phase 1 academic job matching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gradio as gr

from cv_parser import parse_academic_cv
from job_adapters.ajo import deduplicate, fetch_ajo_jobs
from matcher import save_jobs, search_academic_jobs

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_PATH = DATA_DIR / "jobs.json"


def refresh_jobs() -> str:
    try:
        raw_jobs = fetch_ajo_jobs()
        jobs = deduplicate(raw_jobs)
        save_jobs(jobs, JOBS_PATH)
        return f"已加载 {len(jobs)} 个 AcademicJobsOnline 职位到 {JOBS_PATH}"
    except Exception as exc:  # noqa: BLE001 - UI should stay responsive
        return f"AJO 加载失败：{exc}。可先使用已有缓存，或检查 AJO_API_URL 和网络。"


def parse_cv(file) -> tuple[str, str]:
    if file is None:
        return "请先上传简历文件", "{}"
    try:
        profile = parse_academic_cv(file.name)
        return "解析成功，请在下方确认或修正", json.dumps(
            {
                "research_areas": profile.research_areas,
                "publication_count": profile.publication_count,
                "first_or_corresponding_count": profile.first_or_corresponding_count,
                "skills": profile.skills,
                "languages": profile.languages,
                "position_level_range": profile.position_level_range,
                "accepted_countries": profile.accepted_countries,
                "parsing_note": profile.parsing_note,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:  # noqa: BLE001 - return error to UI
        return f"解析失败：{exc}", "{}"


def search_jobs(profile_json: str, levels: str, countries: str, discipline: str) -> str:
    try:
        profile_data = json.loads(profile_json or "{}")
    except json.JSONDecodeError:
        return "简历画像 JSON 格式不正确，请先修正。"

    from schema import AcademicProfile

    profile = AcademicProfile(**profile_data)
    filters: dict[str, Any] = {}
    if levels:
        filters["position_levels"] = [v.strip() for v in levels.split(",") if v.strip()]
    if countries:
        filters["countries"] = [v.strip() for v in countries.split(",") if v.strip()]
    if discipline:
        filters["discipline"] = discipline

    jobs = search_academic_jobs(profile, filters, JOBS_PATH)
    if not jobs:
        return "没有匹配的职位。请放宽筛选条件或先刷新职位数据。"

    lines = ["| 职位 | 机构 | 地点 | 级别 | 分数 | 匹配理由 | 截止日期 |", "|---|---|---|---|---|---|---|"]
    for job in jobs[:20]:
        lines.append(
            f"| {job.title} | {job.institution} | {job.city or ''} | {job.position_level} | "
            f"{job.match_score} | {'; '.join(job.match_reasons or [])} | {job.deadline or '—'} |"
        )
    return "\n".join(lines)


with gr.Blocks(title="全球学术求职聚合与匹配平台 - Phase 1") as demo:
    gr.Markdown("# 全球学术求职聚合与匹配平台（Phase 1：AcademicJobsOnline）")

    with gr.Row():
        cv_file = gr.File(label="上传简历 PDF/DOCX/TXT")
        parse_btn = gr.Button("解析简历")
        refresh_btn = gr.Button("刷新 AJO 职位")

    status = gr.Textbox(label="状态", interactive=False)
    profile_box = gr.Code(label="简历画像（可手动修正 JSON）", language="json")

    with gr.Row():
        level_filter = gr.Textbox(label="职位级别，逗号分隔", placeholder="Postdoc,AssistantProf")
        country_filter = gr.Textbox(label="国家/地区 ISO 代码，逗号分隔", placeholder="US,GB,CN")
        discipline_filter = gr.Textbox(label="学科关键词", placeholder="NLP")

    search_btn = gr.Button("搜索匹配职位")
    result = gr.Markdown()

    parse_btn.click(parse_cv, inputs=cv_file, outputs=[status, profile_box])
    refresh_btn.click(refresh_jobs, inputs=None, outputs=status)
    search_btn.click(
        search_jobs,
        inputs=[profile_box, level_filter, country_filter, discipline_filter],
        outputs=result,
    )

if __name__ == "__main__":
    demo.launch()
'''
,
    "requirements.txt": r"""modelscope
gradio
pdfplumber
python-docx
requests
""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Phase 1 scaffold files into a project directory.")
    parser.add_argument("--out", required=True, help="Target project directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold files")
    args = parser.parse_args()

    target = Path(args.out).resolve()
    target.mkdir(parents=True, exist_ok=True)

    written = 0
    for rel_name, content in FILES.items():
        dest = target / rel_name
        if dest.exists() and not args.force:
            print(f"[skip] {dest} (use --force to overwrite)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content.strip() + "\n", encoding="utf-8")
        written += 1
        print(f"[write] {dest}")

    print(f"Done: {written} files written to {target}")


if __name__ == "__main__":
    main()
