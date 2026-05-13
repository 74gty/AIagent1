""" - Agent工具集"""
import json
import os
import time
import random
import re
import queue
import threading
import requests
from bs4 import BeautifulSoup
from zhipuai import ZhipuAI
from config import ZHIPUAI_API_KEY, MODEL_NAME, SERPAPI_KEY, JOB_SITES

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

llm_client = ZhipuAI(api_key=ZHIPUAI_API_KEY)

GOAL_TIMEOUT_SECONDS = int(os.getenv("GOAL_TIMEOUT_SECONDS", "20"))
ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "25"))
KEYWORD_TIMEOUT_SECONDS = int(os.getenv("KEYWORD_TIMEOUT_SECONDS", "15"))
APPLICATION_TIMEOUT_SECONDS = int(os.getenv("APPLICATION_TIMEOUT_SECONDS", "35"))
SEARCH_TIMEOUT_SECONDS = int(os.getenv("SEARCH_TIMEOUT_SECONDS", "45"))
SERPAPI_RETRIES = int(os.getenv("SERPAPI_RETRIES", "3"))
SERPAPI_CONNECT_TIMEOUT = int(os.getenv("SERPAPI_CONNECT_TIMEOUT", "10"))
SERPAPI_READ_TIMEOUT = int(os.getenv("SERPAPI_READ_TIMEOUT", "25"))


# ========== 工具1：SerpAPI搜索 ==========

def search_jobs(keyword: str, site: str = "zhipin") -> list:
    cfg = JOB_SITES.get(site, {})
    domain = cfg.get("domain", "")
    source_name = cfg.get("name", "网络")

    query = f"site:{domain} {keyword}" if domain else f"{keyword} 招聘"
    print(f" SerpAPI搜索：\"{query}\"")

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "hl": "zh-cn",
        "gl": "cn",
        "num": 20,
        "output": "json",
    }

    try:
        data = _call_with_timeout(lambda: _serpapi_request(params),
                                  SEARCH_TIMEOUT_SECONDS)
        if data is None:
            print("  ⚠ SerpAPI搜索超时，跳过本轮")
            return []
        organic = data.get("organic_results", [])

        jobs = []
        for item in organic:
            parsed = _parse_serp_result(item, source_name)
            if parsed:
                jobs.append(parsed)

        print(f"共解析到 {len(jobs)} 条结果")
        return jobs

    except Exception as e:
        print(f"  ⚠ SerpAPI搜索失败: {_safe_error(e)}")
        return []


def _serpapi_request(params: dict) -> dict:
    last_error = None
    url = "https://serpapi.com/search.json"

    for attempt in range(1, SERPAPI_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=(SERPAPI_CONNECT_TIMEOUT, SERPAPI_READ_TIMEOUT),
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            last_error = exc
            if attempt < SERPAPI_RETRIES:
                wait = round(1.5 * attempt, 1)
                print(f"  ⚠ SerpAPI连接中断，第{attempt}次重试，等待{wait}s")
                time.sleep(wait)
                continue
            raise last_error
        except Exception as exc:
            raise exc

    raise last_error


def _parse_serp_result(item: dict, source: str) -> dict:
    title = item.get("title", "")
    link = item.get("link", "")
    snippet = item.get("snippet", "")

    if not title:
        return None

    clean = re.split(
        r'\s*[-–|_]\s*(BOSS|猎聘|牛客|拉勾|智联|招聘)',
        title, flags=re.IGNORECASE
    )[0].strip()
    if not clean or len(clean) < 2:
        return None

    job_title = clean
    company = ""
    parts = re.split(r'[-_·|/]', clean, maxsplit=1)
    if len(parts) == 2:
        job_title = parts[0].strip()
        company = parts[1].strip()

    salary = "面议"
    m = re.search(r'(\d+[kK]?\s*[-~至]\s*\d+[kK]?)', snippet)
    if m:
        salary = m.group(1)

    location = ""
    m = re.search(
        r'(北京|上海|深圳|广州|杭州|成都|南京|武汉|西安|苏州|合肥|长沙|重庆|天津)',
        title + snippet
    )
    if m:
        location = m.group(1)

    return {
        "title": job_title,
        "company": company,
        "salary": salary,
        "location": location,
        "job_url": link,
        "source": source,
        "snippet": snippet,
    }


# ========== 工具2：抓取详情页 ==========

def scrape_detail(url: str) -> str:
    if not url:
        return ""
    try:
        time.sleep(random.uniform(0.5, 1.5))
        resp = requests.get(url, headers=HEADERS, timeout=6)
        soup = BeautifulSoup(resp.text, "html.parser")

        for sel in [".job-detail", ".job-desc", ".job-description",
                    ".position-content", "[class*='description']",
                    "[class*='detail']", ".job-sec"]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator="\n", strip=True)[:1500]

        body = soup.find("body")
        return body.get_text(separator="\n", strip=True)[:1500] if body else ""
    except Exception:
        return ""


