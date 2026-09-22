from __future__ import annotations

from typing import Any, Mapping


class GeminiAIError(RuntimeError):
    """Error seguro para mostrar en la interfaz sin revelar credenciales."""


def get_gemini_config(secrets: Mapping[str, Any]) -> dict[str, str] | None:
    try:
        settings = dict(secrets["gemini"])
    except (KeyError, TypeError, ValueError):
        return None

    api_key = str(settings.get("api_key", "")).strip()
    if not api_key:
        return None

    model = str(settings.get("model", "gemini-2.5-flash")).strip()
    return {"api_key": api_key, "model": model or "gemini-2.5-flash"}


def generate_analysis(config: Mapping[str, str], prompt: str) -> str:
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiAIError("El componente de IA todavía no está instalado.") from exc

    try:
        client = genai.Client(api_key=config["api_key"])
        response = client.models.generate_content(
            model=config["model"],
            contents=prompt,
        )
        text = str(getattr(response, "text", "") or "").strip()
    except Exception as exc:
        raise GeminiAIError(
            "Gemini no respondió. Revisa la clave, la cuota del proyecto y vuelve a intentar."
        ) from exc

    if not text:
        raise GeminiAIError("Gemini respondió sin contenido. Intenta nuevamente.")
    return text
