"""Playwright冒烟测试：生成trace和失败截图"""
from pathlib import Path

import pytest


@pytest.mark.e2e
def test_frontend_smoke_with_trace(ui_server):
    playwright = pytest.importorskip("playwright.sync_api")
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    trace_path = reports_dir / "playwright-trace.zip"
    screenshot_path = reports_dir / "failure-screenshot.png"

    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright Chromium不可用：{exc}")

        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()

        try:
            page.goto(ui_server, wait_until="networkidle")
            page.get_by_text("AI求职助手").first.wait_for(timeout=5000)
            page.get_by_text("AI Engineer Intern").first.wait_for(timeout=5000)
            page.get_by_text("投递准备").first.wait_for(timeout=5000)
        except Exception:
            page.screenshot(path=str(screenshot_path), full_page=True)
            raise
        finally:
            context.tracing.stop(path=str(trace_path))
            context.close()
            browser.close()

    assert trace_path.exists()
