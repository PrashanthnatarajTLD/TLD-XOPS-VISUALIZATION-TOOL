"""Agent for fast local AI chat using Ollama.

This module focuses on low-latency answers for basic telemetry questions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import json
import requests


@dataclass
class AIChatResult:
    success: bool
    answer: str
    latency_ms: int
    error: Optional[str] = None


def build_compact_context(
    *,
    plate_number: str,
    start_date: str,
    end_date: str,
    timezone_label: str,
    total_rows: int,
    columns: List[str],
    sample_rows: List[Dict[str, Any]],
) -> str:
    """Build compact context string to keep prompts fast and cheap."""
    payload = {
        "plate_number": plate_number,
        "period": f"{start_date} to {end_date}",
        "timezone": timezone_label,
        "total_rows": total_rows,
        "columns": columns[:30],
        "sample_rows": sample_rows[:12],
    }
    return json.dumps(payload, default=str, ensure_ascii=True)


def ask_ollama_fast(
    *,
    question: str,
    context_json: str,
    model: str = "qwen2.5:3b",
    host: str = "http://localhost:11434",
    timeout_seconds: int = 12,
    max_tokens: int = 140,
) -> AIChatResult:
    """Send a fast non-streaming request to local Ollama."""
    system_prompt = (
        "You are a concise EV telemetry assistant. "
        "Answer from provided context only. "
        "If data is insufficient, say that clearly in one line. "
        "Keep response under 6 bullet points and avoid long explanations."
    )

    user_prompt = (
        "Telemetry context JSON:\n"
        f"{context_json}\n\n"
        "User question:\n"
        f"{question}\n\n"
        "Output format:\n"
        "- Short answer\n"
        "- Up to 3 key observations\n"
        "- Optional next check"
    )

    req_payload = {
        "model": model,
        "prompt": f"{system_prompt}\n\n{user_prompt}",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": max_tokens,
        },
    }

    try:
        resp = requests.post(
            f"{host.rstrip('/')}/api/generate",
            json=req_payload,
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = (data.get("response") or "").strip()
        latency_ms = int(data.get("total_duration", 0) / 1_000_000)

        if not answer:
            return AIChatResult(
                success=False,
                answer="",
                latency_ms=latency_ms,
                error="No response returned by model.",
            )

        return AIChatResult(success=True, answer=answer, latency_ms=latency_ms)
    except requests.exceptions.RequestException as exc:
        return AIChatResult(
            success=False,
            answer="",
            latency_ms=0,
            error=(
                "Unable to reach Ollama. Ensure Ollama is running and model is pulled. "
                f"Details: {exc}"
            ),
        )
