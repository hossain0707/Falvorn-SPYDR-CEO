"""OpenAI-compatible LLM interface; provider config comes only from server environment."""
from __future__ import annotations
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from .config import Config

class ModelError(Exception):
    pass

@dataclass(frozen=True)
class ModelReply:
    content: str
    input_tokens: int
    output_tokens: int

class ModelClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def configured(self) -> bool:
        return bool(self.cfg.api_key.strip())

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> ModelReply:
        if not self.configured():
            raise ModelError("Configure AI_API_KEY on the server to use a real AI model")
        base = urllib.parse.urlparse(self.cfg.model_base_url)
        if base.scheme not in {"https", "http"} or not base.hostname or base.username or base.password:
            raise ModelError("Invalid AI_BASE_URL")
        if base.scheme == "http" and base.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ModelError("AI_BASE_URL must use HTTPS except for loopback-based providers")
        payload = json.dumps({
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": max_tokens or self.cfg.max_completion_tokens,
        }).encode()
        req = urllib.request.Request(self.cfg.model_base_url + "/chat/completions", data=payload, method="POST", headers={
            "Authorization": "Bearer " + self.cfg.api_key,
            "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout) as response:
                data = json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as exc:
            raise ModelError(f"Provider HTTP {exc.code}; check model, API key, and quota") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelError("Model provider connection timed out or failed") from exc
        except (ValueError, KeyError) as exc:
            raise ModelError("Provider returned invalid JSON") from exc
        try:
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty content")
            return ModelReply(content, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            raise ModelError("Provider response lacked valid text content") from exc


def parse_json_object(text: str) -> dict:
    """Handle providers wrapping JSON in fenced Markdown, but reject trailing prose."""
    content = text.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[-1].strip() != "```":
            raise ModelError("Planner returned an unfinished JSON fence")
        content = "\n".join(lines[1:-1])
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ModelError("Planner response was not valid JSON; retry planning") from exc
    if not isinstance(result, dict):
        raise ModelError("Planner must return a JSON object")
    return result

ROLES = ("CEO", "Engineering", "Research", "Marketing", "Design", "Quality", "Operations")

# A conservative presentation flag. This does not grant or deny tool permissions:
# all external side effects are disabled regardless of risk score.
HIGH_RISK_TERMS = ("pay invoice", "transfer funds", "delete customer", "delete database", "publish publicly", "send email", "launch production", "deploy production", "personal health data", "legal advice", "credentials", "password reset")
MEDIUM_RISK_TERMS = ("finance", "security", "customer data", "production", "public relations", "privacy", "marketing campaign", "user tracking")

def classify_risk(description: str, stated: str) -> str:
    value = description.casefold()
    ranking = {"low": 0, "medium": 1, "high": 2}
    base = ranking.get(stated, -1)
    if base < 0:
        raise ModelError("Invalid task risk")
    derived = 2 if any(term in value for term in HIGH_RISK_TERMS) else 1 if any(term in value for term in MEDIUM_RISK_TERMS) else 0
    return ("low", "medium", "high")[max(base, derived)]

ROLE_PROMPTS = {
    "CEO": "You are the executive strategist. Break goals into independently verifiable outcomes, be concise, and flag uncertainty.",
    "Engineering": "You are a senior software engineer. Produce actionable technical designs, safe code snippets, tests and acceptance criteria. Never claim deployment without tools.",
    "Research": "You are an evidence-led researcher. State assumptions, distinguish evidence from hypotheses, and identify validation steps.",
    "Marketing": "You are a marketing strategist. Produce ethical, audience-specific messaging with measurable experiments; avoid invented market facts.",
    "Design": "You are a product designer. Deliver usable flows, accessibility requirements, design rationale and implementation-ready specs.",
    "Quality": "You are a QA and security analyst. Produce verifiable acceptance tests, edge cases, defects and recommended remediation.",
    "Operations": "You are an operations manager. Produce checklists, runbooks, dependencies, costs and rollback procedures.",
}

PLAN_SYSTEM = """You are a CEO agent that prepares a goal execution plan for a human-controlled company.
Return ONLY a JSON object with keys overview (string), tasks (array of 3 to 6 objects).
Each task must have title (max 100 chars), description (20-1300 chars), role (exactly one of CEO, Engineering, Research, Marketing, Design, Quality, Operations), risk (low|medium|high), estimated_usd (number from 0.001 to 1.0).
Tasks must be deliverables the agents can complete as TEXT artifacts, not claims of taking external actions.
An operator will review your plan before any task is started. Prefer specific acceptance criteria, minimal costs and measurable results.
Do not output Markdown fences."""


def validate_plan(plan: dict) -> dict:
    overview = plan.get("overview")
    tasks = plan.get("tasks")
    if not isinstance(overview, str) or not (10 <= len(overview) <= 2000):
        raise ModelError("Plan overview must be 10–2000 characters")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 10:
        raise ModelError("Plan needs 1–10 tasks")
    clean = []
    for item in tasks:
        if not isinstance(item, dict):
            raise ModelError("Each task must be an object")
        title, desc, role, risk = (item.get(k) for k in ("title", "description", "role", "risk"))
        try:
            estimate = float(item.get("estimated_usd", 0.01))
        except (ValueError, TypeError):
            raise ModelError("Invalid cost estimate")
        if not isinstance(title, str) or not 3 <= len(title.strip()) <= 100:
            raise ModelError("Invalid task title")
        if not isinstance(desc, str) or not 10 <= len(desc.strip()) <= 1500:
            raise ModelError("Invalid task description")
        if role not in ROLES or risk not in ("low", "medium", "high") or not .001 <= estimate <= 2.0:
            raise ModelError("Invalid task role, risk, or cost")
        clean.append({"title": title.strip(), "description": desc.strip(), "role": role, "risk": classify_risk(desc, risk), "estimated_usd": round(estimate, 4)})
    return {"overview": overview.strip(), "tasks": clean}
