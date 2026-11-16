# Academic job matcher architecture reference

Read this when adding a new data source, deploying to ModelScope Studio, or writing user-facing compliance text.

## Data sources and adapters
Each source gets its own adapter under `job_adapters/`. An adapter fetches data, maps fields to the unified `Job` schema, and deduplicates. Never build one universal crawler.

| Source | Coverage | Access | Notes |
|---|---|---|---|
| AcademicJobsOnline (AJO) | Global; math, physics, statistics, economics, CS | Public JSON API, no auth | Phase 1 only. 5-second crawl delay. Verify the live endpoint before use. |
| EURAXESS | Europe and global | Apify adapter | Researcher profiles R1-R4 and funding programme. Token via Studio Secrets. |
| Academic Positions | Mainly Europe | Apify adapter | Includes full description, employer, location, deadline. |
| jobs.ac.uk | Mainly UK | Apify "10 Boards in One" adapter | Add in a later phase. |
| FacultyVacancies | Multi-country faculty roles | Crawler or RSS | Useful for non-English markets. |
| Chinese platforms (e.g. 理聘) | Chinese universities and institutes | Source-specific adapter | Requires its own field mapping and compliance review. |

Deduplication keys: `source + job_id`; fallback to `institution + title + deadline` hash.

## Unified job schema
```json
{
  "job_id": "string",
  "source": "AJO | EURAXESS | AcademicPositions | FacultyVacancies | ...",
  "title": "string",
  "position_level": "RA | Masters | PhD | Postdoc | AssistantProf | AssociateProf | FullProf | ResearchFellow | ResearchScientist",
  "institution": "string",
  "country": "ISO 3166-1 alpha-2",
  "city": "string",
  "discipline": "string",
  "deadline": "YYYY-MM-DD or null",
  "posted_date": "YYYY-MM-DD",
  "url": "string",
  "description_full": "string",
  "requirements_extracted": ["string"],
  "funding_duration": "string or null"
}
```

Runtime-only additions: `match_score` (0-100) and `match_reasons` (array of strings).

## Academic profile fields
Degrees earned and in progress; expected graduation; 3-8 normalized research-area tags; publication count; first/corresponding-author count; top venues; programming languages, experimental techniques, software tools; language proficiency; inferred applicable `position_level` range; accepted countries; and `parsing_note` when rule-based fallback was used.

## Matching order
1. Hard filter: applicable `position_level`, accepted countries, unexpired deadline.
2. Soft rank: research-direction embedding similarity, publication/venue fit, skill overlap, optional institution/discipline weighting.
3. Output: `match_score` plus reasons that cite concrete profile/job evidence.

Never let semantic similarity promote a level-incompatible job above the hard-filtered set.

## ModelScope Studio deployment
- Use a Gradio or Streamlit space; React/Vue static sites need a separate backend for CV parsing and matching.
- Persist uploaded CVs, the job cache, and tracking records under `/mnt/workspace/data`; local development uses `data/`.
- Store `MODELSCOPE_API_KEY`, Apify tokens, and model API keys in Studio Secrets or environment variables. Never hardcode them.
- `requirements.txt` must cover `modelscope`, the chosen UI framework, `pdfplumber`, and `requests`.
- Validate locally with `python app.py` and a test CV before deploying.
- Start with a JSON job cache; move to SQLite or object storage only when size or quota justifies it.

## Product rules
- The user confirms or edits the parsed profile before it affects matching.
- Deadline tracking may surface reminders at 7 days and 3 days before expiry.
- Requirements assistance only highlights gaps (for example, missing teaching experience); it never writes application letters.
- Non-English descriptions may be summarized in Chinese and English.
- Surface the source, collection date, and application link for every job.

## Compliance wording
Job data comes from third-party public sources. The platform cannot guarantee real-time accuracy or completeness. Verify on the original posting before applying. Do not claim to be the most complete source for every country; local-language and local-only postings may be missing.

## Crawling rules
Check each target's `robots.txt` and honor its crawl delay. AJO requires 5 seconds per page. Do not scrape behind logins or bypass access controls. Stop adding sources once the requested phase is complete.
