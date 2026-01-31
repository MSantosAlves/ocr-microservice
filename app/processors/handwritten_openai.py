from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Dict, Tuple

from openai import OpenAI
from PIL import Image

from app.core.config import get_settings


class OpenAIHandwritingProcessor:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.openai_model:
            raise ValueError("OPENAI_MODEL is required to use OpenAI handwriting OCR.")
        self.client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
        )

    def extract_text(
        self, image: Image.Image, prompt_name: str | None = None
    ) -> Tuple[str, float, Dict[str, object]]:
        image_b64 = self._image_to_base64(image)
        prompt = _load_prompt(prompt_name or "handwritten_general.md")

        last_error: Exception | None = None
        for attempt in range(1, self.settings.openai_max_retries + 1):
            try:
                response = self.client.responses.create(
                    model=self.settings.openai_model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{image_b64}",
                                },
                            ],
                        }
                    ],
                )
                text = response.output_text or ""
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", None) if usage else None
                output_tokens = getattr(usage, "output_tokens", None) if usage else None
                return (
                    text.strip(),
                    0.0,
                    {
                        "model": self.settings.openai_model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                )
            except Exception as error:
                last_error = error
                if attempt < self.settings.openai_max_retries:
                    time.sleep(2**attempt)

        raise RuntimeError(f"OpenAI OCR failed: {last_error}") from last_error

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
