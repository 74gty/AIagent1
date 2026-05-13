"""本地Web前端：搜索、查看、分析岗位"""
import argparse
import contextlib
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from agent import JobHuntAgent
from export import to_csv, to_json, to_tracker
from models import JobInfo
from tools import analyze_job, generate_application_pack, scrape_detail

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
JOBS_JSON = os.path.join(OUTPUT_DIR, "jobs_serpapi.json")
LEGACY_JOBS_JSON = os.path.join(OUTPUT_DIR, "jobs.json")
TASK_TIMEOUT_SECONDS = 30 * 60

task_lock = threading.Lock()
task_state = {
    "running": False,
    "message": "就绪",
    "started_at": "",
    "finished_at": "",
    "count": 0,
    "logs": [],
    "error": "",
}


class UILogBuffer:
    """把Agent的print输出收集到前端状态，不直接刷终端。"""

    def __init__(self):
        self._partial = ""

    def write(self, text):
        if not text:
            return
        self._partial += text
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            _append_log(line.strip())

    def flush(self):
        if self._partial.strip():
            _append_log(self._partial.strip())
        self._partial = ""


class JobUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(APP_HTML)
        elif path == "/api/jobs":
            self._send_json({"jobs": load_jobs()})
        elif path == "/api/status":
            self._send_json(get_task_state())
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_json()
        if path == "/api/search":
            self._start_search(data)
        elif path == "/api/analyze":
            self._analyze_job(data)
        elif path == "/api/apply":
            self._prepare_application(data)
        else:
            self.send_error(404)

    def _start_search(self, data: dict):
        query = (data.get("query") or "").strip()
        if not query:
            self._send_json({"ok": False, "message": "请输入搜索需求"}, status=400)
            return

        with task_lock:
            if task_state["running"]:
                self._send_json({"ok": False, "message": "已有搜索任务正在运行"}, status=409)
                return
            _reset_task(query)

        thread = threading.Thread(target=run_search_task, args=(query,), daemon=True)
        thread.start()
        self._send_json({"ok": True, "message": "搜索已开始"})

    def _analyze_job(self, data: dict):
        jobs = load_jobs()
        index = data.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(jobs):
            self._send_json({"ok": False, "message": "岗位索引无效"}, status=400)
            return

        job = jobs[index]
        jd_text = scrape_detail(job.get("job_url", "")) or job.get("requirements", "")
        analysis = analyze_job(job.get("title", ""), job.get("company", ""), jd_text)
        job.update({
            "tech_tags": analysis.get("tech_tags", []),
            "requirements": analysis.get("requirements", ""),
            "highlights": analysis.get("highlights", []),
            "risk_flags": analysis.get("risk_flags", []),
            "recommendation": analysis.get("recommendation", "待评估"),
            "match_score": analysis.get("match_score", 0.0),
            "jd_summary": analysis.get("jd_summary", ""),
            "confidence": analysis.get("confidence", 0.0),
        })

        buffer = UILogBuffer()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            save_jobs(jobs)
        buffer.flush()
        self._send_json({"ok": True, "job": _normalize_job(job)})

    def _prepare_application(self, data: dict):
        jobs = load_jobs()
        index = data.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(jobs):
            self._send_json({"ok": False, "message": "岗位索引无效"}, status=400)
            return

        job = jobs[index]
        pack = generate_application_pack(job)
        job["application_pack"] = pack

        buffer = UILogBuffer()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            save_jobs(jobs)
        buffer.flush()
        self._send_json({"ok": True, "job": _normalize_job(job), "pack": pack})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def load_jobs() -> list:
    path = JOBS_JSON if os.path.exists(JOBS_JSON) else LEGACY_JOBS_JSON
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize_job(item) for item in data]


