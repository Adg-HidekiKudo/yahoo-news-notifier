"""
設定読み込みとバリデーション

依存: pydantic

使い方:
from config import load_config
cfg = load_config("config.txt")
"""
from typing import List, Optional
import os

from pydantic import BaseModel, Field, validator, ValidationError


class AppConfig(BaseModel):
    DISCORD_WEBHOOK_URL: Optional[str]
    GEMINI_API_KEY: Optional[str] = None
    CATEGORY: List[str] = Field(default_factory=lambda: ["domestic"])
    KEYWORDS: List[str] = Field(default_factory=list)
    AI_SUMMARY_ENABLED: bool = True
    SEMANTIC_INTEREST: Optional[str] = None
    SEMANTIC_THRESHOLD: int = 80
    CHECK_INTERVAL: int = 60

    @validator("SEMANTIC_THRESHOLD")
    def check_threshold(cls, v):
        if v is None:
            return 80
        if not (0 <= v <= 100):
            raise ValueError("SEMANTIC_THRESHOLD must be between 0 and 100")
        return v

    @validator("CHECK_INTERVAL")
    def check_interval(cls, v):
        if v is None or v <= 0:
            raise ValueError("CHECK_INTERVAL must be positive seconds")
        return v


def _parse_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _read_config_file(path: str) -> dict:
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def load_config(path: str = "config.txt") -> AppConfig:
    raw = _read_config_file(path)
    # environment variables override file
    env = os.environ
    data = {}

    data["DISCORD_WEBHOOK_URL"] = raw.get("DISCORD_WEBHOOK_URL") or env.get("DISCORD_WEBHOOK_URL")
    data["GEMINI_API_KEY"] = raw.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY")

    category = raw.get("CATEGORY")
    parsed_categories = _parse_list(category) if category is not None else []
    data["CATEGORY"] = parsed_categories if parsed_categories else ["domestic"]

    keywords = raw.get("KEYWORDS")
    data["KEYWORDS"] = _parse_list(keywords) if keywords is not None else []

    ai_enabled = raw.get("AI_SUMMARY_ENABLED")
    if ai_enabled is None:
        data["AI_SUMMARY_ENABLED"] = True
    else:
        data["AI_SUMMARY_ENABLED"] = ai_enabled.lower() in ("true", "1", "yes", "on")

    data["SEMANTIC_INTEREST"] = raw.get("SEMANTIC_INTEREST")

    sem_thr = raw.get("SEMANTIC_THRESHOLD")
    try:
        data["SEMANTIC_THRESHOLD"] = int(sem_thr) if sem_thr is not None else 80
    except ValueError:
        data["SEMANTIC_THRESHOLD"] = 80

    check_int = raw.get("CHECK_INTERVAL")
    try:
        data["CHECK_INTERVAL"] = int(check_int) if check_int is not None else 60
    except ValueError:
        data["CHECK_INTERVAL"] = 60

    try:
        cfg = AppConfig(**data)
    except ValidationError as e:
        # re-raise with a clearer message
        raise RuntimeError(f"Invalid configuration: {e}")

    # If GEMINI API key present in env, prefer it
    if env.get("GEMINI_API_KEY"):
        cfg.GEMINI_API_KEY = env.get("GEMINI_API_KEY")

    return cfg


if __name__ == "__main__":
    try:
        cfg = load_config()
        print(cfg.json(indent=2, ensure_ascii=False))
    except Exception as e:
        print("Failed to load config:", e)