# ========== 工具3：LLM分析 ==========

def analyze_job(title: str, company: str, jd_text: str = "") -> dict:
    prompt = f"""请分析以下岗位是否属于AI Engineer方向（包括机器学习、深度学习、NLP、CV、推荐系统、大模型、算法工程等AI相关岗位）。

岗位名称：{title}
公司：{company}
岗位描述：{jd_text if jd_text else '无详细描述'}

请严格以JSON格式返回（不要返回任何其他内容）：
{{
  "is_ai": true或false,
  "confidence": 0到1的数字,
  "match_score": 1到5的数字,
  "recommendation": "强烈建议/建议关注/谨慎考虑/不建议",
  "tech_tags": ["标签1","标签2"],
  "requirements": "候选人必须满足的3-5个核心要求，合并成一句话，不要复述岗位摘要",
  "highlights": ["岗位亮点1", "岗位亮点2"],
  "risk_flags": ["风险点1", "风险点2"],
  "jd_summary": "岗位实际做什么的一句话摘要，只描述工作内容，不写候选人要求"
}}"""

    try:
        resp = _llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
            timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
        )
        if resp is None:
            raise TimeoutError("LLM分析超时")
        text = resp.choices[0].message.content.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            text = m.group(1) if m else "{}"
        return _normalize_analysis(json.loads(text))
    except Exception:
        return _rule_fallback(title, jd_text)


def _normalize_analysis(data: dict) -> dict:
    # 统一LLM输出字段，避免后续导出和UI遇到缺失值。
    confidence = _to_float(data.get("confidence", 0.0), 0.0)
    match_score = _to_float(data.get("match_score", confidence * 5), 0.0)
    match_score = max(0.0, min(match_score, 5.0))
    requirements = data.get("requirements", "") or ""
    jd_summary = data.get("jd_summary", "") or ""
    if requirements and jd_summary and requirements.strip() == jd_summary.strip():
        jd_summary = _summary_from_requirements(requirements)

    return {
        "is_ai": _to_bool(data.get("is_ai", False)),
        "confidence": max(0.0, min(confidence, 1.0)),
        "match_score": match_score,
        "recommendation": data.get("recommendation", "待评估") or "待评估",
        "tech_tags": _to_list(data.get("tech_tags", [])),
        "requirements": requirements,
        "highlights": _to_list(data.get("highlights", [])),
        "risk_flags": _to_list(data.get("risk_flags", [])),
        "jd_summary": jd_summary,
    }


def generate_application_pack(job: dict) -> dict:
    """生成半自动投递材料，不提交申请。"""
    prompt = f"""你是求职申请助手。请基于岗位信息生成半自动投递准备材料，但不要声称已经投递，也不要编造候选人经历。

岗位：{job.get("title", "")}
公司：{job.get("company", "")}
地点：{job.get("location", "")}
薪资：{job.get("salary", "")}
岗位摘要：{job.get("jd_summary", "")}
核心要求：{job.get("requirements", "")}
技术标签：{job.get("tech_tags", [])}
岗位亮点：{job.get("highlights", [])}
风险提示：{job.get("risk_flags", [])}

请严格返回JSON：
{{
  "resume_tips": ["简历该突出什么1", "简历该突出什么2", "简历该突出什么3"],
  "cover_letter": "一段可复制的中文求职信，不超过180字",
  "form_answers": [
    {{"question": "为什么适合这个岗位？", "answer": "回答"}},
    {{"question": "相关项目/经历怎么写？", "answer": "回答"}},
    {{"question": "可到岗/求职动机怎么写？", "answer": "回答"}}
  ],
  "star_stories": [
    {{"title": "故事标题", "situation": "S", "task": "T", "action": "A", "result": "R", "reflection": "复盘"}},
    {{"title": "故事标题", "situation": "S", "task": "T", "action": "A", "result": "R", "reflection": "复盘"}}
  ],
  "manual_checklist": ["打开岗位链接", "核对JD有效性", "按提示调整简历", "人工确认并提交"]
}}"""

    try:
        resp = _llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=1200,
            timeout_seconds=APPLICATION_TIMEOUT_SECONDS,
        )
        if resp is None:
            raise TimeoutError("投递准备生成超时")
        text = resp.choices[0].message.content.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            text = m.group(1) if m else "{}"
        return _normalize_application_pack(json.loads(text), job)
    except Exception:
        return _fallback_application_pack(job)


