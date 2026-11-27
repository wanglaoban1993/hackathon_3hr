"""Nebius Token Factory client. The API key is read from .env / environment only."""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"


def _get_api_key() -> str:
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key or key == "your_nebius_key_here":
        raise RuntimeError(
            "NEBIUS_API_KEY is not set. Copy .env.example to .env and paste your key "
            "(https://tokenfactory.nebius.com/project/api-keys)."
        )
    return key


def get_model() -> str:
    return os.environ.get("NEBIUS_MODEL", "").strip() or DEFAULT_MODEL


def get_client() -> OpenAI:
    return OpenAI(base_url=NEBIUS_BASE_URL, api_key=_get_api_key())


def mask(key: str) -> str:
    """Safe-to-print version of a key, e.g. 'eyJh...9fQ'."""
    return f"{key[:4]}...{key[-3:]}" if len(key) > 10 else "***"
