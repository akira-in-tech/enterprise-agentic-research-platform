# Enterprise Agentic Research Platform — 完整项目章程

> 文档模式：Future-state / completion-state charter
> 假设：所有 phases 均已完成。它描述最终目标，不代表当前仓库已经实现这些功能。
> 产品概览见根目录 [README.md](../README.md)；逐项、可验证的当前实现状态见
> [status.md](status.md)。

## 1. 项目定位

Enterprise Agentic Research Platform 是一个面向企业团队的通用、多租户、证据驱动研究平台。

平台可以研究所有能够通过公开网页、企业私有文档、外部工具和人工输入获得证据的问题，包括但不限于：

- Software engineering
- Cloud infrastructure
- Market and competitive research
- Product and vendor comparison
- Academic and technical literature
- Policy and regulatory research
- Internal strategy and knowledge synthesis
- Operations and security analysis

平台内置一个 backend、Linux、HTTP、AWS、Docker、distributed systems 方向的 demo/evaluation profile（`demo_profiles/engineering/`），用于：

- Demo queries
- Evaluation dataset
- Private knowledge-base samples
- Report examples

这个 profile 不是产品边界，也不与任何具体公司或组织绑定。核心路由、规划、检索、证据评分和报告撰写代码（`app/agents/`、`app/services/`）是 domain-neutral 的，不依赖任何单一领域的关键词。

## 2. Core Platform 与内置 Demo Profile 的关系

| 层级 | 定位 |
| --- | --- |
| Core product | 通用企业研究平台，可处理任意研究主题 |
| Workflow | 根据问题复杂度选择 direct answer 或 deep research |
| Evidence pipeline | 与领域无关的检索、评分、冲突检测和引用验证 |
| Private RAG | 检索任意企业私有文档，不限于工程文档 |
| Report writer | 根据问题类型动态选择报告结构 |
| `demo_profiles/engineering/` | 使用工程、云、网络、Linux、数据库问题展示能力和评估路由/质量 |

Demo 数据隔离为独立配置：

```text
demo_profiles/
└── engineering/
    ├── queries.jsonl
    ├── evaluation_cases.jsonl
    ├── report_profile.yaml
    ├── kb_manifest.yaml
    └── demo_walkthrough.md
```

删除这个目录不会影响平台研究其他领域的问题：路由、规划、检索、证据和报告撰写代码从不 import `demo_profiles/`。其他领域的 profile（例如 `market_research/`、`policy_research/`）可以按同样的五文件结构添加。

## 3. 项目目标

### 产品目标

- 为简单问题提供快速、直接的回答。
- 为复杂问题执行多步骤、多来源研究。
- 合并公开网页与企业私有知识。
- 为重要结论提供可追踪的来源和引用。
- 识别来源冲突、证据不足和不确定性。
- 支持 Claude 和 Qwen 的 per-request 用户选择。
- 持久化 research runs、agent steps、sources、reports 和 checkpoints。
- 为长时间运行的研究提供实时进度、失败恢复和幂等控制。
- 提供可本地运行、可测试、可容器化和可部署的完整系统。

### 工程目标

- Provider-neutral interfaces
- Typed domain models
- Explicit transaction boundaries
- Tenant isolation
- Reproducible migrations
- Unit、integration 和 end-to-end tests
- CI/CD
- Structured logging and observability
- Documented architecture and trade-offs
- Real AWS deployment
- Real open-source contribution

## 4. 非目标

该平台不会被描述为：

- 可以自动判断绝对真相的系统
- 可以替代医生、律师、金融顾问或安全专家的系统
- 无需人工审核的高风险决策引擎
- 无限预算、无限 token、无限迭代的 autonomous agent
- 已达到多区域、高可用生产规模的系统
- 在没有证据时生成确定性结论的系统

对于医疗、法律、金融、安全等高风险问题，系统必须：

- 明确显示证据与不确定性
- 标记信息时效
- 请求 human review
- 避免给出未经限定的最终决策

高风险领域检测和 human-review 信号已在 Intent Router 和 Reflect 阶段实现（`app/agents/intent_router.py` 的 `detect_high_risk_domain`，`ReflectionDecision.human_review_required`）；MCP `request_human_review` 工具将其记录为可审计事件。