def _normalize_application_pack(data: dict, job: dict) -> dict:
    fallback = _fallback_application_pack(job)
    form_answers = data.get("form_answers") or fallback["form_answers"]
    star_stories = data.get("star_stories") or fallback["star_stories"]
    return {
        "resume_tips": _to_list(data.get("resume_tips")) or fallback["resume_tips"],
        "cover_letter": data.get("cover_letter") or fallback["cover_letter"],
        "form_answers": form_answers if isinstance(form_answers, list) else fallback["form_answers"],
        "star_stories": star_stories if isinstance(star_stories, list) else fallback["star_stories"],
        "manual_checklist": _to_list(data.get("manual_checklist")) or fallback["manual_checklist"],
    }


def _fallback_application_pack(job: dict) -> dict:
    title = job.get("title", "该岗位")
    company = job.get("company", "贵公司")
    tags = "、".join(_to_list(job.get("tech_tags"))[:4]) or "AI相关技术"
    return {
        "resume_tips": [
            f"在简历摘要中突出与{title}相关的项目经验",
            f"把{tags}相关能力放到技能区靠前位置",
            "补充可量化结果，例如准确率、性能、部署规模或业务影响",
        ],
        "cover_letter": (
            f"您好，我对{company}的{title}很感兴趣。我的背景与岗位中的"
            f"{tags}方向有较强关联，能够围绕模型应用、工程落地和问题分析推进工作。"
            "期待有机会进一步沟通我能为团队带来的价值。"
        ),
        "form_answers": [
            {
                "question": "为什么适合这个岗位？",
                "answer": f"我会重点说明自己与{tags}相关的项目、工程实现和学习能力。",
            },
            {
                "question": "相关项目/经历怎么写？",
                "answer": "建议用问题、方法、结果三段式描述，并补充量化指标。",
            },
            {
                "question": "求职动机怎么写？",
                "answer": f"可以围绕对{company}业务方向和AI工程落地场景的兴趣展开。",
            },
        ],
        "star_stories": [
            {
                "title": "AI项目落地故事",
                "situation": "团队需要把一个AI能力从实验验证推进到可用原型。",
                "task": "负责梳理需求、选择方案并完成核心实现。",
                "action": "拆分数据、模型、接口和评估环节，快速迭代并记录效果。",
                "result": "形成可演示结果，并明确后续优化方向。",
                "reflection": "面试时要强调取舍、指标和复盘，而不仅是技术栈。",
            },
            {
                "title": "复杂问题排查故事",
                "situation": "项目效果或稳定性没有达到预期。",
                "task": "定位主要瓶颈并提出可执行改进。",
                "action": "从数据质量、模型表现、工程链路逐层排查。",
                "result": "找到关键问题并推动修复。",
                "reflection": "体现结构化分析能力和跨环节协作能力。",
            },
        ],
        "manual_checklist": ["打开岗位链接", "确认岗位仍有效", "按建议调整简历", "人工确认并提交"],
    }


def _summary_from_requirements(requirements: str) -> str:
    text = requirements.strip()
    if len(text) > 45:
        text = text[:45].rstrip("，。；,; ") + "..."
    return f"该岗位围绕AI相关工程任务展开，重点参考核心要求：{text}"


def _llm_chat(messages: list, temperature: float, max_tokens: int,
              timeout_seconds: int):
    # 给外部LLM调用加超时，避免前端一直停在“正在理解”。
    return _call_with_timeout(
        lambda: llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ),
        timeout_seconds,
    )


def _call_with_timeout(func, timeout_seconds: int):
    result_queue = queue.Queue(maxsize=1)

    def runner():
        try:
            result_queue.put((True, func()))
        except Exception as exc:
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    try:
        ok, value = result_queue.get(timeout=timeout_seconds)
    except queue.Empty:
        return None
    if ok:
        return value
    raise value


def _safe_error(error: Exception) -> str:
    text = str(error)
    text = re.sub(r'(api_key=)[^&\s]+', r'\1***', text)
    text = text.replace(SERPAPI_KEY, "***") if SERPAPI_KEY else text
    return f"{error.__class__.__name__}: {text}"


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ["true", "是", "yes", "1"]
    return bool(value)


