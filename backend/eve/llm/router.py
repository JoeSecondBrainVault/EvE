"""Hybrid LLM Router: Gemini 2.5 Flash primary with local Ollama 7B fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from eve.config import Settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMRouter:
    """Dispatches intelligence queries to Gemini or local Ollama."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._gemini_client: Any = None
        self._init_gemini()

    def _init_gemini(self) -> None:
        api_key = self.settings.resolved_gemini_api_key
        if api_key:
            try:
                from google import genai

                self._gemini_client = genai.Client(api_key=api_key)
                log.info("Gemini client initialized with model %s", self.settings.gemini_model)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to initialize Gemini client: %s", exc)
                self._gemini_client = None
        else:
            self._gemini_client = None

    @property
    def has_cloud(self) -> bool:
        return self._gemini_client is not None

    def generate_structured(
        self,
        prompt: str,
        *,
        system_prompt: str,
        schema: type[T],
    ) -> tuple[T, str]:
        """Generate structured output adhering to a Pydantic schema.

        Returns (parsed_result, provider_name).
        """
        # 1. Try Gemini primary
        if self._gemini_client is not None:
            try:
                from google.genai import types

                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.2,
                )
                response = self._gemini_client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=config,
                )
                text = response.text or "{}"
                parsed = schema.model_validate_json(text)
                return (parsed, "gemini")
            except Exception as exc:  # noqa: BLE001
                log.warning("Gemini structured generation failed (%s); falling back to Ollama", exc)

        # 2. Try Ollama local fallback
        return (self._generate_ollama_structured(prompt, system_prompt, schema), "ollama")

    def _generate_ollama_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: type[T],
    ) -> T:
        """Call local Ollama HTTP daemon with JSON schema constraint."""
        json_schema = json.dumps(schema.model_json_schema())
        full_prompt = (
            f"{system_prompt}\n\n"
            f"You MUST respond ONLY with a valid JSON object matching this JSON Schema:\n{json_schema}\n\n"
            f"Input:\n{prompt}"
        )
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/generate"
        try:
            with httpx.Client(timeout=120.0) as client:
                res = client.post(
                    url,
                    json={
                        "model": self.settings.ollama_model,
                        "prompt": full_prompt,
                        "format": "json",
                        "stream": False,
                        "options": {"temperature": 0.2},
                    },
                )
                res.raise_for_status()
                data = res.json()
                raw_response = data.get("response", "{}")
                return schema.model_validate_json(raw_response)
        except Exception as exc:
            raise RuntimeError(
                f"Both Gemini and local Ollama ({self.settings.ollama_model}) failed to process request: {exc}"
            ) from exc

    def transcribe_audio_cloud(self, audio_path: Path, prompt_hint: str = "") -> str | None:
        """Second-pass high-fidelity re-transcription of saved audio via Gemini."""
        if not self._gemini_client or not self.settings.cloud_transcribe:
            return None
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return None

        try:
            from google.genai import types

            log.info("Uploading %s to Gemini for high-accuracy code-switch re-transcription...", audio_path.name)
            uploaded_file = self._gemini_client.files.upload(file=str(audio_path))
            transcribe_prompt = (
                "Please transcribe this lecture audio accurately word-for-word. "
                "The speaker may switch naturally between Bisaya (Cebuano), Tagalog, and English. "
                "Preserve exact technical terminology, code, numbers, and dates. "
                f"{prompt_hint}"
            ).strip()

            response = self._gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=[uploaded_file, transcribe_prompt],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            # Delete remote temporary uploaded file after transcribing
            try:
                self._gemini_client.files.delete(name=uploaded_file.name)
            except Exception:  # noqa: BLE001
                pass

            return response.text.strip() if response.text else None
        except Exception as exc:  # noqa: BLE001
            log.warning("Cloud audio re-transcription failed (%s); retaining local transcript", exc)
            return None