## 5. 目标用户

- Researchers
- Analysts
- Product managers
- Backend and platform engineers
- DevOps and SRE teams
- Security teams
- Technical product teams
- Enterprise knowledge workers
- Internal strategy teams

## 6. 核心工作流

```text
User question
        ↓
Input validation
        ↓
Tenant and provider resolution
        ↓
Intent Router (domain-neutral)
   ┌────┴───────────┐
   ↓                ↓
Direct Answer    Deep Research
   ↓                ↓
Stable answer      Planner
                    ↓
             Parallel retrieval
        ┌───────────┼────────────┐
        ↓           ↓            ↓
     Tavily      Milvus          MCP
   public web   private KB   external tools
        └───────────┼────────────┘
                    ↓
             Source normalization
                    ↓
        Deduplication and stable IDs
                    ↓
     Quality, relevance and freshness scoring
                    ↓
         Conflict and gap detection
                    ↓
              Analyst agents
                    ↓
          Reflection and supplementation
                    ↓
            Claim-to-source mapping
                    ↓
             Citation validation
                    ↓
              Report writer
                    ↓
       PostgreSQL persistence + SSE result
```

详见 [workflow.md](workflow.md)。

## 7. Routing 设计

Intent Router 是通用的，不依赖工程关键词决定产品能力。它基于以下信号判断：

- 问题是否需要最新信息
- 是否需要多个来源
- 是否包含比较、权衡或推荐
- 是否需要私有企业知识
- 是否存在高不确定性
- 是否属于高风险领域
- 是否需要工具调用
- 是否需要结构化报告

示例：

```text
What is a mutex?
→ direct

What are the current regulatory differences between
the EU and US for this product category?
→ deep_research

Compare HTTP/2 and HTTP/3 using current technical sources.
→ deep_research

Summarize our internal onboarding policy.
→ deep_research (private knowledge)
```

内置的 `demo_profiles/engineering/` 主要使用工程方向的例子，但 router 本身（`app/agents/intent_router.py`）保持 domain-neutral：LLM prompt 和规则回退关键词都不引用任何单一领域的技术词汇。

## 8. LLM Provider Strategy

```text
LLMClient
├── Claude through Anthropic
└── Qwen through Ollama
```

用户界面提供：

```text
Claude
Qwen
```

内部正规化：

```text
claude → anthropic
qwen   → ollama
```

选择结果按 research run 持久化，不能只依赖全局环境变量。

### Provider 分工

Claude：复杂规划、长上下文分析、复杂证据综合、严格 structured output、Reflection、Final report generation。

Qwen：本地和低成本开发、Intent routing、Structured planning、Summarization、Offline research workflows、Integration testing、Privacy-sensitive deployments。

系统不把业务逻辑绑定到任何单一 provider。

## 9. Retrieval Architecture

### Public retrieval

```text
Research tasks
→ bounded concurrency
→ circuit breaker (fails fast once Tavily is clearly failing)
→ AcademicAwareSearchClient: Tavily ‖ Semantic Scholar (concurrent, each leg fails open independently;
  Semantic Scholar carries its own circuit breaker so an unavailable academic provider adds no latency)
→ timeout and partial-failure isolation
→ URL normalization
→ deduplication (paper-typed result preferred when both providers return the same URL)
→ stable WEB-*/PAPER-* source IDs, with author/year/venue metadata for paper-typed sources
```

Semantic Scholar works unauthenticated by default (lower rate limit) or with an
optional `SEMANTIC_SCHOLAR_API_KEY` for a higher one.

### Private retrieval

```text
TXT / Markdown / PDF
→ parsing and validation
→ deterministic chunking
→ Qwen or Bedrock embeddings
→ Milvus
→ tenant-scoped semantic search
→ stable PRIVATE-* source IDs
```

平台允许私有 KB 包含任意领域文档。

### MCP tools

```text
search_web
search_private_documents
retrieve_source
ingest_document
save_research_report
get_research_history
request_human_review
```

MCP server（`app/mcp_server.py`, `app/services/mcp/tools.py`）与主 API 保持独立边界，方便其他 agents 或 clients 调用。每个能力独立降级：缺少某个凭据（Tavily key、embedding/vector store 配置）只会禁用对应工具，不会让整个 server 起不来。

