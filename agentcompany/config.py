"""Explicit environment configuration. No model provider is contacted without an API key."""
from dataclasses import dataclass
import os
from pathlib import Path

@dataclass(frozen=True)
class Config:
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8787"))
    database: Path = Path(os.getenv("APP_DB", "./data/agentcompany.sqlite3")).resolve()
    https: bool = os.getenv("APP_HTTPS", "0") == "1"
    model_base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model: str = os.getenv("AI_MODEL", "gpt-4.1-mini")
    api_key: str = os.getenv("AI_API_KEY", "")
    price_input_million: float = float(os.getenv("AI_INPUT_PER_MILLION_USD", "0.40"))
    price_output_million: float = float(os.getenv("AI_OUTPUT_PER_MILLION_USD", "1.60"))
    monthly_budget_usd: float = float(os.getenv("DEFAULT_MONTHLY_BUDGET_USD", "10"))
    request_timeout: int = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))
    max_completion_tokens: int = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "1600"))
    app_origin: str = os.getenv("APP_ORIGIN", "")
