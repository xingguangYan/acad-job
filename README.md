# acad-job

**AI 驱动全球学术求职聚合与匹配平台 — Codex Skill**

本 Skill 将学术职位聚合、简历解析、职位匹配能力封装为可被 Claude Code、Cursor 等 Agent 调用的 Skill，核心暴露两个工具函数：

- `parse_academic_cv(file_path)` → 返回结构化学术画像（PDF/DOCX/TXT 简历 → 学位、研究方向、发表记录、技能、语言、适用职位级别等）
- `search_academic_jobs(profile, filters)` → 返回经过硬过滤 + 软排序的学术职位列表（匹配分数 0–100 + 可解释匹配理由）

## 适用场景
- 面向全球学术求职者：本科生 RA、硕士/博士、博士后、助理教授、副教授、教授、Research Fellow / Scientist / PI
- 职位覆盖：AcademicJobsOnline（Phase 1 主源）、EURAXESS、Academic Positions、FacultyVacancies、国内理聘等（逐阶段接入）
- 核心价值：双层评分（硬过滤 position_level/country/deadline + 软排序语义相似度与发表匹配）、可解释匹配理由、不代写求职信、不伪造简历内容

## 不做什么
- ❌ 不代写求职信、简历或申请材料
- ❌ 不伪造或修改用户简历内容（只提示缺失项，由用户自行修正）
- ❌ 不绕过目标站点 robots.txt / crawl-delay
- ❌ 不在代码中硬编码 Apify Token、ModelScope API Key 等敏感信息
- ❌ 不宣称“全球最全” —— 非英语国家本土语言职位可能覆盖不足，界面会标注数据来源与覆盖说明

## 快速开始

### 前提条件
- Python 3.9+
- ModelScope 账号及 API Key（用于 Qwen 简历解析与嵌入式模型）
- （可选）Apify Token（用于 EURAXESS、Academic Positions 等源，Phase 1 无需）

### 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 包含：`modelscope`、`gradio`、`pdfplumber`、`python-docx`、`requests`

### 本地运行（Phase 1：AcademicJobsOnline）

```bash
# 配置环境变量（建议放在 .env 中，不要提交到 Git）
export MODELSCOPE_API_BASE="https://api-inference.modelscope.cn/v1"
export MODELSCOPE_API_KEY="your-modelscope-api-key"
export AJO_API_URL="https://api.academicjobsonline.org/v1/jobs"   # 需核实实际 AJO 公开 JSON API 地址

# 启动 Gradio 界面
python app.py
```

打开浏览器访问 `http://127.0.0.1:7860`，上传简历 → 解析 → 刷新 AJO 职位 → 设置筛选条件 → 搜索匹配职位。

## 项目结构

```text
acad-job/
├── SKILL.md                    # Skill 说明（调用边界、能力边界、不适用场景）
├── README.md                   # 本文件
├── agents/openai.yaml          # Codex 自动发现与 UI 元数据
├── job_adapters/
│   └── __init__.py             # 职位适配器包标记
├── references/
│   └── architecture.md         # 数据源、统一 Schema、部署与合规细节（按需阅读）
├── scripts/
│   └── scaffold_phase1.py      # 一键生成 Phase 1 项目文件（app.py、cv_parser.py、ajo.py 等）
└── requirements.txt            # Python 依赖清单
```

`scripts/scaffold_phase1.py --out <项目目录> --force` 可一次性生成：
- `schema.py`：统一职位 Schema 与简历画像 Schema（Python dataclass）
- `job_adapters/ajo.py`：AcademicJobsOnline 适配器（含 5 秒/页 crawl-delay）
- `cv_parser.py`：PDF/DOCX 文本抽取 + ModelScope Qwen 结构化解析（失败降级为规则抽取）
- `matcher.py`：硬过滤 + 软排序 + 可解释 match_reasons
- `app.py`：Gradio 前端界面
- `requirements.txt`

## 数据源与 Schema

### 职位统一 Schema（Job）

| 字段 | 类型 | 说明 |
|------|------|------|
| job_id | str | 唯一 ID，前缀标注来源（如 `ajo:12345`） |
| source | str | `AJO` / `EURAXESS` / `AcademicPositions` / `FacultyVacancies` ... |
| title | str | 职位名称 |
| position_level | str | `RA` / `Masters` / `PhD` / `Postdoc` / `AssistantProf` / `AssociateProf` / `FullProf` / `ResearchFellow` / `ResearchScientist` |
| institution | str | 机构名称 |
| country | str | ISO 3166-1 alpha-2 国家代码 |
| city | str | 城市 |
| discipline | str | 学科 |
| deadline | str\|null | `YYYY-MM-DD` 或 null |
| posted_date | str | 发布日期 |
| url | str | 原始申请链接 |
| description_full | str | 完整职位描述 |
| requirements_extracted | list[str] | 提取的要求列表 |
| funding_duration | str\|null | 资助期限 |
| match_score | int\|null | 运行时匹配分数 0–100 |
| match_reasons | list[str] | 运行时可解释匹配理由 |

### 简历画像 Schema（AcademicProfile）

| 字段 | 类型 | 说明 |
|------|------|------|
| degrees | list[str] | 已获/在读学位 |
| expected_graduation | str\|null | 预计毕业时间 |
| research_areas | list[str] | 3–8 个标准化研究方向标签 |
| publication_count | int | 发表数量 |
| first_or_corresponding_count | int | 一作/通讯数量 |
| top_venues | list[str] | 顶会/顶刊列表 |
| skills | list[str] | 编程语言、实验技术、软件工具 |
| languages | list[str] | 语言能力 |
| position_level_range | list[str] | 推断适用职位级别范围 |
| accepted_countries | list[str] | 接受的国家/地区 |
| parsing_note | str\|null | 降级解析时的提示 |

## 匹配流程

1. **硬过滤层**：`position_level` 是否在用户可申请范围；`country` 是否在接受列表；`deadline` 是否已过期。
2. **软排序层**：研究方向语义相似度 + 发表记录/顶刊匹配度 + 技能重叠 + 机构声誉加权。
3. **输出**：每个职位给出 `match_score`（0–100）和可解释 `match_reasons`。

## ModelScope Studio 部署

1. 新建 Gradio/Streamlit 类型空间（推荐 Gradio，开发最快）。
2. 将代码推送到 Studio，配置 Secrets（`MODELSCOPE_API_KEY`、`AJO_API_URL` 等，不要写入代码）。
3. 持久化目录：`/mnt/workspace/data`（简历、职位缓存、追踪列表）。
4. `requirements.txt` 中包含 `modelscope`、`gradio`、`pdfplumber`、`requests`。
5. 部署前本地运行 `python app.py` 并上传测试简历验证解析与匹配流程。

## 合规说明
- 职位数据来自第三方公开来源，平台不保证信息的实时性与完整性，申请前请以原始链接为准。
- 所有爬虫遵守目标站点 `robots.txt` 与 `crawl-delay`（AJO 要求 5 秒/页）。
- 敏感信息通过 Studio Secrets 或环境变量配置，禁止写入代码仓库。

## Skill 调用

Agent 可通过自然语言触发：
- `parse_academic_cv("path/to/resume.pdf")`
- `search_academic_jobs(profile={"research_areas": ["NLP", ...], ...}, filters={"position_levels": ["Postdoc"]})`

## 版本历史

- v1.0：Phase 1 基础版，AcademicJobsOnline 适配器 + Gradio 前端 + 本地运行验证

## 许可

MIT License
