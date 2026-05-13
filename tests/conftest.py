"""测试夹具：启动本地服务并统计接口请求"""
import json
import socket
import threading

import pytest
import requests
from http.server import ThreadingHTTPServer

import ui

API_STATS = {"total": 0, "status_codes": {}, "methods": {}}


@pytest.fixture
def sample_job():
    return {
        "title": "AI Engineer Intern",
        "company": "TestAI",
        "location": "上海",
        "salary": "面议",
        "tech_tags": ["LLM", "RAG"],
        "requirements": "要求具备Python、RAG和接口开发基础",
        "highlights": ["方向匹配"],
        "risk_flags": [],
        "recommendation": "建议关注",
        "match_score": 4.2,
        "jd_summary": "参与AI应用和检索增强系统开发",
        "status": "evaluated",
        "source": "测试",
        "job_url": "https://example.com/jobs/1",
        "confidence": 0.8,
        "application_pack": {},
    }


@pytest.fixture
def isolated_output(tmp_path, monkeypatch, sample_job):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    jobs_path = output_dir / "jobs_serpapi.json"
    jobs_path.write_text(
        json.dumps([sample_job], ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(ui, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(ui, "JOBS_JSON", str(jobs_path))
    monkeypatch.setattr(ui, "LEGACY_JOBS_JSON", str(output_dir / "jobs.json"))
    return output_dir


@pytest.fixture
def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(autouse=True)
def count_api_requests():
    original_request = requests.Session.request

    def counted_request(self, method, url, **kwargs):
        response = original_request(self, method, url, **kwargs)
        API_STATS["total"] += 1
        code = str(response.status_code)
        method_key = method.upper()
        API_STATS["status_codes"][code] = API_STATS["status_codes"].get(code, 0) + 1
        API_STATS["methods"][method_key] = API_STATS["methods"].get(method_key, 0) + 1
        return response

    requests.Session.request = counted_request
    try:
        yield
    finally:
        requests.Session.request = original_request


@pytest.fixture
def api_stats():
    return API_STATS


@pytest.fixture
def ui_server(isolated_output, free_port):
    server = ThreadingHTTPServer(("127.0.0.1", free_port), ui.JobUIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{free_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def pytest_sessionfinish(session, exitstatus):
    # 生成一个轻量接口统计文件，便于不装额外插件时也能查看接口测试数量。
    reports_dir = session.config.rootpath / "reports"
    reports_dir.mkdir(exist_ok=True)
    stats_file = reports_dir / "api-test-stats.json"
    stats_file.write_text(
        json.dumps({
            "exitstatus": exitstatus,
            "total_requests": API_STATS["total"],
            "status_codes": API_STATS["status_codes"],
            "methods": API_STATS["methods"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
