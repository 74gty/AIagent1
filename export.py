"""导出结果"""
import json
import csv
import os
from typing import List
from models import JobInfo

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def ensure_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def to_json(jobs: List[JobInfo], path: str = None):
    ensure_dir()
    path = path or os.path.join(OUTPUT_DIR, "jobs_serpapi.json")
    data = [j.model_dump() for j in jobs]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f" JSON已保存：{path}（{len(jobs)}条）")


def to_csv(jobs: List[JobInfo], path: str = None):
    ensure_dir()
    path = path or os.path.join(OUTPUT_DIR, "jobs_serpapi.csv")
    fields = ["title", "company", "location", "salary",
              "match_score", "recommendation", "tech_tags",
              "requirements", "highlights", "risk_flags", "jd_summary",
              "status", "source", "job_url", "confidence"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for job in jobs:
            row = job.model_dump()
            for key in ["tech_tags", "highlights", "risk_flags"]:
                row[key] = " | ".join(row.get(key, []))
            writer.writerow({k: row.get(k, "") for k in fields})
    print(f" CSV已保存：{path}（{len(jobs)}条）")


def to_tracker(jobs: List[JobInfo], path: str = None):
    ensure_dir()
    path = path or os.path.join(OUTPUT_DIR, "applications.md")

    lines = [
        "# 求职跟踪表",
        "",
        "| # | 公司 | 岗位 | 地点 | Score | 建议 | 状态 | 来源 | 链接 |",
        "|---|------|------|------|-------|------|------|------|------|",
    ]
    for idx, job in enumerate(jobs, 1):
        lines.append(
            "| {idx} | {company} | {title} | {location} | {score:.1f}/5 | "
            "{recommendation} | {status} | {source} | {url} |".format(
                idx=idx,
                company=_cell(job.company),
                title=_cell(job.title),
                location=_cell(job.location),
                score=job.match_score,
                recommendation=_cell(job.recommendation),
                status=_cell(job.status),
                source=_cell(job.source),
                url=f"[打开]({job.job_url})" if job.job_url else "",
            )
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f" 跟踪表已保存：{path}（{len(jobs)}条）")


def _cell(value) -> str:
    # Markdown表格中不能直接出现竖线，否则会破坏列结构。
    return str(value or "").replace("|", "/").replace("\n", " ").strip()
