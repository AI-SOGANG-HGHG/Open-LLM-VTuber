"""Prepare visible vector parts from the pinned official PDF, not a rig-ready PSD.

The source curves, clipping paths and paint order are retained. Hidden artwork,
closed eyes and an open mouth still need an artist's work before Cubism rigging.
Requires optional pymupdf.
"""

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


SOURCE_SHA256 = "aa1fed216c2106c3f4699e259b80cb58df22f411954b12ffb96688c66cac48e0"
NS = "{http://www.w3.org/2000/svg}"
PARTS = {
    "ArmL_Base": [1],
    "ArmR_Base": [2],
    "LegL_Base": [3],
    "LegR_Base": [4],
    "Body_Tunic": [5, 6],
    "Body_Stripe": [7],
    "Body_Emblem": [8],
    "Hood_WingL": [9, 10],
    "Hood_WingR": [11, 12],
    "Hood_Base": [13],
    "Face_Base": [14],
    "EyeR_Open": [15],
    "EyeR_Highlight": [16],
    "EyeL_Open": [17],
    "EyeL_Highlight": [18],
    "Mouth_Closed": [19],
    "Hood_BirdEyeL": [20],
    "Hood_BirdEyeR": [21],
    "Hood_Beak": [22, 23],
    "Face_CheekR": [24],
    "Face_CheekL": [25],
}


def painted_paths(node, parents=()):
    if node.tag == NS + "defs":
        return
    if node.tag == NS + "path":
        yield node, parents
        return
    if node.tag == NS + "g" and node.attrib:
        parents = (*parents, dict(node.attrib))
    for child in node:
        yield from painted_paths(child, parents)


def wrapped_path(item):
    path, parents = item
    leaf = copy.deepcopy(path)
    for attributes in reversed(parents):
        group = ET.Element(NS + "g", attributes)
        group.append(leaf)
        leaf = group
    return leaf


def split_drawings(root, drawings):
    paths = list(painted_paths(root))
    groups, offset = [], 0
    for drawing in drawings:
        count = 2 if drawing["type"] == "fs" else 1
        groups.append(paths[offset : offset + count])
        offset += count
    if offset != len(paths):
        raise ValueError("SVG/PDF paint counts differ")
    return groups


