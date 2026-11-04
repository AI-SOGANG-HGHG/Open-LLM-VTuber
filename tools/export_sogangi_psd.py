"""Convert existing official-vector parts to a visible-layer preparation PSD.

This is format conversion, not underpainting or a Cubism rig. Requires optional
psd-tools 1.26.0, Playwright and Pillow in a separate Python >=3.11 environment.
"""

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
SOURCE_SHA256 = "aa1fed216c2106c3f4699e259b80cb58df22f411954b12ffb96688c66cac48e0"


class BrowserRasterizer:
    """Use the same SVG clipping behavior as the app's installed Chrome."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.launch(
                executable_path=os.environ.get(
                    "SOGANGI_BROWSER",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                ),
                headless=True,
            )
            self.page = self.browser.new_page()
            return self
        except Exception:
            self.playwright.stop()
            raise

    def __call__(self, svg):
        encoded = base64.b64encode(svg).decode("ascii")
        png = self.page.evaluate(
            """async encoded => {
          const image = new Image();
          image.src = 'data:image/svg+xml;base64,' + encoded;
          await image.decode();
          const canvas = document.createElement('canvas');
          canvas.width=image.naturalWidth; canvas.height=image.naturalHeight;
          canvas.getContext('2d').drawImage(image,0,0);
          return canvas.toDataURL('image/png').split(',')[1];
        }""",
            encoded,
        )
        return base64.b64decode(png)

    def __exit__(self, *_):
        try:
            self.browser.close()
        finally:
            self.playwright.stop()


def rasterize(path, canvas, margin, render_svg):
    from PIL import Image

    source = ET.parse(path).getroot()
    x, y, width, height = map(float, source.attrib["viewBox"].split())
    scale = min((canvas - 2 * margin) / width, (canvas - 2 * margin) / height)
    # Keep all original clipping coordinates in the root coordinate system.
    # Nested SVG viewports are not rendered consistently by every SVG converter.
    side = canvas / scale
    source.set("width", str(canvas))
    source.set("height", str(canvas))
    source.set(
        "viewBox", f"{x - (side - width) / 2} {y - (side - height) / 2} {side} {side}"
    )
    png = render_svg(ET.tostring(source))
    image = Image.open(io.BytesIO(png))
    image.load()
    if image.size != (canvas, canvas) or image.mode != "RGBA":
        raise ValueError("Unexpected raster canvas/mode")
    return image, png


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layers", type=Path, default=Path("web_tool/sogangi/assets/layers")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("web_tool/sogangi/assets/production")
    )
    parser.add_argument("--canvas", type=int, choices=[1024, 2048], default=2048)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    with BrowserRasterizer() as render_svg:
        export(args, render_svg)


def export(args, render_svg):
    from psd_tools import PSDImage
    import numpy as np

    manifest_file = args.layers / "parts-manifest.json"
    source = json.loads(manifest_file.read_text(encoding="utf-8"))
    if source.get("source_sha256") != SOURCE_SHA256 or len(source["parts"]) != 24:
        raise ValueError("Unexpected source manifest/version")
    if args.output.exists() and any(args.output.iterdir()) and not args.overwrite:
        raise ValueError(
            "Output exists; use --overwrite to replace this generated bundle"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    png_directory = args.output / "layers"
    png_directory.mkdir(exist_ok=True)
    canvas, margin = args.canvas, args.canvas // 16
    psd = PSDImage.new(mode="RGBA", size=(canvas, canvas), depth=8)
    psd.background_color = None
    parts = []
    seen = set()
    for part in source["parts"]:
        name = part["name"]
        filename = part["file"]
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]+\.svg", filename)
            or name in seen
            or name != Path(filename).stem
        ):
            raise ValueError("Invalid or duplicate layer")
        seen.add(name)
        path = (args.layers / filename).resolve()
        if path.parent != args.layers.resolve():
            raise ValueError("Layer path escapes source directory")
        image, png = rasterize(path, canvas, margin, render_svg)
        layer = psd.create_pixel_layer(image, name=name, top=0, left=0)
        layer.visible = part.get("default_visible", True)
        (png_directory / f"{name}.png").write_bytes(png)
        parts.append(
            {
                "name": name,
                "file": f"layers/{name}.png",
                "visible": layer.visible,
                "source_svg_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "rgba_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
            }
        )
        print(f"Converted {name}", flush=True)
    psd_path = args.output / "sogangi-visible-parts.psd"
    # PSD format: negative layer count declares merged-image alpha as transparency.
    # psd-tools 1.26.0 otherwise saves an opaque compatibility preview.
    psd._record.layer_and_mask_information.layer_info.layer_count = -len(psd)
    psd.save(psd_path)
    restored = PSDImage.open(psd_path)
    if len(restored) != 24 or restored.size != (canvas, canvas) or restored.depth != 8:
        raise ValueError("PSD document structure changed during export")
    for layer, part in zip(restored, parts):
        if (
            layer.name != part["name"]
            or layer.visible != part["visible"]
            or layer.offset != (0, 0)
        ):
            raise ValueError("PSD layer name/visibility/alignment mismatch")
        if hashlib.sha256(layer.topil().tobytes()).hexdigest() != part["rgba_sha256"]:
            raise ValueError(f"PSD layer pixel round-trip failed: {layer.name}")
    merged = restored.composite(force=True, color=1.0, alpha=0.0)
    cached = restored.topil()
    if cached.mode != "RGBA" or cached.getpixel((0, 0))[3] != 0:
        raise ValueError("PSD compatibility preview lost transparency")
    merged.save(args.output / "neutral-preview.png")
    reference, _ = rasterize(
        args.layers.parent / "sogangi-neutral.svg", canvas, margin, render_svg
    )
    # Compare alpha and premultiplied colors, ignoring meaningless RGB in transparency.
    actual = np.asarray(merged, dtype=np.float32) / 255
    expected = np.asarray(reference, dtype=np.float32) / 255
    for pixels in [actual, expected]:
        pixels[:, :, :3] *= pixels[:, :, 3:4]
    difference = np.abs(actual - expected) * 255
    metrics = {
        "mean_channel_error_255": round(float(difference.mean()), 6),
        "fraction_pixels_over_16": round(
            float((difference.max(axis=2) > 16).mean()), 6
        ),
        "individual_layer_pixels_exact": True,
    }
    report = {
        "status": "visible_parts_preparation_psd",
        "official_layered_source": False,
        "source_pdf_sha256": SOURCE_SHA256,
        "svg_renderer": "installed Chromium via Playwright",
        "canvas": {
            "width": canvas,
            "height": canvas,
            "mode": "RGB 8bit with layer alpha",
            "transparent": True,
            "margin": margin,
        },
        "layer_order": "background to foreground; all layers share full-canvas coordinates",
        "layer_count": 24,
        "default_visible_count": sum(part["visible"] for part in parts),
        "parts": parts,
        "verification": metrics,
        "psd_sha256": hashlib.sha256(psd_path.read_bytes()).hexdigest(),
        "not_completed": [
            "hidden-overlap artwork",
            "artist review of expression candidates",
            "deformation topology",
            "Cubism import check",
            "cmo3 project",
            "moc3 runtime",
        ],
    }
    (args.output / "handoff-manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if (
        metrics["mean_channel_error_255"] > 0.7
        or metrics["fraction_pixels_over_16"] > 0.01
    ):
        raise ValueError(f"Composite differs too much from source: {metrics}")
    (args.output / "README.txt").write_text(
        "SOGANGI VISIBLE-PARTS PREPARATION PSD\n\n"
        "2048 (or selected size) square RGB 8-bit document with transparent layers.\n"
        "24 existing vector parts, 21 visible by default; three expression candidates hidden.\n"
        "This is a generated preparation file, not an official layered PSD or a Cubism model.\n"
        "All PNG layers retain the same canvas. Do not independently crop/resize them.\n"
        "Complete hidden overlaps and review expression shapes before rigging.\n"
        "Layer L/R are screen coordinates. Preserve official source attribution/conditions.\n"
        "Source: https://www.sogang.ac.kr/intro/symbol/data/Sogang_UI_renewal.pdf\n"
        "PSD structure and pixels were reopened and checked with psd-tools, not Cubism Editor.\n",
        encoding="utf-8",
    )
    bundle = args.output / "sogangi-art-handoff.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        allowed = [
            psd_path,
            args.output / "neutral-preview.png",
            args.output / "handoff-manifest.json",
            args.output / "README.txt",
            *(args.output / part["file"] for part in parts),
        ]
        for path in allowed:
            archive.write(path, path.relative_to(args.output))
    print(
        json.dumps(
            {"psd": str(psd_path), "bundle": str(bundle), "verification": metrics}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
