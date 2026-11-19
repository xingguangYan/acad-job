---
name: acad-job
description: Build and run the acad-job Streamlit app that aggregates academic papers, industrial signals, jobs with CV matching, and early-career grants in one dashboard.
---

# acad-job

## Purpose
Build, run, and extend the Streamlit application `app.py`: academic paper search (OpenAlex / Semantic Scholar / arXiv), industrialization signals (arXiv 90-day trend, PatentsView, TRL), academic job aggregation with CV-based matching, and early-career grant tracking.

## When to use
Use when the user wants to run or modify this aggregator dashboard, add a new data source or tab, adjust matching logic, or deploy the app to ModelScope Studio or Streamlit Cloud.

## When not to use
Do not use for non-academic job boards, writing or rewriting cover letters, altering user resume content, bypassing robots.txt / crawl-delay, or hardcoding API keys and tokens.

## Entry points
- Run: `streamlit run app.py`
- Configuration: left sidebar (session-only keys) or environment variables listed in README
- Data paths default to `data/academic_jobs.csv`, `data/research_grants.csv.csv`, `data/commercial_potential.csv`

## Module map
- `app.py`: page config, caching (`st.cache_data` / `st.cache_resource`), tab orchestration
- `src/academic_api.py`: paper search and dedup across OpenAlex, Semantic Scholar, arXiv; daily preprint buckets
- `src/industrial_signals.py`: arXiv 90-day trend, PatentsView patents, commercial potential index, TRL via Apify
- `src/job_signals.py`: static jobs CSV, live RSS job feeds, filtering
- `src/grant_signals.py`: static grants, filtering, eligibility pre-check
- `src/cv_matcher.py`: resume text extraction and job matching (hard filter then soft rank)
- `src/llm_client.py`: OpenAI-compatible LLM presets; keys are session-only
- `src/ui_components.py` and `src/styles.py`: tabs, cards, KPIs, hero, footer

## Constraints
Deduplicate jobs by source plus job id. Run hard filters (position level, country, deadline) before soft ranking and always return explainable match reasons. Keep secrets in environment variables or session state only; never commit them. Respect each upstream site's robots.txt and crawl-delay.

## Extension pattern
Add a new data source as its own small module under `src/` (loader plus fetcher), wire it through a cache helper in `app.py`, and render it inside an existing tab or a new one. Do not build one universal crawler.

## Validation
Run `streamlit run app.py` locally and confirm the five tabs render, static CSVs load, and search plus CV upload behave. After editing this skill itself, run the skill-creator validator (`C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py`).
