"""
LLM provider abstraction (phase brief §8).

CRITICAL PROPERTIES
  * The platform NEVER requires an external LLM. `DeterministicProvider` is
    the default and is fully functional on its own.
  * The LLM never receives database access and never generates SQL. It only
    (a) optionally re-words an already-fact-checked deterministic answer and
    (b) optionally picks one of the fixed `TOOL_SPECS` tools. The backend
    validates every parameter and runs the query itself.
  * Any LLM error -> transparent fallback to the deterministic result.
"""
from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger("sentinel.ai.llm")


class LLMProvider:
    name = "base"
    available = False

    def narrate(self, query: str, facts: dict, deterministic_answer: str) -> str:
        return deterministic_answer

    def choose_tool(self, query: str, tool_specs: list[dict]) -> dict | None:
        return None


class DeterministicProvider(LLMProvider):
    """No external calls. The Copilot's deterministic parser + templated
    answers are the whole intelligence here -- honest and reproducible."""

    name = "deterministic"
    available = True


class OpenAIProvider(LLMProvider):
    """Optional. Rewords the deterministic answer for readability and can
    pick a tool. It is handed ONLY the structured facts the backend already
    computed -- it cannot query anything itself."""

    name = "openai"

    def __init__(self):
        self.available = bool(settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL
        self._base = settings.OPENAI_BASE_URL.rstrip("/")
        self._key = settings.OPENAI_API_KEY

    def _chat(self, system: str, user: str, *, max_tokens: int = 400) -> str | None:
        if not self.available:
            return None
        try:
            import httpx  # available via fastapi/starlette test stack

            r = httpx.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.1,
                    "max_tokens": max_tokens,
                },
                timeout=settings.OPENAI_TIMEOUT_S,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:  # noqa: BLE001 -- never break the request over the LLM
            logger.warning("OpenAI call failed; using deterministic output", exc_info=True)
            return None

    def narrate(self, query: str, facts: dict, deterministic_answer: str) -> str:
        out = self._chat(
            system=(
                "You are a police CCTV investigation assistant. You will be given a "
                "question and a set of VERIFIED FACTS extracted from the Sentinel "
                "database, plus a draft answer. Rewrite the draft answer to be clear "
                "and concise. You MUST NOT add, infer or invent any fact, number, "
                "camera, time or location that is not in the FACTS. If the facts say "
                "something is unavailable, keep it that way. Two short sentences max."
            ),
            user=f"QUESTION: {query}\n\nFACTS:\n{json.dumps(facts, default=str)[:3000]}\n\n"
                 f"DRAFT ANSWER: {deterministic_answer}",
        )
        return out or deterministic_answer

    def choose_tool(self, query: str, tool_specs: list[dict]) -> dict | None:
        out = self._chat(
            system=(
                "Pick exactly ONE tool to answer the question and give its parameters "
                "as JSON. Respond ONLY with a JSON object: "
                '{"tool": "<name>", "params": {...}}. No prose.'
            ),
            user=f"TOOLS:\n{json.dumps(tool_specs)}\n\nQUESTION: {query}",
            max_tokens=200,
        )
        if not out:
            return None
        try:
            obj = json.loads(out[out.index("{"): out.rindex("}") + 1])
            if isinstance(obj, dict) and obj.get("tool"):
                return {"tool": str(obj["tool"]), "params": obj.get("params") or {}}
        except Exception:  # noqa: BLE001
            pass
        return None


_CACHED: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _CACHED
    if _CACHED is not None:
        return _CACHED
    if settings.AI_LLM_PROVIDER.strip().lower() == "openai":
        p = OpenAIProvider()
        _CACHED = p if p.available else DeterministicProvider()
    else:
        _CACHED = DeterministicProvider()
    return _CACHED


def reset_llm_provider_cache() -> None:
    """Tests flip settings then need a fresh provider."""
    global _CACHED
    _CACHED = None