def _to_list(value) -> list:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _rule_fallback(title: str, jd_text: str = "") -> dict:
    ai_kw = ["ai", "人工智能", "机器学习", "深度学习", "算法", "nlp", "cv",
             "大模型", "llm", "pytorch", "tensorflow", "推荐", "神经网络",
             "transformer", "模型", "数据挖掘", "自然语言", "计算机视觉"]
    text = (title + " " + jd_text).lower()
    hits = [k for k in ai_kw if k in text]
    confidence = min(len(hits) / 4, 1.0)
    match_score = round(max(confidence * 5, 1.0), 1) if hits else 0.0
    recommendation = "建议关注" if match_score >= 3.5 else "谨慎考虑"
    return {
        "is_ai": len(hits) >= 1,
        "confidence": confidence,
        "match_score": match_score,
        "recommendation": recommendation,
        "tech_tags": hits[:6],
        "requirements": f"要求候选人具备{('、'.join(hits[:5]) if hits else 'AI相关')}经验或学习能力",
        "highlights": ["命中AI相关关键词"] if hits else [],
        "risk_flags": ["缺少详细JD，建议人工复核"] if not jd_text else [],
        "jd_summary": "岗位内容疑似与AI工程、算法或模型应用相关，建议结合原始链接复核",
    }


def parse_user_goal(user_input: str) -> dict:
    prompt = f"""你是CareerPilot职涯导航员。请解析用户的求职需求，提取关键信息。

用户说："{user_input}"

请以JSON格式返回（不要返回其他内容）：
{{
    "job_type": "岗位类型",
    "target_count": 目标数量（数字，默认50）,
    "experience_level": "校招/实习/社招",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "summary": "一句话总结"
}}"""

    try:
        resp = _llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
            timeout_seconds=GOAL_TIMEOUT_SECONDS,
        )
        if resp is None:
            raise TimeoutError("需求理解超时")
        text = resp.choices[0].message.content.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            text = m.group(1) if m else "{}"
        return _normalize_goal(json.loads(text), user_input)
    except Exception:
        print("  ⚠ 需求理解调用超时或失败，使用规则解析继续搜索")
        return _fallback_goal(user_input)


def _normalize_goal(goal: dict, user_input: str) -> dict:
    fallback = _fallback_goal(user_input)
    keywords = goal.get("keywords") or fallback["keywords"]
    if isinstance(keywords, str):
        keywords = [keywords]
    return {
        "job_type": goal.get("job_type") or fallback["job_type"],
        "target_count": _parse_count(goal.get("target_count"), fallback["target_count"]),
        "experience_level": goal.get("experience_level") or fallback["experience_level"],
        "keywords": [str(k).strip() for k in keywords if str(k).strip()][:6],
        "summary": goal.get("summary") or user_input,
    }


def _fallback_goal(user_input: str) -> dict:
    lower = user_input.lower()
    job_type = "AI工程师"
    if "算法" in user_input:
        job_type = "算法工程师"
    elif "机器学习" in user_input or "ml" in lower:
        job_type = "机器学习工程师"
    elif "大模型" in user_input or "llm" in lower:
        job_type = "大模型工程师"

    exp = "校招"
    if "实习" in user_input:
        exp = "实习"
    elif "社招" in user_input or "高级" in user_input or "senior" in lower:
        exp = "社招"

    count = _parse_count(None, 50)
    m = re.search(r'(\d+)\s*个?', user_input)
    if m:
        count = _parse_count(m.group(1), 50)

    return {
        "job_type": job_type,
        "target_count": count,
        "experience_level": exp,
        "keywords": [
            f"{job_type} {exp}",
            f"AI Engineer {exp}",
            f"算法工程师 {exp}",
            f"机器学习 {exp}",
            f"大模型 {exp}",
        ],
        "summary": user_input,
    }


def _parse_count(value, default: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(1, min(count, 200))


def generate_keywords(used: list, found: int, target: int) -> list:
    prompt = f"""我在搜索AI Engineer校招岗位，目前找到{found}/{target}条，不够。
已用关键词：{used}

请生成5个新的搜索关键词（不要重复），与AI/ML/算法工程师校招实习相关。
严格返回JSON数组：["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]"""

    try:
        resp = _llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=200,
            timeout_seconds=KEYWORD_TIMEOUT_SECONDS,
        )
        if resp is None:
            raise TimeoutError("关键词生成超时")
        text = resp.choices[0].message.content.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            text = m.group(1) if m else "[]"
        return json.loads(text)
    except Exception:
        return ["智能算法 校招", "模型部署 实习", "MLOps 校招",
                "AI应用开发 应届", "多模态算法 校招"]
