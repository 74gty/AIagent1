"""SerpAPI版本 - Agent主控"""
from typing import List, Set, Tuple, Optional
from models import JobInfo
from tools import (
    search_jobs, scrape_detail, analyze_job,
    generate_keywords, parse_user_goal,
)
from config import TARGET_JOB_COUNT, MAX_ITERATIONS, JOB_SITES


class JobHuntAgent:

    def __init__(self):
        self.collected: List[JobInfo] = []
        self.seen_uids: Set[str] = set()
        self.used_keywords: List[str] = []
        self.keyword_queue: List[str] = []
        self.site_list = list(JOB_SITES.keys())
        self.iteration = 0
        self.site_index = 0
        self.target = TARGET_JOB_COUNT

    @property
    def count(self) -> int:
        return len(self.collected)

    @property
    def enough(self) -> bool:
        return self.count >= self.target

    def chat(self, user_input: str) -> List[JobInfo]:
        print(f"\n Agent收到需求，正在理解...")
        goal = parse_user_goal(user_input)

        self.target = int(goal.get("target_count", TARGET_JOB_COUNT))
        user_keywords = goal.get("keywords", [])
        exp = goal.get("experience_level", "校招")
        job_type = goal.get("job_type", "AI工程师")

        print(f" Agent理解：")
        print(f"   岗位类型：{job_type}")
        print(f"   目标数量：{self.target}")
        print(f"   经验要求：{exp}")
        print(f"   生成关键词：{user_keywords}")
        print(f"   需求摘要：{goal.get('summary', '')}")

        self.keyword_queue = user_keywords + [
            f"{job_type} 招聘 2025",
            f"大模型 {exp}",
            f"深度学习 {exp}",
            f"NLP算法 {exp}",
            f"CV算法 {exp}",
            f"推荐系统 {exp}",
            f"AIGC {exp}",
        ]
        return self._run()

    def _run(self) -> List[JobInfo]:
        print(f"\n Agent开始执行，目标：{self.target} 条岗位")
        print("=" * 60)

        while not self.enough and self.iteration < MAX_ITERATIONS:
            self.iteration += 1
            print(f"\n--- 第 {self.iteration}/{MAX_ITERATIONS} 轮 "
                  f"| 已收集 {self.count}/{self.target} ---")

            keyword, site = self._plan()
            if keyword is None:
                print("  关键词耗尽，让AI生成新关键词...")
                self._expand_keywords()
                keyword, site = self._plan()
                if keyword is None:
                    break

            raw_jobs = search_jobs(keyword, site)

            new_count = 0
            for raw in raw_jobs:
                if self.enough:
                    break
                if self._process_one(raw):
                    new_count += 1

            self._reflect(keyword, site, len(raw_jobs), new_count)

        print("\n" + "=" * 60)
        print(f"✅ Agent完成，共收集 {self.count} 条岗位（目标{self.target}）")

        source_stats = {}
        for job in self.collected:
            source_stats[job.source] = source_stats.get(job.source, 0) + 1
        print(f"   来源分布：{source_stats}")
        return self.collected

    def _plan(self) -> Tuple[Optional[str], str]:
        if not self.keyword_queue:
            return None, ""
        keyword = self.keyword_queue.pop(0)
        self.used_keywords.append(keyword)
        site = self.site_list[self.site_index % len(self.site_list)]
        self.site_index += 1
        print(f"  规划：关键词=\"{keyword}\" 网站={JOB_SITES[site]['name']}")
        return keyword, site

    def _process_one(self, raw: dict) -> bool:
        title = raw.get("title", "")
        company = raw.get("company", "")

        jd_text = scrape_detail(raw.get("job_url", ""))
        if not jd_text:
            jd_text = raw.get("snippet", "")

        analysis = analyze_job(title, company, jd_text)
        if not analysis.get("is_ai", False):
            return False

        job = JobInfo(
            title=title, company=company,
            location=raw.get("location", ""),
            salary=raw.get("salary", "面议"),
            tech_tags=analysis.get("tech_tags", []),
            requirements=analysis.get("requirements", ""),
            highlights=analysis.get("highlights", []),
            risk_flags=analysis.get("risk_flags", []),
            recommendation=analysis.get("recommendation", "待评估"),
            match_score=analysis.get("match_score", 0.0),
            jd_summary=analysis.get("jd_summary", ""),
            source=raw.get("source", ""),
            job_url=raw.get("job_url", ""),
            confidence=analysis.get("confidence", 0.0),
        )

        if job.uid in self.seen_uids:
            return False

        self.seen_uids.add(job.uid)
        self.collected.append(job)
        print(f"  ✅ [{self.count}] {job.title} @ {job.company}")
        return True

    def _reflect(self, keyword, site, raw_count, new_count):
        if raw_count == 0:
            print(f"  反思：\"{keyword}\"无结果")
            if keyword not in self.keyword_queue:
                self.keyword_queue.insert(0, keyword)
                self.site_index += 1
        elif new_count > 0:
            print(f"  反思：本轮新增{new_count}条")

        expected = (self.iteration / MAX_ITERATIONS) * self.target
        if self.count < expected * 0.5 and len(self.keyword_queue) < 3:
            self._expand_keywords()

    def _expand_keywords(self):
        new_kws = generate_keywords(self.used_keywords, self.count, self.target)
        fresh = [k for k in new_kws
                 if k not in self.used_keywords and k not in self.keyword_queue]
        self.keyword_queue.extend(fresh)
        print(f"  🔄 AI生成了 {len(fresh)} 个新关键词：{fresh}")
