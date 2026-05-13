"""Mock测试：验证解析、脱敏和兜底逻辑"""
import requests
import pytest

import tools


@pytest.mark.mock
def test_normalize_analysis_deduplicates_summary():
    result = tools._normalize_analysis({
        "is_ai": True,
        "confidence": 0.8,
        "requirements": "要求熟悉Python、RAG和模型部署",
        "jd_summary": "要求熟悉Python、RAG和模型部署",
    })

    assert result["is_ai"] is True
    assert result["requirements"] != result["jd_summary"]
    assert result["match_score"] == 4.0


@pytest.mark.mock
def test_serpapi_error_masks_api_key():
    error = requests.exceptions.SSLError(
        "https://serpapi.com/search?api_key=secret-key&q=test"
    )

    text = tools._safe_error(error)

    assert "secret-key" not in text
    assert "api_key=***" in text


@pytest.mark.mock
def test_application_pack_fallback_contains_star_story():
    pack = tools._fallback_application_pack({
        "title": "AI Engineer Intern",
        "company": "TestAI",
        "tech_tags": ["LLM", "RAG"],
    })

    assert pack["resume_tips"]
    assert pack["cover_letter"]
    assert pack["star_stories"][0]["situation"]
    assert pack["manual_checklist"][-1] == "人工确认并提交"


@pytest.mark.mock
def test_search_jobs_uses_mocked_serpapi(monkeypatch):
    def fake_request(params):
        return {
            "organic_results": [{
                "title": "AI Engineer Intern - TestAI",
                "link": "https://example.com/jobs/1",
                "snippet": "上海 Python RAG 20k-30k",
            }]
        }

    monkeypatch.setattr(tools, "_serpapi_request", fake_request)
    jobs = tools.search_jobs("AI Engineer 实习", "liepin")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "AI Engineer Intern"
    assert jobs[0]["company"] == "TestAI"