## 10. Evidence Pipeline

每个来源经过：

```text
Validation
→ canonicalization
→ deduplication
→ quality scoring
→ relevance scoring
→ freshness assessment
→ conflict detection
→ claim mapping
→ citation verification
```

系统必须区分：

- 有直接证据支持的 claim
- 多个来源间存在冲突的 claim
- 仅有弱证据的 claim
- 尚未找到证据的 claim
- 模型推断而非来源直接陈述的内容

## 11. Analyst 与 Reflection

Analyst 层按 research plan 回答 sub-questions。

Reflection 判断：

- 是否覆盖全部 sub-questions
- 是否有足够的独立来源
- 是否存在互相矛盾的证据
- 是否有关键 claim 缺少 citation
- 是否需要补充搜索
- 是否已经达到预算或迭代上限
- **是否属于高风险领域**（如是，无论证据质量如何都标记 `human_review_required`）

所有循环必须有 `max_iterations` / `max_sources` / `max_time` / `max_tokens` / `max_cost` 边界。不允许无限 reflection。

## 12. Report Writer

报告结构不硬编码成工程报告。Planner（`app/agents/planner.py`）为每个请求动态生成 outline，并根据请求的实际领域选择合适的 section（工程、市场、政策等），而不是套用固定模板。

### 通用报告

```text
Executive Summary
Research Scope
Key Findings
Evidence
Conflicting Information
Uncertainties and Limitations
Recommendations
References
```

### Engineering demo profile（参考大纲，见 `demo_profiles/engineering/report_profile.yaml`）

```text
Executive Summary
Technical Background
Architecture
Trade-offs
Reliability
Performance
Security
Recommendations
References
```

### Market research profile（示例，未来 profile）

```text
Executive Summary
Market Definition
Competitive Landscape
Customer Segments
Key Trends
Risks
Opportunities
Recommendations
References
```

## 13. PostgreSQL 数据模型

详见 [data-model.md](data-model.md)。

## 14. 存储职责

```text
PostgreSQL → durable business data (runs, reports, sources, agent steps, checkpoints, audit)
Redis      → temporary cache, progress, rate limiting, idempotency, coordination locks
Milvus     → private document chunks, embeddings, tenant-scoped vector search
S3         → uploaded source documents, generated report exports
```

Redis 不作为 durable business-data database，Milvus 不保存用户和 billing 等关系数据。

## 15. API

详见根目录 README 的 "Research API" 一节和 [architecture.md](architecture.md)。

## 16. Vue Frontend

```text
Vue 3
TypeScript
Vite
Vue Router
Pinia
TanStack Vue Query
Vitest
Vue Test Utils
Playwright
```

Vue Router 驱动客户端路由与认证守卫（`router/index.ts`），Pinia 管理认证与主题 state（`stores/auth.ts`、`stores/workspace.ts`），TanStack Vue Query 管理研究数据的请求缓存（`views/ResearchRunView.vue`、`components/KnowledgeLibrary.vue`），Playwright 覆盖端到端流程（`frontend/e2e/`）。详见 [status.md](status.md) 的
Component Status 表。

Frontend 标题保持通用："Enterprise Research Platform"，placeholder 保持通用："Ask a research question..."。内置 demo profile 可以展示工程示例，但不限制用户输入其他领域的问题。

## 17. Reliability

- Per-provider timeout
- Exponential backoff with jitter
- Retry only for retryable failures
- Circuit-breaker boundaries where justified（已应用于 Tavily 搜索、Anthropic 客户端和 Milvus 向量存储）
- Partial search-result preservation
- Checkpoint and resume
- Idempotent research-run creation
- Atomic status transitions
- Structured logs with per-request correlation IDs
- Health and readiness endpoints
- Graceful shutdown
- External-service failure isolation
- Budget enforcement
- No long external LLM call inside a database transaction

## 18. Security

- Tenant-scoped database and vector queries
- Secrets stored outside source control
- AWS Secrets Manager in deployment
- Document media-type and size validation
- Filename and metadata sanitization
- Prompt-injection-aware private document handling
- SSRF protection for user-provided URLs
- Rate limiting
- Audit events
- CORS allowlist
- Least-privilege AWS IAM
- Private database networking
- Encryption in transit
- No raw credentials in logs
- Human review for high-risk research

