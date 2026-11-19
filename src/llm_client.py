from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from src.cv_matcher import fallback_rank_jobs_by_keywords, heuristic_parse_cv


def get_llm_settings(session_state: dict[str, Any] | None = None) -> dict[str, str]:
    ss = session_state or {}
    api_key = (
        ss.get("ui_llm_api_key", "").strip()
        or os.environ.get("LLM_API_KEY", "").strip()
        or os.environ.get("MODELSCOPE_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    base_url = (
        ss.get("ui_llm_base_url", "").strip()
        or os.environ.get("LLM_BASE_URL", "").strip()
        or "https://api-inference.modelscope.cn/v1"
    ).rstrip("/")
    model = (
        ss.get("ui_llm_model", "").strip()
        or os.environ.get("LLM_MODEL_ID", "").strip()
        or "Qwen/Qwen2.5-72B-Instruct"
    )
    return {"api_key": api_key, "base_url": base_url, "model": model}


def call_llm(
    system_prompt: str,
    user_prompt: str,
    llm_cfg: dict[str, str],
    max_tokens: int = 800,
    temperature: float = 0.25,
) -> str:
    if not llm_cfg.get("api_key"):
        raise RuntimeError("尚未配置大模型 API Key")
    if not llm_cfg.get("base_url") or not llm_cfg.get("model"):
        raise RuntimeError("请填写完整的 Base URL 与 Model 名称")

    endpoint = f"{llm_cfg['base_url']}/chat/completions"
    resp = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {llm_cfg['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": llm_cfg["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def test_llm_connection(llm_cfg: dict[str, str]) -> tuple[bool, str]:
    try:
        reply = call_llm(
            "You are a concise assistant.",
            "Reply with only: OK",
            llm_cfg,
            max_tokens=32,
            temperature=0.0,
        )
        return True, f"连接成功！模型返回：{reply[:40]}"
    except Exception as exc:
        return False, f"连接失败：{exc}"


def _strip_reasoning_tags(raw: str) -> str:
    """移除推理模型可能输出的 <think>...</think> 过程，并剥离 markdown 代码围栏。"""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return cleaned


def _repair_json_str(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s.strip()


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    cleaned = _strip_reasoning_tags(raw)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        snippet = _repair_json_str(cleaned[match.start():])
        try:
            obj, _ = decoder.raw_decode(snippet)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _extract_json_array(raw: str) -> list[Any] | None:
    cleaned = _strip_reasoning_tags(raw)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", cleaned):
        snippet = _repair_json_str(cleaned[match.start():])
        try:
            arr, _ = decoder.raw_decode(snippet)
            if isinstance(arr, list):
                return arr
        except Exception:
            continue
    return None


def llm_assess_trl(title: str, abstract: str, llm_cfg: dict[str, str]) -> dict[str, Any]:
    prompt = (
        "请根据以下论文标题和摘要，评估该技术目前处于 NASA TRL 1–9 的哪一个技术就绪度等级，"
        "并简要说明产业化瓶颈与商业潜力等级（A/B/C/D）。请严格只输出一个 JSON 对象：\n"
        '{"trl": 3, "commercial_grade": "B", "summary": "80字以内的中文评估依据与落地瓶颈"}\n\n'
        f"标题：{title}\n摘要：{abstract[:1500]}"
    )
    raw = call_llm(
        "你是资深科技成果转化与技术尽调专家，只输出标准 JSON 对象，不要输出其他文字。",
        prompt,
        llm_cfg,
        max_tokens=500,
    )
    trl_num = None
    grade = None
    summary = _strip_reasoning_tags(raw)[:300]
    parsed = _extract_json_object(raw)
    if isinstance(parsed, dict):
        if parsed.get("trl") is not None:
            try:
                trl_num = max(1, min(9, int(parsed["trl"])))
            except (TypeError, ValueError):
                trl_num = None
        grade = parsed.get("commercial_grade")
        summary = parsed.get("summary") or summary
    return {"trl": trl_num, "commercial_grade": grade, "summary": f"[AI 评估] {summary}", "source": "LLM"}


def llm_summarize_paper(title: str, abstract: str, llm_cfg: dict[str, str]) -> str:
    prompt = (
        "请用中文分 3 点精读这篇论文（每点不超过 40 字）：\n"
        "1. 核心创新点\n2. 关键技术路线/实验结论\n3. 潜在产业应用场景\n\n"
        f"标题：{title}\n摘要：{abstract[:1800]}"
    )
    raw = call_llm("你是面向科研人员与技术转移顾问的论文精读助手。", prompt, llm_cfg, max_tokens=500)
    return _strip_reasoning_tags(raw)


def llm_parse_cv(cv_text: str, llm_cfg: dict[str, str]) -> dict[str, Any]:
    """用大模型结构化解析 CV 简历；若模型输出非标准 JSON，则自动融合本地规则解析兜底，绝不失败。"""
    prompt = (
        "请解析以下科研/学术简历（CV），提炼结构化画像，严格只输出一个标准 JSON 对象（禁止任何前后缀解释或 Markdown 废话）：\n"
        "{\n"
        '  "career_stage": "PhD Candidate / Postdoc / Early-Career Faculty / R&D Engineer",\n'
        '  "years_after_phd": "未获博士学位 或 已毕业X年（未知写未知）",\n'
        '  "research_areas": ["方向1", "方向2", "方向3"],\n'
        '  "skills": ["技能1", "技能2", "技能3"],\n'
        '  "highlights": "80字以内的代表性论文或项目亮点总结",\n'
        '  "target_roles": ["推荐岗位类型1", "推荐方向2"],\n'
        '  "search_keywords": "3-5个英文学术检索关键词，用空格分隔"\n'
        "}\n\n"
        f"CV 内容：\n{cv_text[:5000]}"
    )
    raw = call_llm(
        "你是资深学术猎头与科研人才评估专家。必须严格只返回合法的 JSON 对象。",
        prompt,
        llm_cfg,
        max_tokens=1500,
    )
    parsed = _extract_json_object(raw)
    if isinstance(parsed, dict):
        parsed.setdefault("career_stage", "Researcher")
        parsed.setdefault("years_after_phd", "未知")
        parsed.setdefault("research_areas", [])
        parsed.setdefault("skills", [])
        parsed.setdefault("highlights", "")
        parsed.setdefault("target_roles", [])
        parsed.setdefault("search_keywords", "")
        parsed["parse_mode"] = "AI 深度解析"
        return parsed

    # 兜底：若模型未输出严格 JSON，保留模型总结 + 本地规则结构化字段
    return heuristic_parse_cv(cv_text, llm_fallback_note=_strip_reasoning_tags(raw))


def llm_batch_rank_jobs(
    cv_summary: str, jobs: list[dict[str, Any]], llm_cfg: dict[str, str]
) -> list[dict[str, Any]]:
    if not jobs:
        return []
    if not llm_cfg.get("api_key"):
        return fallback_rank_jobs_by_keywords(cv_summary, jobs)

    pre_ranked = fallback_rank_jobs_by_keywords(cv_summary, jobs)
    candidates = pre_ranked[:15]
    rest = pre_ranked[15:]

    brief_jobs = [
        {
            "idx": i,
            "title": j["title"],
            "institution": j["institution"],
            "category": j["category"],
            "tags": j.get("tags", ""),
            "desc": j.get("description", "")[:220],
        }
        for i, j in enumerate(candidates)
    ]

    prompt = (
        "请根据候选人 CV 画像，为以下岗位打匹配分（0-100）并给出一句简短中文理由（25字以内）。\n"
        '严格只返回 JSON 数组，格式：[{"idx": 0, "score": 88, "reason": "研究方向高度契合"}]\n\n'
        f"候选人画像：\n{cv_summary[:1200]}\n\n"
        f"候选岗位列表：\n{json.dumps(brief_jobs, ensure_ascii=False)}"
    )
    try:
        raw = call_llm(
            "你是精确的学术与研发岗位匹配专家，只返回标准 JSON 数组。",
            prompt,
            llm_cfg,
            max_tokens=1500,
        )
        scored_list = _extract_json_array(raw)
        if isinstance(scored_list, list):
            score_map = {
                int(item["idx"]): item
                for item in scored_list
                if isinstance(item, dict) and "idx" in item
            }
            for i, job in enumerate(candidates):
                if i in score_map:
                    job["ai_match_score"] = max(0, min(100, int(score_map[i].get("score", 50))))
                    job["ai_match_reason"] = f"[AI 匹配] {score_map[i].get('reason', '')}"
            candidates.sort(key=lambda x: x.get("ai_match_score", 0), reverse=True)
            return candidates + rest
    except Exception:
        pass
    return pre_ranked


def llm_analyze_job_fit(
    research_profile: str,
    job_title: str,
    institution: str,
    job_desc: str,
    llm_cfg: dict[str, str],
) -> tuple[bool, str]:
    if not llm_cfg.get("api_key"):
        terms = [w.strip().lower() for w in re.split(r"[,，\s/]+", research_profile or "") if len(w.strip()) >= 2]
        text_lower = f"{job_title} {institution} {job_desc}".lower()
        matched = [t for t in dict.fromkeys(terms) if t in text_lower]
        if not terms:
            return False, "未配置大模型。请在上方填写研究背景或先上传 CV 解析。"
        ratio = int(len(matched) / max(len(terms), 1) * 100)
        hit_str = "、".join(matched[:6]) if matched else "暂无直接词面重合"
        return False, f"【离线规则匹配】词面重合度：{ratio}% | 命中词：{hit_str}"

    prompt = (
        f"请评估申请人与以下科研/研发岗位的匹配度（150字以内，含匹配分 0-100、契合点与建议）：\n"
        f"- 申请人背景：{research_profile or '未填写'}\n"
        f"- 目标岗位：{job_title}（{institution}）\n"
        f"- 岗位描述：{job_desc[:1400]}"
    )
    try:
        return True, _strip_reasoning_tags(call_llm("你是专业的学术及研发求职顾问。", prompt, llm_cfg, max_tokens=500))
    except Exception as exc:
        return False, f"大模型调用失败（已自动降级）：{type(exc).__name__}"


def llm_generate_cover_letter(
    research_profile: str,
    job_title: str,
    institution: str,
    job_desc: str,
    llm_cfg: dict[str, str],
) -> str:
    if not llm_cfg.get("api_key"):
        return (
            "【套磁信模板（未配置大模型，可按需修改）】\n\n"
            f"Dear Hiring Committee / Professor at {institution},\n\n"
            f"I am writing to express my strong interest in the {job_title} position. "
            f"My research focuses on {research_profile or '[Your Research Area]'}, "
            "and my background aligns closely with your group's work.\n\n"
            "Best regards,\n[Your Name]"
        )
    prompt = (
        f"请撰写一封简洁专业的英文学术套磁/求职邮件（180词左右，突出与岗位的契合点）：\n"
        f"- 申请人背景：{research_profile or 'PhD/Postdoc researcher'}\n"
        f"- 申请岗位：{job_title} @ {institution}\n"
        f"- 岗位信息：{job_desc[:1000]}"
    )
    return _strip_reasoning_tags(call_llm("你是擅长撰写教职与博后套磁信的学术写作专家。", prompt, llm_cfg, max_tokens=650))


def llm_check_grant_eligibility(
    applicant_profile: str,
    grant: dict[str, Any],
    llm_cfg: dict[str, str],
) -> tuple[bool, str]:
    if not llm_cfg.get("api_key"):
        elig = grant.get("eligibility", "")
        stage = grant.get("stage", "")
        return (
            False,
            f"【离线资格提示（未配置大模型）】本项目主要面向：{stage}。核心要求：{elig}。如需结合你的 CV 做逐条资格精核，请在左侧栏填入大模型 API Key。",
        )

    prompt = (
        "请扮演 Fundlark 科研基金申报顾问，严格对比“申请人背景”与“基金资格要求”，"
        "给出：1) 资格判断（✅ 符合 / ⚠️ 需确认某条件 / ❌ 暂不符合）；2) 关键限制条件（如博士毕业年限/国籍/依托单位）；3) 1条申报建议（160字以内）。\n\n"
        f"申请人背景：{applicant_profile or '未填写具体简历，请给出通用重点核查项'}\n"
        f"基金名称：{grant['name']}（{grant['funder']}）\n"
        f"面向阶段：{grant['stage']} | 地区：{grant['region']}\n"
        f"官方资格要求：{grant['eligibility']}\n"
        f"项目说明：{grant.get('description', '')}"
    )
    try:
        return True, _strip_reasoning_tags(call_llm("你是严谨的全球科研基金与人才项目申报顾问。", prompt, llm_cfg, max_tokens=500))
    except Exception as exc:
        return False, f"AI 资格核验调用失败（已降级）：{type(exc).__name__}"