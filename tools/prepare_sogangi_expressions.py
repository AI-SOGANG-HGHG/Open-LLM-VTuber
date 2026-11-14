"""Add pinned official anger/discovery face parts to a separate preparation PSD.

Uses original PDF curves and the existing rasterizer; no generated character art.
Requires the optional art environment (psd-tools, Pillow, PyMuPDF, Playwright).
"""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from export_sogangi_psd import BrowserRasterizer, rasterize
from prepare_sogangi_layers import (
    SOURCE_SHA256,
    NS,
    prefix_ids,
    split_drawings,
    wrapped_path,
)


def main():
    import numpy as np
    import pymupdf
    from psd_tools import PSDImage

    assets = Path("web_tool/sogangi/assets")
    baseline = assets / "cubism-import"
    output = assets / "expressions"
    pdf = Path("tmp/sogangi-reference/Sogang_UI_renewal.pdf")
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Official PDF changed; review drawing identities first")
    base = json.loads((baseline / "import-manifest.json").read_text(encoding="utf8"))
    psd_path = baseline / "sogangi-cubism-import.psd"
    if hashlib.sha256(psd_path.read_bytes()).hexdigest() != base["psd_sha256"]:
        raise ValueError("Baseline PSD changed")
    output.mkdir(parents=True, exist_ok=True)
    (output / "layers").mkdir(exist_ok=True)
    psd = PSDImage.open(psd_path)
    groups = {group.name: group for group in psd}
    parts = copy.deepcopy(base["parts"])
    for part in parts:
        shutil.copyfile(baseline / part["file"], output / part["file"])
    with pymupdf.open(pdf) as document, BrowserRasterizer() as render:
        face = document[18].get_drawings()[14]["rect"]
        page = document[19]
        drawings = page.get_drawings()
        svg = ET.fromstring(page.get_svg_image(text_as_path=False))
        prefix_ids(svg, "expression_")
        logical = split_drawings(svg, drawings)
        if len(logical) != 218:
            raise ValueError("Reviewed expression drawing order changed")
        for name, parent, index, face_index in [
            ("EyeL_Anger", "Eye L", 50, 42),
            ("EyeR_Anger", "Eye R", 51, 42),
            ("Mouth_AngerClosed", "Mouth", 47, 42),
            ("Mouth_SurpriseOpen", "Mouth", 203, 194),
            ("Mouth_AngerOpen", "Mouth", 203, 194),
        ]:
            source_face = drawings[face_index]["rect"]
            scale = face.width / source_face.width
            tx, ty = face.x0 - scale * source_face.x0, face.y0 - scale * source_face.y0
            root = ET.Element(
                NS + "svg",
                {"width": "270", "height": "337", "viewBox": "175 315 270 337"},
            )
            root.append(copy.deepcopy(svg.find(NS + "defs")))
            layer_svg = ET.SubElement(
                root,
                NS + "g",
                {"transform": f"matrix({scale:.9f} 0 0 {scale:.9f} {tx:.9f} {ty:.9f})"},
            )
            for item in logical[index]:
                layer_svg.append(wrapped_path(item))
            vector_path = output / (name + ".svg")
            vector_path.write_text(
                ET.tostring(root, encoding="unicode"), encoding="utf8"
            )
            image, _ = rasterize(vector_path, 2048, 128, render)
            bounds = image.getchannel("A").getbbox()
            if bounds is None:
                raise ValueError("Empty official expression part")
            cropped = image.crop(bounds)
            cropped.save(output / "layers" / (name + ".png"))
            layer = psd.create_pixel_layer(
                cropped, name=name, left=bounds[0], top=bounds[1]
            )
            layer.visible = False
            groups[parent].append(layer)
            parts.append(
                {
                    "name": name,
                    "path": [parent, name],
                    "visible": False,
                    "bounds": list(bounds),
                    "file": "layers/" + name + ".png",
                    "source_page": 20,
                    "drawing_index": index,
                    "alignment": [scale, tx, ty],
                    "trimmed_rgba_sha256": hashlib.sha256(
                        cropped.tobytes()
                    ).hexdigest(),
                }
            )
    info = psd._record.layer_and_mask_information.layer_info
    info.layer_count = -len(info.layer_records)
    destination = output / "sogangi-expressions.psd"
    psd.save(destination)
    restored = PSDImage.open(destination)
    leaves = {
        layer.name: layer for layer in restored.descendants() if not layer.is_group()
    }
    if len(leaves) != 29 or len(restored) != 9:
        raise ValueError("Expression PSD structure changed")
    for part in parts:
        layer = leaves[part["name"]]
        if (
            layer.offset != tuple(part["bounds"][:2])
            or layer.visible != part["visible"]
        ):
            raise ValueError("Expression layer position/visibility changed")
        if (
            hashlib.sha256(layer.topil().tobytes()).hexdigest()
            != part["trimmed_rgba_sha256"]
        ):
            raise ValueError("Expression part pixels changed during PSD save")
    original = PSDImage.open(psd_path).composite(force=True, color=1.0, alpha=0)
    neutral = restored.composite(force=True, color=1.0, alpha=0)
    error = int(
        np.abs(np.asarray(original).astype(int) - np.asarray(neutral).astype(int)).max()
    )
    if error != 0:
        raise ValueError(f"Neutral preparation composite changed: {error}")
    neutral.save(output / "neutral-preview.png")
    manifest = {
        "schema_version": 1,
        "status": "official_expression_parts_preparation",
        "source_pdf_sha256": SOURCE_SHA256,
        "baseline_psd_sha256": base["psd_sha256"],
        "psd_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "canvas": {"width": 2048, "height": 2048},
        "parts": parts,
        "layer_count": 29,
        "group_count": 9,
        "layer_pixels_offsets_and_visibility_exact": True,
        "neutral_composite_exact": True,
        "official_layered_source": False,
        "notes": [
            "Anger-open reuses the discovery mouth; its wider/flatter shape is a project keyform adaptation.",
            "Surprise eye widening is a project affine adaptation of the neutral eyes.",
            "No sadness, fear or smirk artwork was added.",
        ],
    }
    (output / "import-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(
        "Prepared 29-layer expression PSD; baseline pixels and neutral composite unchanged."
    )


if __name__ == "__main__":
    main()
