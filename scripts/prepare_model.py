"""Download only the original full-precision ONNX model at build time."""

from pathlib import Path
from urllib.request import urlopen
import shutil


REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
BASE = f"https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/{REVISION}"


def main():
    directory = Path(__file__).resolve().parent.parent / ".model"
    directory.mkdir(exist_ok=True)
    for source, filename in [("onnx/model.onnx", "model.onnx"), ("tokenizer.json", "tokenizer.json"), ("README.md", "MODEL_CARD.md")]:
        target = directory / filename
        temporary = target.with_suffix(".download")
        with urlopen(f"{BASE}/{source}", timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(target)
        print(f"Prepared {filename}: {target.stat().st_size:,} bytes", flush=True)


if __name__ == "__main__":
    main()
