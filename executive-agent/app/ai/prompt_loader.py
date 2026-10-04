"""Load prompt files from disk so prompt text never lives in Python."""

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Read a prompt file by stem.

    Args:
        name: File stem such as classify_email.

    Returns:
        Prompt text without a trailing newline.
    """
    for suffix in (".md", ".txt"):
        path = PROMPT_DIR / f"{name}{suffix}"
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Prompt file not found: {name}")
