# LLM client — single selected provider, no fallback chain
import time
import re
import random
import requests
from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError
from groq import Groq
from groq import APIStatusError as GroqAPIStatusError
from config.config import (
    GROQ_API_KEY,
    HF_API_TOKEN,
    OLLAMA_BASE_URL,
)
from logger import get_logger

logger = get_logger("test_automation.mistral_client")

_MAX_RETRIES = 8
_BASE_DELAY = 2

# ── HF errors that are non-recoverable ───────────────────────────────────────
_HF_FATAL_CODES = {402, 401, 403}


def _parse_retry_delay(exc) -> float | None:
    match = re.search(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", str(exc))
    if match:
        return float(match.group(1)) + random.uniform(1, 3)
    return None


def _wait(attempt: int, reason: str, exc=None) -> None:
    api_delay = _parse_retry_delay(exc) if exc else None
    delay = (
        api_delay
        if api_delay is not None
        else (_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1))
    )
    source = "API-specified" if api_delay is not None else "backoff"
    logger.warning(f"[RETRY] {reason} — attempt {attempt}/{_MAX_RETRIES}, retrying in {delay:.1f}s ({source})")
    time.sleep(delay)


# ── HuggingFace ────────────────────────────────────────────────────────────────

def _hf_generate(client: InferenceClient, prompt: str) -> str:
    """Call the HuggingFace Inference API with retry for transient errors."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            print("   [LLM] Using HuggingFace...")
            response = client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            if attempt > 1:
                logger.info(f"[RETRY] Success after retry attempt {attempt} (HuggingFace)")
            return content.strip() if content else ""

        except HfHubHTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", 0)

            if status_code in _HF_FATAL_CODES:
                # Non-recoverable billing/auth error — escalate immediately.
                raise

            if status_code == 429 or "too many requests" in str(exc).lower():
                if attempt == _MAX_RETRIES:
                    logger.error("[LLM ERROR] Rate limit reached on HuggingFace — max retries exhausted")
                    raise
                _wait(attempt, "HF rate limited (429)")
            elif status_code >= 500:
                if attempt == _MAX_RETRIES:
                    raise
                _wait(attempt, f"HF server error {status_code}")
            else:
                raise

    return ""


# ── Groq ──────────────────────────────────────────────────────────────────────

_GROQ_FATAL_CODES = {401, 403}


def _groq_generate(client: Groq, prompt: str, model: str) -> str:
    """Call the Groq Inference API with retry for transient errors."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            print(f"   [LLM] Using Groq ({model})...")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            if attempt > 1:
                logger.info(f"[RETRY] Success after retry attempt {attempt} (Groq)")
            return content.strip() if content else ""

        except GroqAPIStatusError as exc:
            status_code = exc.status_code
            if status_code in _GROQ_FATAL_CODES:
                raise
            if status_code == 429 or "rate limit" in str(exc).lower():
                if attempt == _MAX_RETRIES:
                    logger.error("[LLM ERROR] Rate limit reached on Groq — max retries exhausted")
                    raise
                _wait(attempt, f"Groq rate limited (429) (attempt {attempt})")
            elif status_code >= 500:
                if attempt == _MAX_RETRIES:
                    raise
                _wait(attempt, f"Groq server error {status_code} (attempt {attempt})")
            else:
                raise

    return ""


# ── Ollama ─────────────────────────────────────────────────────────────────────

def _ollama_generate(prompt: str, model: str) -> str:
    """Call a locally running Ollama instance."""
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    print(f"   [LLM] Using Ollama ({model})...")
    resp = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


# ── Available LLM options (shared with backend) ───────────────────────────────
LLM_OPTIONS = [
    {"label": "Ollama — llama3",                          "provider": "ollama",      "model": "llama3"},
    {"label": "Groq — llama-3.1-8b-instant",              "provider": "groq",        "model": "llama-3.1-8b-instant"},
    {"label": "Groq — llama-3.3-70b-versatile",           "provider": "groq",        "model": "llama-3.3-70b-versatile"},
    {"label": "Groq — llama-4-scout-17b-16e-instruct",    "provider": "groq",        "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    {"label": "HuggingFace — Llama-3.3-70B-Instruct",     "provider": "huggingface", "model": "meta-llama/Llama-3.3-70B-Instruct"},
]

# ── Main LLM class ─────────────────────────────────────────────────────────────

class MistralLLM:
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        self._groq_client: Groq | None = None
        self._hf_client: InferenceClient | None = None

        if provider == "groq":
            if not GROQ_API_KEY:
                raise RuntimeError("[LLM] GROQ_API_KEY is not set — cannot use Groq")
            self._groq_client = Groq(api_key=GROQ_API_KEY)
            print(f"   [LLM] Groq ready ({model})")
        elif provider == "huggingface":
            if not HF_API_TOKEN:
                raise RuntimeError("[LLM] HF_API_TOKEN is not set — cannot use HuggingFace")
            self._hf_client = InferenceClient(model=model, token=HF_API_TOKEN)
            print(f"   [LLM] HuggingFace ready ({model})")
        elif provider == "ollama":
            print(f"   [LLM] Ollama ready ({model})")
        else:
            raise ValueError(f"[LLM] Unknown provider: '{provider}'")

    def generate(self, prompt: str) -> str:
        if self.provider == "groq":
            return _groq_generate(self._groq_client, prompt, self.model)
        if self.provider == "huggingface":
            return _hf_generate(self._hf_client, prompt)
        if self.provider == "ollama":
            return _ollama_generate(prompt, self.model)
        raise RuntimeError(f"[LLM] Unknown provider: '{self.provider}'")
