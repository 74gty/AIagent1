"""接口自动化测试：Pytest + Requests"""
import json

import pytest
import requests

import ui


@pytest.mark.api
def test_home_and_status_api(ui_server, api_stats):
    home = requests.get(f"{ui_server}/", timeout=5)
    status = requests.get(f"{ui_server}/api/status", timeout=5)

    assert home.status_code == 200
    assert "AI求职助手" in home.text
    assert status.status_code == 200
    assert status.json()["running"] is False
    assert api_stats["total"] == 2
    assert api_stats["status_codes"]["200"] == 2


@pytest.mark.api
def test_jobs_api_returns_normalized_jobs(ui_server):
    response = requests.get(f"{ui_server}/api/jobs", timeout=5)

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["application_pack"] == {}
    assert jobs[0]["match_score"] == 4.2


@pytest.mark.api
def test_search_api_rejects_empty_query(ui_server):
    response = requests.post(f"{ui_server}/api/search", json={"query": ""}, timeout=5)

    assert response.status_code == 400
    assert response.json()["ok"] is False


@pytest.mark.api
def test_apply_api_generates_application_pack(ui_server, monkeypatch, tmp_path):
    pack = {
        "resume_tips": ["突出RAG项目"],
        "cover_letter": "您好，我对该岗位很感兴趣。",
        "form_answers": [{"question": "为什么适合？", "answer": "具备相关项目经验。"}],
        "star_stories": [{
            "title": "RAG项目",
            "situation": "需要搭建检索增强应用",
            "task": "负责核心实现",
            "action": "完成接口与评估",
            "result": "形成可演示版本",
            "reflection": "后续可加强监控",
        }],
        "manual_checklist": ["打开岗位链接", "人工确认并提交"],
    }

    monkeypatch.setattr(ui, "generate_application_pack", lambda job: pack)

    # 保存到隔离目录，避免修改真实output数据。
    def quiet_save(jobs):
        path = tmp_path / "saved_jobs.json"
        path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(ui, "save_jobs", quiet_save)

    response = requests.post(f"{ui_server}/api/apply", json={"index": 0}, timeout=5)

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["pack"]["star_stories"][0]["title"] == "RAG项目"
