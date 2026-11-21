"""
Centralized LLM client factory.

Uses Nia API (OpenAI-compatible) if NIA_API_KEY is set,
falls back to Groq API otherwise.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)


def get_llm_client(max_retries: int = 0):
    """Return an OpenAI-compatible client (Nia or Groq)."""
    nia_key = os.getenv("NIA_API_KEY")
    if nia_key:
        from openai import OpenAI
        return OpenAI(
            api_key=nia_key,
            base_url=os.getenv("NIA_BASE_URL", "https://api.nia.naslabs.ai/v1"),
            max_retries=max_retries,
        )
    # Fallback to Groq
    from groq import Groq
    return Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=max_retries)
