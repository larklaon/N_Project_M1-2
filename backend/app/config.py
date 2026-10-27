"""All secrets stay on the server; production never silently falls back to demo."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    demo: bool = False
    gemini_key: str = ""
    model: str = "gemini-3.8-flash"
    firebase_json: str = ""
    firebase_path: str = ""
    origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    max_output_tokens: int = 800
    chat_per_minute: int = 5
    chat_per_day: int = 100
    local_path: Path = ROOT / ".local" / "demo.json"

    @classmethod
    def from_env(cls):
        return cls(
            demo=os.getenv("DEMO_MODE", "false").lower() == "true",
            gemini_key=os.getenv("GEMINI_API_KEY", ""),
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            firebase_json=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", ""),
            firebase_path=os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", ""),
            origins=tuple(x.strip().rstrip("/") for x in os.getenv(
                "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",") if x.strip()),
            max_output_tokens=max(64, min(2000, int(os.getenv("MAX_OUTPUT_TOKENS", "800")))),
            chat_per_minute=max(1, int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "5"))),
            chat_per_day=max(1, int(os.getenv("CHAT_REQUESTS_PER_DAY", "100"))),
            local_path=Path(os.getenv("DEMO_DATABASE_PATH", str(ROOT / ".local" / "demo.json"))),
        )
