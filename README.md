# CareerPilot 职涯导航员

一个本地运行的 AI 职涯导航工具，支持岗位搜索、岗位分析、半自动投递准备、STAR 故事生成和测试报告产出。

## 功能

- 前端搜索岗位，在终端启动
- 岗位列表、评分、摘要、核心要求、亮点和风险提示
- 半自动投递准备：简历优化点、求职信、申请表回答、STAR 故事
- Pytest + Requests 接口自动化测试
- Pytest HTML、Allure、Playwright Trace、coverage 报告

## 快速开始

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
cp api.env.example api.env
```

编辑 `api.env`，填入自己的 `ZHIPUAI_API_KEY` 和 `SERPAPI_KEY`。

启动前端：

```bash
./venv/Scripts/python.exe main.py
```

浏览器打开：

```text
http://127.0.0.1:7860
```

## 测试

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

报告位置：

- `reports/pytest-report.html`
- `reports/htmlcov/index.html`
- `reports/coverage.xml`
- `reports/allure-results/`
- `reports/playwright-trace.zip`
- `reports/api-test-stats.json`

## 注意

- `api.env` 不会提交到 Git，其他人需要复制 `api.env.example` 自己配置。
- `output/` 和 `reports/` 是本地生成数据，默认不提交。
- 投递功能目前是半自动准备材料，不会自动提交申请。