def save_jobs(jobs: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    normalized = [_normalize_job(item) for item in jobs]
    job_models = [JobInfo(**item) for item in normalized]
    to_json(job_models, JOBS_JSON)
    to_csv(job_models)
    to_tracker(job_models)


def run_search_task(query: str):
    buffer = UILogBuffer()
    try:
        _set_task(message="正在理解需求并搜索岗位")
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            agent = JobHuntAgent()
            jobs = agent.chat(query)
            if jobs:
                to_json(jobs, JOBS_JSON)
                to_csv(jobs)
                to_tracker(jobs)
        buffer.flush()
        _set_task(
            running=False,
            message="搜索完成",
            finished_at=_now(),
            count=len(jobs),
        )
    except Exception as exc:
        buffer.flush()
        _set_task(
            running=False,
            message="搜索失败",
            finished_at=_now(),
            error=str(exc),
        )


def run_server(host: str = "127.0.0.1", port: int = 7860, open_browser: bool = True):
    server = ThreadingHTTPServer((host, port), JobUIHandler)
    url = f"http://{host}:{port}"
    print(f"CareerPilot 职涯导航员前端已启动：{url}")
    print("搜索、查看、分析都在浏览器中操作；按 Ctrl+C 关闭服务。")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    server.serve_forever()


def get_task_state() -> dict:
    with task_lock:
        if task_state["running"] and _task_elapsed_seconds() > TASK_TIMEOUT_SECONDS:
            task_state.update({
                "running": False,
                "message": "搜索超时",
                "finished_at": _now(),
                "error": "后台任务超过30分钟未完成，请重新搜索或缩小目标数量。",
            })
        state = dict(task_state)
        state["logs"] = list(task_state["logs"])
        return state


def _reset_task(query: str):
    task_state.update({
        "running": True,
        "message": f"正在搜索：{query}",
        "started_at": _now(),
        "finished_at": "",
        "count": 0,
        "logs": [],
        "error": "",
    })


def _set_task(**kwargs):
    with task_lock:
        task_state.update(kwargs)


def _append_log(line: str):
    if not line:
        return
    with task_lock:
        task_state["logs"].append(line)
        task_state["logs"] = task_state["logs"][-80:]
        task_state["message"] = line


def _normalize_job(job: dict) -> dict:
    # 兼容旧导出文件，保证前端字段稳定。
    confidence = _to_float(job.get("confidence", 0.0))
    match_score = _to_float(job.get("match_score", confidence * 5))
    return {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "salary": job.get("salary", "面议"),
        "tech_tags": _to_list(job.get("tech_tags", [])),
        "requirements": job.get("requirements", ""),
        "highlights": _to_list(job.get("highlights", [])),
        "risk_flags": _to_list(job.get("risk_flags", [])),
        "recommendation": job.get("recommendation", "待评估"),
        "match_score": round(max(0.0, min(match_score, 5.0)), 1),
        "jd_summary": job.get("jd_summary", ""),
        "status": job.get("status", "evaluated"),
        "source": job.get("source", ""),
        "job_url": job.get("job_url", ""),
        "confidence": confidence,
        "application_pack": job.get("application_pack", {}) or {},
    }


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_list(value) -> list:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split("|") if item.strip()]
    return []


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _task_elapsed_seconds() -> float:
    try:
        started = time.strptime(task_state["started_at"], "%Y-%m-%d %H:%M:%S")
        return time.time() - time.mktime(started)
    except (TypeError, ValueError):
        return 0.0