def prefix_ids(root, prefix):
    for node in root.iter():
        if "id" in node.attrib:
            node.set("id", prefix + node.get("id"))
        for key, value in list(node.attrib.items()):
            node.set(
                key,
                re.sub(
                    r"url\(#([^)]+)\)", lambda match: f"url(#{prefix}{match[1]})", value
                ),
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    import pymupdf

    if hashlib.sha256(args.pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        parser.error(
            "PDF differs from the reviewed source; inspect its layout before extracting parts"
        )
    destination = args.output / "layers"
    if destination.exists() and not args.overwrite:
        parser.error("Layer exports exist; use --overwrite to regenerate them")
    destination.mkdir(parents=True, exist_ok=True)
    ET.register_namespace("", NS[1:-1])
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    with pymupdf.open(args.pdf) as document:
        page = document[18]
        original = ET.fromstring(page.get_svg_image(text_as_path=False))
        drawings = page.get_drawings()
        logical = split_drawings(original, drawings)
        if len(logical) != 35:
            parser.error("The SVG/PDF drawing order does not match the reviewed layout")

        joy_page = document[19]
        joy_source = ET.fromstring(joy_page.get_svg_image(text_as_path=False))
        prefix_ids(joy_source, "joy_")
        joy_drawings = joy_page.get_drawings()
        joy_groups = split_drawings(joy_source, joy_drawings)
        if len(joy_groups) != 218:
            parser.error("The expression reference layout changed")
        face, joy_face = drawings[14]["rect"], joy_drawings[141]["rect"]
        scale = face.width / joy_face.width
        tx, ty = face.x0 - scale * joy_face.x0, face.y0 - scale * joy_face.y0
        alignment = f"matrix({scale:.9f} 0 0 {scale:.9f} {tx:.9f} {ty:.9f})"

        def canvas(include_variants=False):
            root = ET.Element(
                NS + "svg",
                {"width": "270", "height": "337", "viewBox": "175 315 270 337"},
            )
            root.append(copy.deepcopy(original.find(NS + "defs")))
            if include_variants:
                root.append(copy.deepcopy(joy_source.find(NS + "defs")))
            return root

        combined = canvas(include_variants=True)
        index_to_part = {
            index: name for name, indices in PARTS.items() for index in indices
        }
        for index in range(1, 26):
            group = ET.SubElement(
                combined,
                NS + "g",
                {"data-layer": index_to_part[index], "id": f"drawing-{index}"},
            )
            for item in logical[index]:
                group.append(wrapped_path(item))
        combined_path = destination / "sogangi-visible-layers.svg"
        exports = []
        for name, indices in PARTS.items():
            root = canvas()
            layer = ET.SubElement(root, NS + "g", {"id": name, "data-layer": name})
            bounds = pymupdf.Rect()
            for index in indices:
                bounds |= drawings[index]["rect"]
                for item in logical[index]:
                    layer.append(wrapped_path(item))
            path = destination / f"{name}.svg"
            path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
            exports.append(
                {
                    "name": name,
                    "file": path.name,
                    "drawing_indices": indices,
                    "bounds": [round(v, 3) for v in bounds],
                }
            )
        for name, index in {
            "EyeL_Closed": 142,
            "EyeR_Closed": 143,
            "Mouth_Open": 144,
        }.items():
            root = canvas(include_variants=True)
            layer = ET.SubElement(root, NS + "g", {"id": name, "data-layer": name})
            aligned = ET.SubElement(layer, NS + "g", {"transform": alignment})
            for item in joy_groups[index]:
                aligned.append(wrapped_path(item))
            path = destination / f"{name}.svg"
            path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
            candidate = copy.deepcopy(layer)
            candidate.set("opacity", "0")
            combined.append(candidate)
            bounds = joy_drawings[index]["rect"]
            exports.append(
                {
                    "name": name,
                    "file": path.name,
                    "source_page": 20,
                    "drawing_indices": [index],
                    "alignment": alignment,
                    "bounds": [
                        round(bounds.x0 * scale + tx, 3),
                        round(bounds.y0 * scale + ty, 3),
                        round(bounds.x1 * scale + tx, 3),
                        round(bounds.y1 * scale + ty, 3),
                    ],
                    "default_visible": False,
                    "note": "Official joy-expression source, aligned to the neutral face; artwork review still required",
                }
            )
        combined_path.write_text(
            ET.tostring(combined, encoding="unicode"), encoding="utf-8"
        )
    manifest = {
        "status": "visible_vector_parts_only",
        "source_sha256": SOURCE_SHA256,
        "source_page": 19,
        "canvas_viewbox": [175, 315, 270, 337],
        "coordinate_convention": "L/R use screen coordinates in this preparation export; confirm before PSD/Cubism naming",
        "psd_available": False,
        "rig_available": False,
        "parts": exports,
        "missing": [
            "hidden overlaps and underpainting",
            "artist review of closed eyes and open-mouth candidates",
            "smooth deformation topology and any extra mouth shapes",
            "Cubism mesh/deformers/parameters",
            "runtime model export",
        ],
    }
    manifest_path = destination / "parts-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    readme = destination / "README.txt"
    readme.write_text(
        "서강이 원화 준비 자료 — 공식 UI 가이드북 19–20쪽 벡터에서 추출\n\n각 SVG는 같은 캔버스를 사용합니다. 합성 파일은 기본형의 그리기 순서를 유지합니다. 감은 눈과 열린 입 후보는 공식 기쁨형에서 가져와 기본 얼굴에 같은 비율로 정렬했고 기본 합성에서는 숨겼습니다. 이 자료는 레이어 PSD나 Live2D 모델이 아닙니다. 가려진 원화 보완, 표정 후보 검토, PSD 정리와 Cubism 리깅이 추가로 필요합니다. 원본 권리는 서강대학교 등 원 권리자에게 있습니다.\n\n공식 원본: https://www.sogang.ac.kr/intro/symbol/data/Sogang_UI_renewal.pdf\n",
        encoding="utf-8",
    )
    archive = args.output / "sogangi-visible-parts.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in [
            combined_path,
            manifest_path,
            readme,
            *(destination / item["file"] for item in exports),
        ]:
            bundle.write(path, arcname=path.name)
    print(f"Prepared {len(exports)} visible vector parts and {archive}")


if __name__ == "__main__":
    main()