## 19. Testing Strategy

见根目录 README 的 "Default Verification" 与 "Live Integration Tests" 章节，以及 CI 中的 `integration` job（PostgreSQL + Redis service containers）。

系统记录但不预先发明 evaluation metrics；只有亲自运行并保留 evaluation artifact 后，才能在 README 或简历中写具体数字。

## 20. Docker Compose

见根目录 README 的 "Local Docker Compose Stack" 章节。

## 21. GitHub Actions

```text
Backend quality    → Ruff, mypy, pytest (no live integrations)
Frontend quality    → ESLint/typecheck, Vitest, Vite build
Integration quality → PostgreSQL + Redis service containers, alembic upgrade, integration pytest
Terraform quality   → fmt, validate, terraform test
Container packaging → Compose config validation, image builds
```

## 22. AWS Deployment

见根目录 README 的 "AWS Staging Deployment" 章节和 `infra/terraform/`。

## 23. Architecture Documentation

```text
docs/
├── PROJECT_CHARTER.md   (this file)
├── architecture.md
├── workflow.md
├── data-model.md
├── deployment.md
├── reliability.md
├── security.md
├── evaluation.md
└── trade-offs.md
```

## 24. 关键 Trade-offs

见 [trade-offs.md](trade-offs.md)。

## 25. Open-Source Contribution

完成条件：

- 至少向一个真实开源仓库提交小型 PR
- PR 与本项目技术栈相关
- 提供公开链接
- 明确标记状态：open、merged 或 closed
- 不把"提交"描述成"merged"，除非确实合并

