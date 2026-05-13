"""项目配置"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "api.env"))

ZHIPUAI_API_KEY = os.getenv("ZHIPUAI_API_KEY")
if not ZHIPUAI_API_KEY:
    raise ValueError("❌ 未找到 ZHIPUAI_API_KEY，请检查 api.env")

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
if not SERPAPI_KEY:
    raise ValueError("❌ 未找到 SERPAPI_KEY，请检查 api.env")

MODEL_NAME = "glm-4-flash"

TARGET_JOB_COUNT = 50
MAX_ITERATIONS = 20

JOB_SITES = {
    "zhipin": {"name": "BOSS直聘", "domain": "zhipin.com"},
    "liepin": {"name": "猎聘", "domain": "liepin.com"},
    "zhilian": {"name": "智联招聘", "domain": "zhaopin.com"},
}