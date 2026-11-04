"""Approval-first control plane API, served without third-party runtime dependencies."""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from .config import Config
from .db import audit, connect, init, new_id, now, row, rows, transaction, verify_chain
from .model import ModelClient, ModelError, PLAN_SYSTEM, ROLE_PROMPTS, ROLES, parse_json_object, validate_plan
from .security import new_session, password_hash, revoke_session, session_user, verify_password

log = logging.getLogger("agentcompany")
WEB = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 65536
RATE_LIMIT = 8
RATE_WINDOW = 15 * 60

class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def cost(cfg: Config, input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens * cfg.price_input_million + output_tokens * cfg.price_output_million) / 1_000_000, 8)


def company_spend(con, company_id: str) -> float:
    month = datetime.now(timezone.utc).strftime("%Y-%m-01")
    result = con.execute("""SELECT COALESCE(SUM(r.cost_usd),0) total FROM runs r
      LEFT JOIN tasks t ON r.task_id=t.id
      LEFT JOIN agents a ON r.agent_id=a.id
      WHERE r.created_at>=? AND (t.company_id=? OR (r.task_id IS NULL AND a.company_id=?))
      AND r.status='completed'""", (month, company_id, company_id)).fetchone()
    return round(float(result["total"]), 8)


def fail(status, message):
    raise APIError(status, message)


def clean_text(value, field, minimum=1, maximum=500):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        fail(400, f"{field} must have {minimum}–{maximum} characters")
    return value.strip()


def default_agents(con, company_id):
    for role, prompt in ROLE_PROMPTS.items():
        con.execute("INSERT INTO agents(id,company_id,name,role,instructions,created_at) VALUES(?,?,?,?,?,?)", (
            new_id("agt"), company_id, "CEO" if role == "CEO" else role + " Agent", role, prompt, now()))


class CompanyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, addr, handler, cfg: Config, model: ModelClient | None = None):
        self.cfg = cfg
        self.model = model or ModelClient(cfg)
        self.rate: dict[str, list[float]] = {}
        self.rate_lock = threading.Lock()
        init(cfg.database)
        super().__init__(addr, handler)