当前状态：**Closed**（被自动机器人关闭，非内容被拒）——
[langchain-ai/langgraph#8583](https://github.com/langchain-ai/langgraph/pull/8583)，
为 `libs/checkpoint-postgres/README.md` 补充一条说明：`psycopg`（`PostgresSaver`/
`AsyncPostgresSaver` 的底层驱动）的连接串使用 `sslmode` 参数，而不是
`asyncpg`（例如从已有的 SQLAlchemy async engine URL 复用而来）所用的 `ssl`
参数；错用会抛出不指名原因的 `psycopg.ProgrammingError`。该问题是本项目
接入 `AsyncPostgresSaver`（见 [checkpointing.py](../app/services/research/checkpointing.py)）
时真实遇到的。提交后被 `langchain-ai/langgraph` 的 `require-issue-link`
GitHub Action 自动关闭，原因是外部 PR 必须先关联一个经 maintainer 批准的
issue（`Fixes #`/`Closes #`/`Resolves #`）才会被接受；本 PR 提交时未满足
这一流程要求。未重新提交前不描述为 open，已在
[docs/status.md](status.md) 的 Development Log 中记录。

第二个 PR：**Open**（已提交，尚未合并）——
[HENNGE/terraform-aws-ecs#47](https://github.com/HENNGE/terraform-aws-ecs/pull/47)，
补齐 `modules/simple/fargate` 与 `modules/core/service` 两份 README，说明
`force_new_deployment = true` 单独设置并不会让每次 `terraform apply` 都触发
重新部署（Terraform 只在该属性值发生变化时才会产生 diff），必须搭配已存在的
`triggers`（配合 `plantimestamp()`）才能达到预期效果；对应 upstream 的
[issue #43](https://github.com/HENNGE/terraform-aws-ecs/issues/43)，PR 里
写了 `Closes #43`。这与本项目 `scripts/aws-deploy.sh` 和 restart verification
中真实验证过的 ECS 强制重新部署机制是同一领域。

第三个 PR：**Open / Ready for Review**（已提交，尚未合并）——
[kedro-org/kedro-plugins#1496](https://github.com/kedro-org/kedro-plugins/pull/1496)，
完成 upstream issues #1316 与 #1317 中 Redis dataset 的 `os.PathLike` 子任务。
`redis.PickleDataset` 的公开 `key` contract 现在接受 `str | os.PathLike`，并在
进入 redis-py 前通过 `os.fspath()` 规范化；回归测试覆盖 save、load、exists 和
describe 使用同一个规范化 key。PR commit 以 `akira <ye.ton@northeastern.edu>`
署名并包含 DCO `Signed-off-by`，GitHub DCO check 已通过；当前已退出 Draft，
等待 maintainer review。

第四个 PR：**Open Draft / CLA Pending**（已提交，尚未合并）——
[finos/FDC3#2091](https://github.com/finos/FDC3/pull/2091)，直接解决 upstream
[issue #1674](https://github.com/finos/FDC3/issues/1674)。FDC3 Workbench 在 2.2+
使用 `DesktopAgent.addEventListener` 与 `PrivateChannel.addEventListener` 监听
user-channel 和 private-channel 事件，同时为 FDC3 2.0/2.1 保留 legacy callback
路径；事件历史保留真实 `details.contextType`，UI 提供状态、历史和可复制示例。
新增 7 个 Vitest 用例，并通过 Workbench build/lint 及 monorepo test/lint。
EasyCLA 当前要求贡献者本人完成授权，授权和 maintainer review 完成前不描述为
ready 或 merged。

Merged 之前不描述为 merged。

## 26. Engineering Demo Strategy

内置的 `demo_profiles/engineering/` 展示：

```text
Python / FastAPI
Vue 3 / TypeScript / Vite
PostgreSQL
Redis
Docker
AWS
CI/CD
Testing
Linux and networking knowledge
Distributed-systems reasoning
Open-source participation
```

Demo query 示例：

```text
Compare HTTP/2 and HTTP/3 using current technical sources.
```

演示路径：

```text
Select Qwen or Claude
→ route to deep research
→ create structured plan
→ search public technical sources
→ retrieve private knowledge documents
→ detect conflicting evidence
→ generate engineering report
→ validate citations
→ persist run
→ stream progress to Vue
```

这只是一个有针对性的 showcase。用户依然可以研究市场、产品、政策、学术或其他主题；切换到其他 `demo_profiles/` 即可展示同一条 pipeline 处理别的领域。

## 27. 完整 Phases

```text
Phase 0   Architecture and scope
Phase 1   Local environment
Phase 2   FastAPI foundation
Phase 3   Claude foundation
Phase 4   LangGraph, routing and provider abstraction
Phase 5   Direct answer and planner
Phase 6   Tavily public retrieval
Phase 7   Milvus private RAG
Phase 8   PostgreSQL persistence
Phase 9   Redis coordination
Phase 10  MCP server and client
Phase 11  Evidence pipeline
Phase 12  Analyst and reflection
Phase 13  Domain-adaptive report writer
Phase 14  REST API, SSE, and AWS staging foundation
Phase 15  Reliability and recovery
Phase 16  Testing and evaluation
Phase 17  Docker Compose
Phase 18  GitHub Actions
Phase 19  Vue frontend
Phase 20  AWS deployment
Phase 21  Architecture and trade-off documentation
Phase 22  Open-source contribution
Phase 23  Resume and demo preparation
```

## 28. Definition of Done

只有满足以下条件，项目才可以被描述为完成：

- 所有默认 tests 通过
- Live integration tests 有可复现记录
- Alembic migration 可 upgrade 和 downgrade
- Tenant isolation 在 PostgreSQL 与 Milvus 中验证
- Claude/Qwen per-request selection 可用
- Reports 包含经过验证的 citations
- Docker Compose 可从干净环境启动
- GitHub Actions 在真实 commit 上通过
- Vue frontend 完成主要用户流程
- AWS URL 可访问并完成 restart verification
- Architecture 和 trade-offs 文档完成
- 至少一个真实开源 PR 已提交
- Evaluation metrics 来自真实运行
- README 只描述实际验证的功能

## 29. 简历定位

项目完成后可以定位为：

> Built a multi-tenant, evidence-driven enterprise research platform that orchestrates Claude and Qwen through LangGraph, combines public-web and private-document retrieval, validates claim-level citations, persists resumable workflows with PostgreSQL and Redis, and delivers real-time reports through a Vue/TypeScript interface deployed on AWS.

但只有当对应功能、测试和部署均真实完成后，才能使用这段描述。
