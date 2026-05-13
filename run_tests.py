"""测试运行入口：生成HTML、Allure、覆盖率和接口统计"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="运行项目测试并生成报告")
    parser.add_argument("--skip-e2e", action="store_true", help="跳过Playwright测试")
    args = parser.parse_args()

    reports = Path("reports")
    reports.mkdir(exist_ok=True)

    pytest_args = [
        sys.executable, "-m", "pytest",
        "--html=reports/pytest-report.html",
        "--self-contained-html",
        "--alluredir=reports/allure-results",
        "--cov=.",
        "--cov-report=xml:reports/coverage.xml",
        "--cov-report=html:reports/htmlcov",
    ]
    if args.skip_e2e:
        pytest_args.extend(["-m", "not e2e"])

    result = subprocess.run(pytest_args, check=False)
    _write_api_summary(reports)
    return result.returncode


def _write_api_summary(reports: Path):
    # 从pytest结果侧生成固定入口，便于前端/人工查看测试产物位置。
    summary = {
        "pytest_html": str(reports / "pytest-report.html"),
        "allure_results": str(reports / "allure-results"),
        "coverage_xml": str(reports / "coverage.xml"),
        "coverage_html": str(reports / "htmlcov" / "index.html"),
        "playwright_trace": str(reports / "playwright-trace.zip"),
        "failure_screenshot": str(reports / "failure-screenshot.png"),
    }
    (reports / "test-artifacts.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
