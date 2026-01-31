import argparse
import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image

from app.processors.pdf_native import PDFNativeProcessor
from app.processors.printed_ocr import PrintedOCRProcessor
from app.utils.image_processing import pdf_to_images


def summarize(label: str, text: str, confidence: float, metadata: dict, preview: int) -> None:
    print(label)
    print(f"text_length: {len(text)}")
    print(f"confidence: {round(confidence, 4)}")
    print(f"metadata: {metadata}")
    if preview > 0:
        print("preview:")
        print(text[:preview])
    print()


def run_image(
    path: Path, language: str, preview: int, preprocess: bool, max_side: int
) -> None:
    processor = PrintedOCRProcessor(
        language=language, preprocess=preprocess, max_side=max_side
    )
    image = Image.open(path)
    text, confidence, metadata = processor.extract_text(image)
    summarize("IMAGE", text, confidence, metadata, preview)


def run_scanned_pdf(
    path: Path,
    language: str,
    preview: int,
    all_pages: bool,
    preprocess: bool,
    dpi: int,
    max_side: int,
) -> None:
    processor = PrintedOCRProcessor(
        language=language, preprocess=preprocess, max_side=max_side
    )
    images, page_count = pdf_to_images(str(path), dpi=dpi)
    print(f"PDF pages: {page_count}")
    print()

    pages = images if all_pages else images[:1]
    for index, image in enumerate(pages, start=1):
        text, confidence, metadata = processor.extract_text(image)
        summarize(f"PDF page {index}", text, confidence, metadata, preview)


def run_native_pdf(path: Path, preview: int) -> None:
    processor = PDFNativeProcessor(str(path))
    text, confidence, metadata = processor.extract_text()
    summarize("PDF native", text, confidence, metadata, preview)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCR samples locally.")
    parser.add_argument("--image", type=Path, help="Path to a printed image (jpg/png).")
    parser.add_argument("--pdf-scanned", type=Path, help="Path to a scanned PDF.")
    parser.add_argument("--pdf-native", type=Path, help="Path to a native-text PDF.")
    parser.add_argument("--language", default="pt", help="OCR language (default: pt).")
    parser.add_argument("--preview", type=int, default=200, help="Preview length.")
    parser.add_argument("--dpi", type=int, default=200, help="PDF render DPI.")
    parser.add_argument(
        "--max-side", type=int, default=2000, help="Resize max image side."
    )
    parser.add_argument(
        "--no-preprocess", action="store_true", help="Disable image pre-processing."
    )
    parser.add_argument("--all-pages", action="store_true", help="Process all PDF pages.")

    args = parser.parse_args()

    preprocess = not args.no_preprocess
    if args.pdf_scanned:
        run_scanned_pdf(
            args.pdf_scanned,
            args.language,
            args.preview,
            args.all_pages,
            preprocess,
            args.dpi,
            args.max_side,
        )
    if args.image:
        run_image(args.image, args.language, args.preview, preprocess, args.max_side)
    if args.pdf_native:
        run_native_pdf(args.pdf_native, args.preview)

    if not any([args.image, args.pdf_scanned, args.pdf_native]):
        parser.print_help()


if __name__ == "__main__":
    main()