class Handler(BaseHTTPRequestHandler):
    server: CompanyHTTPServer
    server_version = "AgentCompany/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        log.info("%s %s", self.client_address[0], fmt % args)

    def headers_common(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if self.server.cfg.https:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def respond(self, status=200, data: Any = None, cookies: str | None = None):
        blob = json.dumps(data if data is not None else {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.headers_common()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        if cookies:
            self.send_header("Set-Cookie", cookies)
        self.end_headers()
        self.wfile.write(blob)

    def send_static(self, name: str, mime: str):
        f = WEB / name
        try:
            b = f.read_bytes()
        except OSError:
            return self.respond(404, {"error": "Resource not found"})
        self.send_response(200)
        self.headers_common()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def parsed_path(self):
        return urllib.parse.urlsplit(self.path).path

    def cookie_value(self):
        try:
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            return cookies["ac_session"].value if "ac_session" in cookies else ""
        except Exception:
            return ""

    def session(self):
        con = connect(self.server.cfg.database)
        try:
            return session_user(con, self.cookie_value())
        finally:
            con.close()

    def require_session(self, mutation=False):
        user = self.session()
        if not user:
            fail(401, "Sign in to continue")
        if mutation and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), user["csrf"]):
            fail(403, "Invalid CSRF token; refresh and sign in again")
        return user

    def body(self):
        raw_size = self.headers.get("Content-Length", "0")
        if not raw_size.isdecimal():
            fail(411, "Content-Length required")
        length = int(raw_size)
        if length > MAX_BODY:
            fail(413, "Request too large")
        if length == 0:
            return {}
        if "application/json" not in self.headers.get("Content-Type", ""):
            fail(415, "JSON Content-Type required")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            fail(400, "Invalid JSON")
        if not isinstance(payload, dict):
            fail(400, "Expected JSON object")
        return payload

    def cookie_header(self, token: str, expire=False):
        secure = "; Secure" if self.server.cfg.https else ""
        if expire:
            return f"ac_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0{secure}"
        return f"ac_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800{secure}"

    def rate_limit(self):
        addr = self.client_address[0]
        current = time.monotonic()
        with self.server.rate_lock:
            recent = [t for t in self.server.rate.get(addr, []) if current - t < RATE_WINDOW]
            if len(recent) >= RATE_LIMIT:
                fail(429, "Too many login attempts; try again later")
            recent.append(current)
            self.server.rate[addr] = recent

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def dispatch(self, method):
        try:
            path = self.parsed_path()
            if method == "GET" and path in ("/", "/index.html"):
                return self.send_static("index.html", "text/html; charset=utf-8")
            if method == "GET" and path == "/app.js":
                return self.send_static("app.js", "text/javascript; charset=utf-8")
            if method == "GET" and path == "/styles.css":
                return self.send_static("styles.css", "text/css; charset=utf-8")
            if method == "GET" and path == "/favicon.svg":
                return self.send_static("favicon.svg", "image/svg+xml")
            if path in ("/health", "/healthz") and method == "GET":
                return self.respond(200, {"status": "ok", "service": "falvorn-spydr-ceo"})
            if path == "/api/session" and method == "GET":
                con = connect(self.server.cfg.database)
                try:
                    configured = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"] > 0
                finally:
                    con.close()
                return self.respond(200, {"setup_required": not configured, "user": self.session(), "model_ready": self.server.model.configured()})
            if path == "/api/setup" and method == "POST":
                return self.setup_workspace(self.body())
            if path == "/api/login" and method == "POST":
                return self.login(self.body())
            if path == "/api/logout" and method == "POST":
                self.require_session(True)
                with transaction(self.server.cfg.database) as con:
                    revoke_session(con, self.cookie_value())
                return self.respond(200, {"ok": True}, cookies=self.cookie_header("", expire=True))
            self.require_session(method != "GET")
            if path == "/api/state" and method == "GET":
                return self.get_state()
            if path == "/api/company" and method == "PATCH":
                return self.update_company(self.body())
            if path == "/api/goals" and method == "POST":
                return self.create_goal(self.body())
            match = re.fullmatch(r"/api/goals/(gol_[a-f0-9]{16})/(plan|manual-plan)", path)
            if method == "POST" and match:
                return self.plan_goal(match.group(1), match.group(2), self.body())
            match = re.fullmatch(r"/api/approvals/(apr_[a-f0-9]{16})/decision", path)
            if method == "POST" and match:
                return self.decide(match.group(1), self.body())
            match = re.fullmatch(r"/api/tasks/(tsk_[a-f0-9]{16})/run", path)
            if method == "POST" and match:
                return self.execute_task(match.group(1))
            if path == "/api/audit/verify" and method == "GET":
                ok, count = verify_chain(self.server.cfg.database)
                return self.respond(200 if ok else 409, {"valid": ok, "entries_checked": count})
            return self.respond(404, {"error": "Endpoint not found"})
        except APIError as exc:
            return self.respond(exc.status, {"error": exc.message})
        except ModelError as exc:
            return self.respond(422, {"error": str(exc)})
        except sqlite3.IntegrityError:
            return self.respond(409, {"error": "Data conflict; refresh and retry"})
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception:
            log.exception("Unhandled server error")
            return self.respond(500, {"error": "Internal server error; check server logs"})

    def setup_workspace(self, data):
        email = clean_text(data.get("email"), "Email", 5, 180).casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            fail(400, "Enter a valid email address")
        pwd = data.get("password", "")
        try:
            pwd_hash = password_hash(pwd)
        except (ValueError, TypeError):
            fail(400, "Password must have 12 to 256 characters")
        company_name = clean_text(data.get("company"), "Company name", 2, 100)
        with transaction(self.server.cfg.database) as con:
            if con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]:
                fail(409, "Setup already completed")
            uid, cid = new_id("usr"), new_id("cmp")
            con.execute("INSERT INTO users VALUES(?,?,?,?)", (uid, email, pwd_hash, now()))
            con.execute("INSERT INTO companies VALUES(?,?,?,?)", (cid, company_name, self.server.cfg.monthly_budget_usd, now()))
            default_agents(con, cid)
            token, csrf = new_session(con, uid)
            audit(con, uid, "company.created", cid, {"company": company_name})
        return self.respond(201, {"ok": True, "csrf": csrf}, cookies=self.cookie_header(token))

    def login(self, data):
        self.rate_limit()
        email = str(data.get("email", "")).strip().casefold()
        pwd = data.get("password", "")
        if not isinstance(pwd, str):
            fail(400, "Invalid password")
        with transaction(self.server.cfg.database) as con:
            user = row(con, "SELECT * FROM users WHERE email=?", (email,))
            if not user or not verify_password(pwd, user["password_hash"]):
                fail(401, "Invalid email or password")
            token, csrf = new_session(con, user["id"])
            audit(con, user["id"], "auth.signed_in", user["id"])
        return self.respond(200, {"ok": True, "csrf": csrf}, cookies=self.cookie_header(token))

    def first_company(self, con):
        company = row(con, "SELECT * FROM companies ORDER BY created_at LIMIT 1")
        if not company:
            fail(404, "Company not found")
        return company

    def get_state(self):
        con = connect(self.server.cfg.database)
        try:
            company = self.first_company(con)
            company["spent_usd"] = company_spend(con, company["id"])
            result = {
                "company": company,
                "agents": rows(con, "SELECT id,name,role,enabled FROM agents WHERE company_id=? ORDER BY rowid", (company["id"],)),
                "goals": rows(con, "SELECT * FROM goals WHERE company_id=? ORDER BY created_at DESC LIMIT 150", (company["id"],)),
                "tasks": rows(con, """SELECT t.*,a.name agent_name,a.role agent_role FROM tasks t LEFT JOIN agents a ON a.id=t.agent_id
                  WHERE t.company_id=? ORDER BY t.created_at DESC LIMIT 300""", (company["id"],)),
                "approvals": rows(con, "SELECT * FROM approvals WHERE company_id=? ORDER BY created_at DESC LIMIT 100", (company["id"],)),
                "runs": rows(con, """SELECT r.*,t.title task_title,a.name agent_name FROM runs r
                  LEFT JOIN tasks t ON r.task_id=t.id LEFT JOIN agents a ON r.agent_id=a.id
                  WHERE t.company_id=? OR (r.task_id IS NULL AND a.company_id=?)
                  ORDER BY r.created_at DESC LIMIT 150""", (company["id"], company["id"])),
                "audit": rows(con, "SELECT id,at,actor,event,entity_id,entry_hash FROM audit ORDER BY id DESC LIMIT 60"),
                "model": {"ready": self.server.model.configured(), "name": self.server.cfg.model},
                "features": {"external_actions": False, "text_deliverables": True, "manual_plan": True},
            }
            return self.respond(200, result)
        finally:
            con.close()

    def update_company(self, data):
        try:
            budget = float(data.get("monthly_budget_usd"))
        except (ValueError, TypeError):
            fail(400, "A numeric monthly budget is required")
        if not 0.01 <= budget <= 100000:
            fail(400, "Budget must be between $0.01 and $100,000")
        with transaction(self.server.cfg.database) as con:
            company = self.first_company(con)
            if budget < company_spend(con, company["id"]):
                fail(409, "Cannot set a budget below this month's recorded spend")
            con.execute("UPDATE companies SET monthly_budget_usd=? WHERE id=?", (budget, company["id"]))
            audit(con, self.session()["id"], "company.budget_changed", company["id"], {"monthly_budget_usd": budget})
        return self.respond(200, {"ok": True})

    def create_goal(self, data):
        title = clean_text(data.get("title"), "Goal title", 4, 140)
        description = clean_text(data.get("description"), "Goal description", 10, 2500)
        gid = new_id("gol")
        with transaction(self.server.cfg.database) as con:
            company = self.first_company(con)
            con.execute("INSERT INTO goals VALUES(?,?,?,?,?,?,?)", (gid, company["id"], title, description, "draft", now(), now()))
            audit(con, self.session()["id"], "goal.created", gid, {"title": title})
        return self.respond(201, {"id": gid})

    def plan_goal(self, goal_id, mode, data):
        con = connect(self.server.cfg.database)
        try:
            goal = row(con, "SELECT * FROM goals WHERE id=?", (goal_id,))
            if not goal:
                fail(404, "Goal not found")
            if goal["status"] not in ("draft", "rejected"):
                fail(409, "Goal is already planned or running")
            company = self.first_company(con)
            if mode == "plan" and company_spend(con, company["id"]) + .02 > company["monthly_budget_usd"]:
                fail(409, "Monthly budget too low for a planning request")
            ceo = row(con, "SELECT id FROM agents WHERE company_id=? AND role='CEO'", (company["id"],))
        finally:
            con.close()
        if mode == "plan":
            reply = self.server.model.complete(PLAN_SYSTEM, f"GOAL: {goal['title']}\nDETAILS: {goal['description']}", max_tokens=1500)
            plan = validate_plan(parse_json_object(reply.content))
        else:
            plan = validate_plan(data)
            reply = None
        approval_id = new_id("apr")
        with transaction(self.server.cfg.database) as con:
            current = row(con, "SELECT status FROM goals WHERE id=?", (goal_id,))
            if not current or current["status"] not in ("draft", "rejected"):
                fail(409, "Goal changed while planning; reload")
            con.execute("UPDATE goals SET status='approval',updated_at=? WHERE id=?", (now(), goal_id))
            con.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?)", (
                approval_id, goal["company_id"], goal_id, "strategy", plan["overview"],
                json.dumps(plan, ensure_ascii=False), "pending", None, now()))
            if reply:
                inp = reply.input_tokens or max(1, len(goal["description"]) // 4)
                out = reply.output_tokens or max(1, len(reply.content) // 4)
                con.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)", (new_id("run"), None, ceo["id"],
                    self.server.cfg.model, inp, out, cost(self.server.cfg, inp, out), "completed", None, now()))
            audit(con, self.session()["id"], "plan.submitted", approval_id, {"goal_id": goal_id, "task_count": len(plan["tasks"]), "mode": mode})
        return self.respond(201, {"approval_id": approval_id, "plan": plan})

    def decide(self, approval_id, data):
        choice = data.get("decision")
        if choice not in ("approved", "rejected"):
            fail(400, "Decision must be approved or rejected")
        with transaction(self.server.cfg.database) as con:
            approval = row(con, "SELECT * FROM approvals WHERE id=?", (approval_id,))
            if not approval:
                fail(404, "Approval not found")
            if approval["status"] != "pending":
                fail(409, "Decision already recorded")
            goal = row(con, "SELECT * FROM goals WHERE id=?", (approval["goal_id"],))
            if not goal or goal["status"] != "approval":
                fail(409, "Goal is not awaiting approval")
            con.execute("UPDATE approvals SET status=?,decided_at=? WHERE id=?", (choice, now(), approval_id))
            con.execute("UPDATE goals SET status=?,updated_at=? WHERE id=?", (
                "active" if choice == "approved" else "rejected", now(), goal["id"]))
            if choice == "approved":
                plan = json.loads(approval["payload"])
                agents = {r["role"]: r["id"] for r in rows(con, "SELECT id,role FROM agents WHERE company_id=? AND enabled=1", (goal["company_id"],))}
                for item in plan["tasks"]:
                    if item["role"] not in agents:
                        fail(409, "Plan requires a disabled or missing agent")
                    con.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                        new_id("tsk"), goal["id"], goal["company_id"], agents[item["role"]],
                        item["title"], item["description"], item["risk"], "queued",
                        item["estimated_usd"], None, None, now(), now()))
            audit(con, self.session()["id"], f"approval.{choice}", approval_id, {"goal_id": goal["id"]})
        return self.respond(200, {"ok": True})

    def execute_task(self, task_id):
        if not self.server.model.configured():
            fail(422, "Configure AI_API_KEY to execute a task using a real model")
        with transaction(self.server.cfg.database) as con:
            task = row(con, """SELECT t.*,a.role,a.instructions,a.enabled,g.title goal_title,g.description goal_desc
              FROM tasks t JOIN agents a ON a.id=t.agent_id JOIN goals g ON g.id=t.goal_id
              WHERE t.id=?""", (task_id,))
            if not task:
                fail(404, "Task not found")
            if task["status"] not in ("queued", "error"):
                fail(409, "Task is not ready to execute")
            if not task["enabled"]:
                fail(409, "Agent is disabled")
            company = row(con, "SELECT * FROM companies WHERE id=?", (task["company_id"],))
            spent = company_spend(con, company["id"])
            # Reserve estimates for concurrent in-flight requests, too.
            reserved = con.execute("SELECT COALESCE(SUM(estimated_cost_usd),0) n FROM tasks WHERE company_id=? AND status='running'", (company["id"],)).fetchone()["n"]
            if spent + reserved + task["estimated_cost_usd"] > company["monthly_budget_usd"]:
                fail(409, "Estimated task cost exceeds remaining monthly budget")
            if con.execute("SELECT COUNT(*) n FROM tasks WHERE company_id=? AND status='running'", (company["id"],)).fetchone()["n"] >= 3:
                fail(409, "Maximum 3 concurrent tasks per company")
            con.execute("UPDATE tasks SET status='running',error=NULL,updated_at=? WHERE id=?", (now(), task_id))
            audit(con, self.session()["id"], "task.started", task_id, {"agent": task["role"]})
        try:
            prompt = (f"COMPANY GOAL: {task['goal_title']}\nCONTEXT: {task['goal_desc']}\n"
                      f"ASSIGNED DELIVERABLE: {task['title']}\nSPECIFICATION: {task['description']}\n"
                      "Return the actual deliverable as well-structured text/Markdown. "
                      "Distinguish completed text from proposed external actions; do not claim to have executed external work. "
                      "Avoid placeholder sections and invented citations. Include validation steps.")
            result = self.server.model.complete(task["instructions"] + "\nDo not reveal secrets.", prompt)
            inp = result.input_tokens or max(1, len(prompt) // 4)
            out = result.output_tokens or max(1, len(result.content) // 4)
            usd = cost(self.server.cfg, inp, out)
            with transaction(self.server.cfg.database) as con:
                con.execute("UPDATE tasks SET status='completed',output=?,error=NULL,updated_at=? WHERE id=?", (result.content, now(), task_id))
                con.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)", (new_id("run"), task_id, task["agent_id"],
                    self.server.cfg.model, inp, out, usd, "completed", None, now()))
                audit(con, "agent:" + task["agent_id"], "task.completed", task_id, {"cost_usd": usd})
                remaining = con.execute("SELECT COUNT(*) n FROM tasks WHERE goal_id=? AND status!='completed'", (task["goal_id"],)).fetchone()["n"]
                if remaining == 0:
                    con.execute("UPDATE goals SET status='completed',updated_at=? WHERE id=?", (now(), task["goal_id"]))
                    audit(con, "system", "goal.completed", task["goal_id"])
            return self.respond(200, {"ok": True, "output": result.content, "cost_usd": usd})
        except Exception as exc:
            msg = str(exc) if isinstance(exc, ModelError) else "Agent execution failed; inspect server logs"
            with transaction(self.server.cfg.database) as con:
                con.execute("UPDATE tasks SET status='error',error=?,updated_at=? WHERE id=?", (msg, now(), task_id))
                con.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)", (new_id("run"), task_id,
                    task["agent_id"], self.server.cfg.model, 0, 0, 0.0, "error", msg, now()))
                audit(con, "system", "task.failed", task_id, {"category": type(exc).__name__})
            if isinstance(exc, ModelError):
                fail(422, msg)
            raise


def serve(cfg: Config | None = None, model=None):
    cfg = cfg or Config()
    if cfg.host not in ("127.0.0.1", "localhost", "::1") and not cfg.https:
        log.warning("Binding to a non-loopback interface without APP_HTTPS=1. Put a TLS reverse proxy in front before public exposure.")
    server = CompanyHTTPServer((cfg.host, cfg.port), Handler, cfg, model=model)
    log.info("SPYDR by Falvorn AI is running at http://%s:%s", cfg.host, server.server_port)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
