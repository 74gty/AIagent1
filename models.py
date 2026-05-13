"""数据模型"""
from pydantic import BaseModel, Field
from typing import Any, Dict, List
import hashlib


class JobInfo(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = "面议"
    tech_tags: List[str] = Field(default_factory=list)
    requirements: str = ""
    highlights: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    recommendation: str = "待评估"
    match_score: float = 0.0
    jd_summary: str = ""
    status: str = "evaluated"
    source: str = ""
    job_url: str = ""
    confidence: float = 0.0
    application_pack: Dict[str, Any] = Field(default_factory=dict)

    @property
    def uid(self) -> str:
        raw = f"{self.title}|{self.company}".lower().strip()
        return hashlib.md5(raw.encode()).hexdigest()
