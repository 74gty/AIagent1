# CareerPilot 职涯导航员

CareerPilot 是一个面向求职场景的本地 AI Agent 项目。它可以根据用户输入的求职目标，自动拆解岗位方向、生成搜索关键词、跨招聘网站检索岗位，并对岗位 JD 做结构化分析，最终输出岗位列表、匹配评分、风险提示、简历优化建议、求职信、申请表回答和 STAR 面试故事。

这个项目的目标不是简单与AI模型聊天，而是把「岗位搜索 -> 岗位理解 -> 候选岗位筛选 -> 投递材料准备 -> 测试报告沉淀」串成一个可运行、可验证、可展示的完整产品闭环。

## 项目亮点

- **Agent 流程闭环**：支持需求理解、关键词规划、搜索执行、结果去重、岗位分析和动态补充关键词，体现了基础 Agent 的规划与反思能力。
- **真实求职场景落地**：围绕 AI/算法类岗位，输出岗位摘要、技术标签、核心要求、亮点、风险项和推荐分数，结果更接近 HR 或求职者真实会看的信息。
- **半自动投递准备**：针对单个岗位生成简历优化点、中文求职信、申请表回答和 STAR 故事，帮助把岗位分析进一步转化为投递材料。
- **本地 Web 前端**：通过浏览器完成搜索、查看岗位、生成投递材料等操作，降低命令行工具的使用门槛。
- **工程化测试与报告**：集成 Pytest、Requests 接口测试、Playwright 前端冒烟测试、coverage、HTML 报告和 Allure 结果，方便展示项目质量意识。
- **数据可导出**：岗位结果会保存为 JSON、CSV 和投递跟踪表，便于后续筛选、复盘和二次分析。

## 功能概览

| 模块 | 能力 |
| --- | --- |
| 求职目标理解 | 解析用户输入，提取岗位方向、经验要求、目标数量和搜索关键词 |
| 岗位搜索 | 基于 SerpAPI 检索 BOSS直聘、猎聘、智联招聘等站点的公开岗位结果 |
| JD 分析 | 使用大模型判断岗位相关性，提取技术标签、要求、亮点、风险和匹配度 |
| 岗位管理 | 前端展示岗位卡片、搜索状态、日志、评分、来源和岗位详情 |
| 投递材料 | 生成简历优化建议、求职信、申请表回答和 STAR 面试故事 |
| 结果导出 | 输出 JSON、CSV 和投递跟踪表，保存在 `output/` 目录 |
| 自动化测试 | 覆盖 Mock 单元测试、接口测试、前端 E2E 冒烟测试和覆盖率报告 |

## 技术栈

- **语言**：Python
- **Web 服务**：`http.server`、`ThreadingHTTPServer`
- **前端**：原生 HTML / CSS / JavaScript
- **AI 能力**：智谱 AI `glm-4-flash`
- **搜索能力**：SerpAPI
- **数据建模**：Pydantic
- **数据处理**：Requests、BeautifulSoup、CSV / JSON 导出
- **测试体系**：Pytest、pytest-html、pytest-cov、allure-pytest、Playwright

## 项目结构

```text
AIagent/
├── main.py                 # 项目入口，启动本地 Web 前端
├── ui.py                   # 前端页面、HTTP 接口、后台搜索任务和状态管理
├── agent.py                # JobHuntAgent 主流程，负责任务规划和岗位收集
├── tools.py                # 搜索、JD 抓取、大模型分析、投递材料生成等工具函数
├── models.py               # 岗位数据模型
├── export.py               # JSON、CSV、投递跟踪表导出
├── run_tests.py            # 测试运行入口，统一生成测试报告
├── tests/                  # 单元测试、接口测试和 Playwright 冒烟测试
├── examples/               # 示例数据
├── output/                 # 本地生成的岗位结果
└── reports/                # 本地生成的测试与覆盖率报告
```

## 快速开始

创建虚拟环境并安装依赖：

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
```

复制环境变量模板：

```bash
cp api.env.example api.env
```

编辑 `api.env`，填入自己的密钥：

```text
ZHIPUAI_API_KEY=你的智谱AI密钥
SERPAPI_KEY=你的SerpAPI密钥
```

启动前端：

```bash
./venv/Scripts/python.exe main.py
```

浏览器打开：

```text
http://127.0.0.1:7860
```

示例输入：

```text
帮我找 20 个适合校招的 AI 算法工程师岗位，重点关注大模型、NLP 和机器学习方向
```

## 测试与报告

安装测试依赖：

```bash
./venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

运行全部测试：

```bash
./venv/Scripts/python.exe run_tests.py
```

快速测试，不跑 Playwright：

```bash
./venv/Scripts/python.exe run_tests.py --skip-e2e
```

测试完成后会生成以下报告：

- `reports/pytest-report.html`
- `reports/htmlcov/index.html`
- `reports/coverage.xml`
- `reports/allure-results/`
- `reports/playwright-trace.zip`
- `reports/api-test-stats.json`

## 适合向 HR 展示的能力点

- **AI 应用落地能力**：不是单点 Demo，而是围绕求职业务场景设计完整工作流。
- **Agent 思维**：包含目标解析、关键词生成、循环搜索、结果过滤和过程日志。
- **工程交付意识**：有清晰模块拆分、配置隔离、数据导出、自动化测试和报告产物。
- **产品体验意识**：提供本地浏览器界面，让非技术用户也能理解和操作。
- **质量保障意识**：使用 Mock 测试隔离外部服务，并通过接口测试和 E2E 测试验证核心链路。

## 注意事项

- `api.env` 不会提交到 Git，其他人需要复制 `api.env.example` 后自行配置密钥。
- `output/` 和 `reports/` 是本地生成数据，默认不提交。
- 投递功能目前是半自动准备材料，不会自动提交申请，避免误操作真实招聘平台。
- 搜索结果依赖 SerpAPI 和公开网页内容，不同时间运行可能得到不同岗位结果。
