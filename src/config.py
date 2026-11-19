import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    openalex_api_key: str
    semantic_scholar_api_key: str
    apify_api_token: str
    apify_trl_actor_id: str
    patentsview_api_key: str
    compot_csv_path: str
    jobs_csv_path: str
    grants_csv_path: str
    request_timeout: int = 12


def load_config(session_state: dict | None = None) -> AppConfig:
    """Load runtime settings from env vars, allowing sidebar session overrides."""
    ss = session_state or {}
    return AppConfig(
        openalex_api_key=(
            ss.get("ui_openalex_key", "").strip()
            or os.environ.get("OPENALEX_API_KEY", "").strip()
        ),
        semantic_scholar_api_key=(
            ss.get("ui_s2_key", "").strip()
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        ),
        apify_api_token=(
            ss.get("ui_apify_token", "").strip()
            or os.environ.get("APIFY_API_TOKEN", "").strip()
        ),
        apify_trl_actor_id=os.environ.get(
            "APIFY_TRL_ACTOR_ID", "automate_lab~tech-scouting-report-mcp"
        ).strip(),
        patentsview_api_key=os.environ.get("PATENTSVIEW_API_KEY", "").strip(),
        compot_csv_path=os.environ.get(
            "COMPOT_CSV_PATH", "data/commercial_potential.csv"
        ).strip(),
        jobs_csv_path=os.environ.get(
            "JOBS_CSV_PATH", "data/academic_jobs.csv"
        ).strip(),
        grants_csv_path=os.environ.get(
            "GRANTS_CSV_PATH", "data/research_grants.csv"
        ).strip(),
    )


DOMAIN_OPTIONS = {
    "全部": {"openalex_concept": None, "s2_fields": None},
    "CS": {"openalex_concept": "C41008148", "s2_fields": "Computer Science"},
    "Bio": {"openalex_concept": "C86803240", "s2_fields": "Biology"},
    "Med": {"openalex_concept": "C71924100", "s2_fields": "Medicine"},
    "Physics": {"openalex_concept": "C121332964", "s2_fields": "Physics"},
}

HOT_TOPICS = [
    "perovskite solar cells",
    "LLM agents",
    "solid state battery",
    "CRISPR gene editing",
    "embodied AI robotics",
]

LLM_PRESETS = {
    "魔搭 ModelScope API-Inference (免费额度)": {
        "base_url": "https://api-inference.modelscope.cn/v1",
        "model": "Qwen/Qwen2.5-72B-Instruct",
    },
    "DeepSeek 官方": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "通义千问 DashScope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "自定义 OpenAI 兼容接口": {
        "base_url": "",
        "model": "",
    },
}

USER_AGENT = "ResearchFrontierStudio/1.2 (ModelScope-Streamlit)"