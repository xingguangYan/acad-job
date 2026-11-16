---
name: acad-job
description: Guide building a ModelScope Studio academic job aggregation and matching platform, packaged as an Agent-callable skill with parse_academic_cv and search_academic_jobs.
---

# Academic Job Match

## Purpose
Build and run the PRD platform: a ModelScope Studio Gradio/Streamlit app that aggregates global academic jobs, parses academic CVs, matches jobs with explainable scores, and packages the core capability as an Agent skill exposing `parse_academic_cv` and `search_academic_jobs`.

## When to use
Use when the user wants the academic job matcher from the pasted PRD, starting with AcademicJobsOnline in Phase 1, then adding EURAXESS, Academic Positions, and FacultyVacancies one adapter at a time.

## When not to use
Do not use for non-academic job boards, cover-letter or resume writing, resume fabrication, crawling without robots.txt/crawl-delay compliance, hardcoding secrets, or claiming complete global coverage.

## Core capabilities
`parse_academic_cv(file_path)` parses PDF/DOCX through ModelScope Qwen, validates the profile schema, falls back to rule extraction on failure, and returns a structured academic profile without altering user content.
`search_academic_jobs(profile, filters)` applies hard filters (position level, country, deadline), then soft ranking (embedding/semantic relevance plus publications and skills), and returns jobs with `match_score` 0-100 and explainable `match_reasons`.

## Phases
1. Phase 1: scaffold the project, implement only the AcademicJobsOnline adapter, complete local “upload CV → parse → match → display,” and verify `python app.py`.
2. Phase 2: deploy to ModelScope Studio as Gradio/Streamlit; put secrets in Studio Secrets, persist data under `/mnt/workspace/data`.
3. Phase 3: add EURAXESS, Academic Positions, then FacultyVacancies adapters, one at a time.
4. Phase 4: package `SKILL.md`, expose the two Agent functions, and test Agent invocation.
Stop after each phase and confirm before adding another data source.

## Scaffolding
Run `python scripts/scaffold_phase1.py --out <project-dir> --force`. It writes `app.py`, `cv_parser.py`, `job_adapters/ajo.py`, `matcher.py`, `schema.py`, and `requirements.txt`. Configure the API endpoints marked `CONFIGURE` before live use.

## Unified schema (summary)
Job: `job_id`, `source`, `title`, `position_level`, `institution`, `country` ISO 3166-1 alpha-2, `city`, `discipline`, `deadline`, `posted_date`, `url`, `description_full`, `requirements_extracted`, `funding_duration`, plus runtime `match_score` and `match_reasons`.
Profile: degrees, expected graduation, 3-8 research areas, publication counts and top venues, skills, languages, inferred applicable `position_level` range, accepted countries, and `parsing_note` when fallback extraction was used.

## Constraints
One adapter per source; map every source to the unified schema; deduplicate by `source + job_id` or `institution + title + deadline`. Run hard filters before soft ranking. AJO requires 5 seconds/page crawl delay and robots.txt compliance. Never write Apify tokens or model API keys into code; use environment variables or Studio Secrets. Local development uses `data/`; Studio uses `/mnt/workspace/data`. Do not write cover letters; only hint at missing requirements. Label data sources and coverage limits honestly.

## Validation
Run the scaffold into a temporary directory, then `python app.py`, upload a sample academic CV, and confirm parsing and job listing work. After editing this skill itself, run the skill-creator validator (`C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py`) against this folder.

For data-source details, ModelScope deployment rules, and compliance wording, read [references/architecture.md](references/architecture.md) before Phase 2 or adding an adapter.



