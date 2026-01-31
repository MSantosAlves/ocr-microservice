from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Dict, Tuple

import anthropic
from PIL import Image

from app.core.config import get_settings


class AnthropicHandwritingProcessor:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.anthropic_model:
            raise ValueError("ANTHROPIC_MODEL is required to use Anthropic handwriting OCR.")
        self.client = anthropic.Anthropic(
            api_key=self.settings.anthropic_api_key,
            timeout=self.settings.anthropic_timeout_seconds,
        )

    def extract_text(
        self, image: Image.Image, prompt_name: str | None = None
    ) -> Tuple[str, float, Dict[str, object]]:
        image_b64 = self._image_to_base64(image)
        prompt = _load_prompt(prompt_name or "handwritten_general.md")

        last_error: Exception | None = None
        for attempt in range(1, self.settings.anthropic_max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.settings.anthropic_model,
                    max_tokens=2048,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": image_b64,
                                    },
                                },
                            ],
                        }
                    ],
                )
                text = "".join(block.text for block in response.content if block.type == "text")
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", None) if usage else None
                output_tokens = getattr(usage, "output_tokens", None) if usage else None
                return (
                    text.strip(),
                    0.0,
                    {
                        "model": self.settings.anthropic_model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                )
            except Exception as error:
                last_error = error
                if attempt < self.settings.anthropic_max_retries:
                    time.sleep(2**attempt)

        raise RuntimeError(f"Anthropic OCR failed: {last_error}") from last_error

    @staticmethod
    def _image_to_base64(image: Image.Image) -> str:
        buffer = image.convert("RGB")
        with _to_bytes_io() as stream:
            buffer.save(stream, format="PNG")
            return base64.b64encode(stream.getvalue()).decode("ascii")


def _to_bytes_io():
    from io import BytesIO

    return BytesIO()


def _load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    if not prompt_path.exists():
        return "Extract all handwritten text from the image."
    return prompt_path.read_text(encoding="utf-8").strip()
