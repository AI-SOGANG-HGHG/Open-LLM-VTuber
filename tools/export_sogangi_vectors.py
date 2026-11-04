"""Export original vector views from Sogang's UI guide, without redrawing artwork.

Requires the optional pymupdf package. The SVG paths are preserved; only each
SVG's viewport changes. These are reference vectors, not layered PSD/Cubism files.
"""

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


VIEWS = {
    "neutral": (19, (175, 315, 270, 337)),
    "joy": (20, (242, 230, 140, 176)),
    "love": (20, (442, 230, 146, 176)),
    "discovery": (20, (650, 230, 145, 176)),
    "teaching": (20, (130, 475, 164, 178)),
    "anger": (20, (337, 475, 145, 178)),
    "peek": (20, (520, 475, 184, 178)),
    "cheer": (20, (730, 475, 169, 178)),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    import pymupdf

    if not args.pdf.read_bytes().startswith(b"%PDF"):
        parser.error("The source is not a PDF document")
    destinations = [args.output / f"sogangi-{name}.svg" for name in VIEWS]
    if not args.overwrite and any(path.exists() for path in destinations):
        parser.error("Output exists; use --overwrite to regenerate known exports")
    args.output.mkdir(parents=True, exist_ok=True)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    exports = []
    with pymupdf.open(args.pdf) as document:
        for name, (number, view) in VIEWS.items():
            page = document[number - 1]
            root = ET.fromstring(page.get_svg_image(text_as_path=False))
            # Page headings and colour labels are not part of the character.
            for parent in root.iter():
                for child in list(parent):
                    if child.tag == "{http://www.w3.org/2000/svg}text":
                        parent.remove(child)
            root.set("viewBox", " ".join(map(str, view)))
            root.set("width", str(view[2]))
            root.set("height", str(view[3]))
            root.set("role", "img")
            path = args.output / f"sogangi-{name}.svg"
            path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
            exports.append(
                {"name": name, "page": number, "viewport": view, "file": path.name}
            )
    manifest = {
        "source_url": "https://www.sogang.ac.kr/intro/symbol/data/Sogang_UI_renewal.pdf",
        "source_sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
        "method": "Original PDF vector paths, cropped SVG viewport; no generated character artwork",
        "layered_psd_available": False,
        "exports": exports,
    }
    (args.output / "sogangi-vector-source.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Exported {len(exports)} original vector views to {args.output}")


if __name__ == "__main__":
    main()