def main():
    parser = argparse.ArgumentParser(description="启动CareerPilot职涯导航员Web前端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    run_server(args.host, args.port, open_browser=not args.no_browser)


APP_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CareerPilot 职涯导航员</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #18212f;
      --muted: #667085;
      --line: #d9e0ea;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --accent-soft: #d9f0ed;
      --warn: #b45309;
      --bad: #b91c1c;
      --good: #15803d;
      --disabled: #98a2b3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 18px 28px;
    }
    h1 {
      margin: 0 0 4px;
      font-size: 24px;
      letter-spacing: 0;
    }
    .sub { color: var(--muted); font-size: 13px; }
    main { padding: 18px 28px 28px; }
    .searchPanel {
      display: grid;
      grid-template-columns: minmax(260px, 1fr) 120px;
      gap: 10px;
      margin-bottom: 12px;
    }
    input, select, button {
      height: 40px;
      border-radius: 6px;
      font-size: 14px;
    }
    input, select {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      padding: 0 10px;
    }
    button {
      border: 0;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
      padding: 0 14px;
    }
    button:hover { background: var(--accent-dark); }
    button.secondary {
      background: var(--accent-soft);
      color: var(--accent-dark);
    }
    button.disabled, button:disabled {
      background: #e4e7ec;
      color: var(--disabled);
      cursor: not-allowed;
    }
    .status {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
    }
    .statusText { color: var(--muted); font-size: 13px; }
    .logs {
      display: none;
      margin-top: 10px;
      max-height: 150px;
      overflow: auto;
      border-top: 1px solid var(--line);
      padding-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .stat strong { display: block; font-size: 24px; margin-bottom: 4px; }
    .stat span { color: var(--muted); font-size: 12px; }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(180px, 2fr) minmax(130px, 1fr) minmax(130px, 1fr);
      gap: 10px;
      margin-bottom: 14px;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.85fr);
      gap: 16px;
      align-items: start;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    th, td {
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }
    th {
      color: var(--muted);
      background: #fbfcfe;
      font-size: 12px;
      font-weight: 700;
    }
    tr { cursor: pointer; }
    tr:hover, tr.active { background: #edf7f5; }
    .score { font-weight: 700; white-space: nowrap; }
    .score.good { color: var(--good); }
    .score.mid { color: var(--warn); }
    .score.low { color: var(--bad); }
    .tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-dark);
      padding: 2px 8px;
      font-size: 12px;
      line-height: 1.2;
    }
    aside {
      position: sticky;
      top: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-height: 300px;
    }
    aside h2 { margin: 0 0 8px; font-size: 20px; letter-spacing: 0; }
    aside h3 { margin: 18px 0 8px; font-size: 14px; }
    .meta { color: var(--muted); font-size: 13px; line-height: 1.6; }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 14px 0;
    }
    .pack {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin-top: 10px;
      background: #fbfcfe;
    }
    .qa {
      border-top: 1px solid var(--line);
      padding-top: 8px;
      margin-top: 8px;
    }
    .qa strong { display: block; margin-bottom: 4px; }
    .copyActions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 10px;
    }
    ul { margin: 8px 0 0 20px; padding: 0; }
    li { margin: 5px 0; }
    a { color: var(--accent); text-decoration: none; font-weight: 700; }
    a:hover { text-decoration: underline; }
    .empty {
      background: var(--panel);
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 36px;
      color: var(--muted);
      text-align: center;
    }
    @media (max-width: 900px) {
      header, main { padding-left: 16px; padding-right: 16px; }
      .searchPanel, .stats, .toolbar, .layout { grid-template-columns: 1fr; }
      aside { position: static; }
      table { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>CareerPilot 职涯导航员</h1>
    <div class="sub">搜索、分析和查看结果都在前端完成</div>
  </header>
  <main>
    <section class="searchPanel">
      <input id="searchInput" placeholder="例如：帮我找50个AI Engineer校招岗位">
      <button id="searchBtn">开始搜索</button>
    </section>
    <section class="status">
      <div>
        <strong id="statusTitle">就绪</strong>
        <div id="statusText" class="statusText">可以输入需求开始搜索。</div>
        <div id="logs" class="logs"></div>
      </div>
      <button id="toggleLogs" class="secondary">后台进度</button>
    </section>
    <section class="stats" id="stats"></section>
    <section class="toolbar">
      <input id="q" type="search" placeholder="搜索已有结果：岗位、公司、技术标签">
      <select id="rec"><option value="">全部建议</option></select>
      <select id="score">
        <option value="0">全部分数</option>
        <option value="4">4分以上</option>
        <option value="3">3分以上</option>
      </select>
    </section>
    <section class="layout">
      <div id="tableWrap"></div>
      <aside id="detail"></aside>
    </section>
  </main>
  <script>
    const state = { jobs: [], selected: 0, running: false, logsOpen: false };

    function scoreClass(score) {
      if (score >= 4) return "good";
      if (score >= 3) return "mid";
      return "low";
    }

    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    async function api(path, options = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || "请求失败");
      return data;
    }

    async function loadJobs() {
      const data = await api("/api/jobs");
      state.jobs = data.jobs || [];
      renderFilters();
      render();
    }

    async function startSearch() {
      const query = document.querySelector("#searchInput").value.trim();
      if (!query) {
        setStatus("缺少搜索需求", "请输入你想找的岗位。");
        return;
      }
      try {
        await api("/api/search", {
          method: "POST",
          body: JSON.stringify({ query }),
        });
        setStatus("搜索已开始", "后台正在执行，结果会自动刷新。");
        pollStatus();
      } catch (err) {
        setStatus("无法开始搜索", err.message);
      }
    }

    async function pollStatus() {
      const data = await api("/api/status");
      state.running = data.running;
      document.querySelector("#searchBtn").disabled = data.running;
      setStatus(data.running ? "正在搜索" : data.message, data.error || data.message || "");
      renderLogs(data.logs || []);
      if (data.running) {
        setTimeout(pollStatus, 1500);
      } else {
        await loadJobs();
      }
    }

    async function analyzeSelected() {
      const job = currentJob();
      if (!job) return;
      setStatus("正在分析岗位", `${job.company} · ${job.title}`);
      try {
        const data = await api("/api/analyze", {
          method: "POST",
          body: JSON.stringify({ index: state.selected }),
        });
        state.jobs[state.selected] = data.job;
        setStatus("分析完成", "已更新岗位评分、亮点和风险提示。");
        render();
      } catch (err) {
        setStatus("分析失败", err.message);
      }
    }

    async function applySelected() {
      const job = currentJob();
      if (!job) return;
      setStatus("正在生成投递准备", `${job.company} · ${job.title}`);
      try {
        const data = await api("/api/apply", {
          method: "POST",
          body: JSON.stringify({ index: state.selected }),
        });
        state.jobs[state.selected] = data.job;
        setStatus("投递准备已生成", "请人工核对后再提交申请。");
        render();
      } catch (err) {
        setStatus("投递准备失败", err.message);
      }
    }

    async function copyText(text, label) {
      try {
        await navigator.clipboard.writeText(text || "");
        setStatus("已复制", label);
      } catch (err) {
        setStatus("复制失败", "浏览器未允许剪贴板访问，请手动选择文本复制。");
      }
    }

    function filteredJobs() {
      const q = document.querySelector("#q").value.trim().toLowerCase();
      const rec = document.querySelector("#rec").value;
      const minScore = Number(document.querySelector("#score").value);
      return state.jobs.filter(job => {
        const text = [
          job.title, job.company, job.location, job.salary,
          job.requirements, job.jd_summary,
          ...(job.tech_tags || [])
        ].join(" ").toLowerCase();
        return (!q || text.includes(q))
          && (!rec || job.recommendation === rec)
          && Number(job.match_score || 0) >= minScore;
      });
    }

    function renderStats(list = filteredJobs()) {
      const total = list.length;
      const avg = total ? list.reduce((sum, job) => sum + Number(job.match_score || 0), 0) / total : 0;
      const high = list.filter(job => Number(job.match_score || 0) >= 4).length;
      const risks = list.filter(job => (job.risk_flags || []).length > 0).length;
      document.querySelector("#stats").innerHTML = [
        ["岗位数", total],
        ["平均分", avg.toFixed(1)],
        ["4分以上", high],
        ["有风险提示", risks],
      ].map(([label, value]) => `
        <div class="stat"><strong>${value}</strong><span>${label}</span></div>
      `).join("");
    }

    function renderTable(list = filteredJobs()) {
      const wrap = document.querySelector("#tableWrap");
      if (list.length === 0) {
        wrap.innerHTML = '<div class="empty">暂无岗位。请在上方输入搜索需求并开始搜索。</div>';
        renderDetail(null);
        return;
      }

      wrap.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>岗位</th>
              <th>地点/薪资</th>
              <th>评分</th>
              <th>建议</th>
              <th>技术标签</th>
            </tr>
          </thead>
          <tbody>
            ${list.map((job, idx) => `
              <tr class="${idx === state.selected ? "active" : ""}" data-idx="${idx}">
                <td><strong>${escapeHtml(job.title)}</strong><br><span class="meta">${escapeHtml(job.company)}</span></td>
                <td>${escapeHtml(job.location || "未知")}<br><span class="meta">${escapeHtml(job.salary || "面议")}</span></td>
                <td class="score ${scoreClass(Number(job.match_score || 0))}">${Number(job.match_score || 0).toFixed(1)}/5</td>
                <td>${escapeHtml(job.recommendation)}</td>
                <td><div class="tags">${(job.tech_tags || []).slice(0, 5).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;

      wrap.querySelectorAll("tr[data-idx]").forEach(row => {
        row.addEventListener("click", () => {
          const visibleIndex = Number(row.dataset.idx);
          const selectedJob = list[visibleIndex];
          state.selected = state.jobs.indexOf(selectedJob);
          render();
        });
      });
      renderDetail(currentJob());
    }

    function renderDetail(job) {
      const detail = document.querySelector("#detail");
      if (!job) {
        detail.innerHTML = "<h2>暂无岗位</h2><p class='meta'>搜索完成后，这里会展示岗位详情和分析。</p>";
        return;
      }
      detail.innerHTML = `
        <h2>${escapeHtml(job.title)}</h2>
        <div class="meta">
          ${escapeHtml(job.company)} · ${escapeHtml(job.location || "未知地点")} · ${escapeHtml(job.source || "未知来源")}<br>
          评分：<strong>${Number(job.match_score || 0).toFixed(1)}/5</strong> · 建议：${escapeHtml(job.recommendation)}
        </div>
        <div class="actions">
          <button class="secondary" id="analyzeBtn">分析岗位</button>
          <button id="applyBtn">投递准备</button>
        </div>
        <h3>岗位摘要</h3>
        <p>${escapeHtml(job.jd_summary || "暂无摘要，请点击分析岗位生成")}</p>
        <h3>核心要求</h3>
        <p>${escapeHtml(job.requirements || "暂无核心要求，请点击分析岗位生成")}</p>
        <h3>岗位亮点</h3>
        ${renderList(job.highlights, "暂无明显亮点")}
        <h3>风险提示</h3>
        ${renderList(job.risk_flags, "暂无明显风险")}
        <h3>技术标签</h3>
        <div class="tags">${(job.tech_tags || []).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
        <h3>链接</h3>
        ${job.job_url ? `<a href="${escapeHtml(job.job_url)}" target="_blank" rel="noreferrer">打开岗位页面</a>` : "<span class='meta'>暂无链接</span>"}
        ${renderApplicationPack(job.application_pack)}
      `;
      document.querySelector("#analyzeBtn").addEventListener("click", analyzeSelected);
      document.querySelector("#applyBtn").addEventListener("click", applySelected);
    }

    function renderList(items, emptyText) {
      if (!items || items.length === 0) return `<p class="meta">${emptyText}</p>`;
      return `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
    }

    function renderApplicationPack(pack) {
      if (!pack || Object.keys(pack).length === 0) return "";
      const answers = Array.isArray(pack.form_answers) ? pack.form_answers : [];
      const stories = Array.isArray(pack.star_stories) ? pack.star_stories : [];
      const fullText = buildApplicationText(pack);
      return `
        <h3>投递准备</h3>
        <div class="pack">
          <div class="copyActions">
            <button class="secondary" onclick='copyText(${JSON.stringify(pack.cover_letter || "")}, "求职信已复制")'>复制求职信</button>
            <button class="secondary" onclick='copyText(${JSON.stringify(fullText)}, "投递材料已复制")'>复制全部</button>
          </div>
          <strong>简历优化点</strong>
          ${renderList(pack.resume_tips || [], "暂无")}
          <h3>求职信草稿</h3>
          <p>${escapeHtml(pack.cover_letter || "暂无")}</p>
          <h3>申请表回答</h3>
          ${answers.map(item => `
            <div class="qa">
              <strong>${escapeHtml(item.question || "问题")}</strong>
              <span>${escapeHtml(item.answer || "")}</span>
            </div>
          `).join("") || "<p class='meta'>暂无</p>"}
          <h3>STAR故事</h3>
          ${stories.map(item => `
            <div class="qa">
              <strong>${escapeHtml(item.title || "STAR故事")}</strong>
              <div class="meta">S：${escapeHtml(item.situation || "")}</div>
              <div class="meta">T：${escapeHtml(item.task || "")}</div>
              <div class="meta">A：${escapeHtml(item.action || "")}</div>
              <div class="meta">R：${escapeHtml(item.result || "")}</div>
              <div class="meta">复盘：${escapeHtml(item.reflection || "")}</div>
            </div>
          `).join("") || "<p class='meta'>暂无</p>"}
          <h3>人工投递清单</h3>
          ${renderList(pack.manual_checklist || [], "暂无")}
        </div>
      `;
    }

    function buildApplicationText(pack) {
      const lines = [];
      lines.push("【求职信】");
      lines.push(pack.cover_letter || "");
      lines.push("");
      lines.push("【简历优化点】");
      (pack.resume_tips || []).forEach(item => lines.push(`- ${item}`));
      lines.push("");
      lines.push("【申请表回答】");
      (pack.form_answers || []).forEach(item => {
        lines.push(`Q: ${item.question || ""}`);
        lines.push(`A: ${item.answer || ""}`);
      });
      lines.push("");
      lines.push("【STAR故事】");
      (pack.star_stories || []).forEach(item => {
        lines.push(item.title || "STAR故事");
        lines.push(`S: ${item.situation || ""}`);
        lines.push(`T: ${item.task || ""}`);
        lines.push(`A: ${item.action || ""}`);
        lines.push(`R: ${item.result || ""}`);
        lines.push(`复盘: ${item.reflection || ""}`);
      });
      return lines.join("\\n");
    }

    function renderFilters() {
      const rec = document.querySelector("#rec");
      const current = rec.value;
      const values = [...new Set(state.jobs.map(job => job.recommendation).filter(Boolean))];
      rec.innerHTML = '<option value="">全部建议</option>' +
        values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      rec.value = current;
    }

    function render() {
      const list = filteredJobs();
      if (state.selected >= state.jobs.length) state.selected = 0;
      renderStats(list);
      renderTable(list);
    }

    function currentJob() {
      return state.jobs[state.selected] || null;
    }

    function setStatus(title, text) {
      document.querySelector("#statusTitle").textContent = title || "就绪";
      document.querySelector("#statusText").textContent = text || "";
    }

    function renderLogs(logs) {
      const box = document.querySelector("#logs");
      box.innerHTML = logs.slice().reverse().map(line => `<div>${escapeHtml(line)}</div>`).join("");
    }

    document.querySelector("#searchBtn").addEventListener("click", startSearch);
    document.querySelector("#searchInput").addEventListener("keydown", event => {
      if (event.key === "Enter") startSearch();
    });
    document.querySelector("#toggleLogs").addEventListener("click", () => {
      state.logsOpen = !state.logsOpen;
      document.querySelector("#logs").style.display = state.logsOpen ? "block" : "none";
    });
    document.querySelector("#q").addEventListener("input", render);
    document.querySelector("#rec").addEventListener("change", render);
    document.querySelector("#score").addEventListener("change", render);

    loadJobs();
    pollStatus();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
