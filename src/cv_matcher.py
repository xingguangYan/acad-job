from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any


COMMON_SKILLS = [
    "Python", "PyTorch", "TensorFlow", "JAX", "C++", "MATLAB", "R", "SQL", "Linux",
    "Docker", "Git", "LLM", "NLP", "Computer Vision", "Reinforcement Learning",
    "RAG", "Agent", "Machine Learning", "Deep Learning", "Transformer",
    "DFT", "VASP", "Gaussian", "LAMMPS", "COMSOL", "ANSYS", "Molecular Dynamics",
    "Perovskite", "Solar Cell", "Battery", "Catalysis", "Electrochemistry",
    "XRD", "SEM", "TEM", "XPS", "NMR", "HPLC", "PCR", "CRISPR", "RNA-seq",
    "Single-cell", "Bioinformatics", "Proteomics", "ROS", "FPGA", "Verilog",
]


def _clean_extracted_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_cv_file(uploaded_file: Any) -> str:
    """支持 .pdf / .docx / .txt / .md 的轻量级简历文本提取。"""
    name = (uploaded_file.name or "").lower()
    raw_bytes = uploaded_file.getvalue()

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("缺少 pypdf 依赖，请确认 requirements.txt 中包含 pypdf>=4.0.0 并重启空间。") from exc

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages_text: list[str] = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
                if not txt.strip():
                    txt = page.extract_text(extraction_mode="layout") or ""
                pages_text.append(txt)
            except Exception:
                continue

        text = _clean_extracted_text("\n".join(pages_text))
        if len(text) < 20:
            raise ValueError(
                "从该 PDF 提取出的有效文字过少（可能是纯图片扫描版 PDF，建议导出为可选中文字的 PDF、DOCX 或直接粘贴文本）。"
            )
        return text

    if name.endswith(".docx"):
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            xml_targets = [
                n for n in zf.namelist()
                if n == "word/document.xml" or n.startswith("word/header") or n.startswith("word/footer")
            ]
            if "word/document.xml" not in xml_targets:
                raise ValueError("无效的 DOCX 文件结构。")

            paragraphs: list[str] = []
            for target in sorted(xml_targets):
                root = ET.fromstring(zf.read(target))
                for p_el in root.iter():
                    if p_el.tag.endswith("}p"):
                        runs = [t.text for t in p_el.iter() if t.tag.endswith("}t") and t.text]
                        line = "".join(runs).strip()
                        if line:
                            paragraphs.append(line)
        text = _clean_extracted_text("\n".join(paragraphs))
        if len(text) < 20:
            raise ValueError("未能从该 DOCX 提取到足够简历文本，请检查文件内容或直接粘贴文本。")
        return text

    # .txt / .md 等纯文本
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1"):
        try:
            text = _clean_extracted_text(raw_bytes.decode(enc))
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码，请使用 UTF-8 编码的 TXT/MD 或 PDF/DOCX 文件。")


def heuristic_parse_cv(cv_text: str, llm_fallback_note: str = "") -> dict[str, Any]:
    """当大模型未返回严格 JSON 时的本地结构化兜底解析器。"""
    lower = cv_text.lower()

    stage = "Researcher"
    if any(k in lower for k in ("assistant professor", "associate professor", "faculty", "副教授", "教授", "讲师")):
        stage = "Early-Career Faculty"
    elif any(k in lower for k in ("postdoc", "post-doc", "postdoctoral", "博士后")):
        stage = "Postdoc"
    elif any(k in lower for k in ("ph.d", "phd", "doctor of philosophy", "doctoral", "在读博士", "博士研究生")):
        stage = "PhD Candidate / Recent PhD"
    elif any(k in lower for k in ("engineer", "scientist", "r&d", "研发", "算法工程师")):
        stage = "R&D Scientist / Engineer"

    skills_found = [s for s in COMMON_SKILLS if re.search(rf"\b{re.escape(s.lower())}\b", lower)]
    if not skills_found:
        skills_found = [s for s in COMMON_SKILLS if s.lower() in lower][:8]

    # 提取英文高频学术关键词作为检索词
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9\-]{3,20}\b", cv_text)
    stop = {
        "university", "college", "school", "department", "institute", "research", "china",
        "beijing", "shanghai", "hong", "kong", "email", "phone", "education", "experience",
        "publications", "paper", "papers", "journal", "conference", "awards", "skills",
        "with", "from", "that", "this", "have", "using", "based", "study", "analysis",
    }
    freq: dict[str, int] = {}
    for w in words:
        wl = w.lower()
        if wl not in stop:
            freq[w] = freq.get(w, 0) + 1
    top_terms = [k for k, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]]

    highlights = llm_fallback_note.strip()[:220] if llm_fallback_note.strip() else _clean_extracted_text(cv_text)[:180]
    return {
        "career_stage": stage,
        "years_after_phd": "见简历原文",
        "research_areas": top_terms[:3] or ["Academic Research"],
        "skills": skills_found[:8] or top_terms[:4],
        "highlights": highlights,
        "target_roles": [stage, "Postdoc / Research Scientist"],
        "search_keywords": " ".join((skills_found[:2] + top_terms[:3])[:5]),
        "parse_mode": "AI + 本地结构化兜底" if llm_fallback_note else "本地规则解析",
    }


def fallback_rank_jobs_by_keywords(
    profile_text: str, jobs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """无大模型或接口异常时的离线规则匹配排序（0-100 分）。"""
    terms = [
        w.strip().lower()
        for w in re.split(r"[,，;；\s/]+", profile_text or "")
        if len(w.strip()) >= 2
    ]
    terms = list(dict.fromkeys(terms))[:20]

    ranked: list[dict[str, Any]] = []
    for job in jobs:
        job_copy = dict(job)
        if not terms:
            job_copy["ai_match_score"] = 50
            job_copy["ai_match_reason"] = "未提取到足够关键词，按默认顺序展示。"
            ranked.append(job_copy)
            continue

        haystack = " ".join(
            [
                job.get("title", ""),
                job.get("tags", ""),
                job.get("category", ""),
                job.get("description", ""),
            ]
        ).lower()
        hits = [t for t in terms if t in haystack]
        score = min(95, int(25 + (len(hits) / max(min(len(terms), 6), 1)) * 70)) if hits else 15
        job_copy["ai_match_score"] = score
        job_copy["ai_match_reason"] = (
            f"规则命中关键词：{'、'.join(hits[:6])}" if hits else "暂未命中直接关键词，建议人工查看详情"
        )
        ranked.append(job_copy)

    ranked.sort(key=lambda x: x.get("ai_match_score", 0), reverse=True)
    return ranked