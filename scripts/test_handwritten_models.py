import argparse
import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image

from app.processors.handwritten_anthropic import AnthropicHandwritingProcessor
from app.processors.handwritten_openai import OpenAIHandwritingProcessor


def run_openai(image_path: Path, prompt: str | None) -> None:
    processor = OpenAIHandwritingProcessor()
    with Image.open(image_path) as image:
        text, confidence, metadata = processor.extract_text(image, prompt_name=prompt)
    print("OPENAI")
    print(f"text_length: {len(text)}")
    print(f"confidence: {confidence}")
    print(f"metadata: {metadata}")
    print("text:")
    print(text)
    print()


def run_anthropic(image_path: Path, prompt: str | None) -> None:
    processor = AnthropicHandwritingProcessor()
    with Image.open(image_path) as image:
        text, confidence, metadata = processor.extract_text(image, prompt_name=prompt)
    print("ANTHROPIC")
    print(f"text_length: {len(text)}")
    print(f"confidence: {confidence}")
    print(f"metadata: {metadata}")
    print("text:")
    print(text)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test handwritten OCR models.")
    parser.add_argument(
        "--image",
        type=Path,
        required=True,
        help="Path to the handwritten image (jpg/png).",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Prompt filename in app/prompts (ex: handwritten_exam.md).",
    )
    parser.add_argument(
        "--skip-openai", action="store_true", help="Skip OpenAI test."
    )
    parser.add_argument(
        "--skip-anthropic", action="store_true", help="Skip Anthropic test."
    )

    args = parser.parse_args()

    if not args.skip_openai:
        run_openai(args.image, args.prompt)
    if not args.skip_anthropic:
        run_anthropic(args.image, args.prompt)


if __name__ == "__main__":
    main()
