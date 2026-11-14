"""Prepare a separately grouped, alpha-trimmed PSD for a first Cubism import.

Canvas coordinates, original pixels and expression visibility are preserved.
Requires optional Pillow, numpy and psd-tools; does not use Editor internals.
This file is import preparation, not an imported/rigged Cubism model.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile

GROUPS = {
    "Arm L": ["ArmL_Base"],
    "Arm R": ["ArmR_Base"],
    "Lower Body": ["LegL_Base", "LegR_Base"],
    "Body": ["Body_Tunic", "Body_Stripe", "Body_Emblem"],
    "Hood": [
        "Hood_WingL",
        "Hood_WingR",
        "Hood_Base",
        "Hood_BirdEyeL",
        "Hood_BirdEyeR",
        "Hood_Beak",
    ],
    "Face": ["Face_Base", "Face_CheekR", "Face_CheekL"],
    "Eye R": ["EyeR_Open", "EyeR_Highlight", "EyeR_Closed"],
    "Eye L": ["EyeL_Open", "EyeL_Highlight", "EyeL_Closed"],
    "Mouth": ["Mouth_Closed", "Mouth_Open"],
}


def atlas_proposal(parts):
    """Find a conservative placement within the published FREE atlas size.

    This is a packing proposal only; no texture or native UVs are exported.
    The official Editor must arrange and export its own atlas and matching MOC.
    """
    size, padding = 2048, 4
    ordered = sorted(
        parts,
        key=lambda part: (
            -max(
                part["bounds"][2] - part["bounds"][0],
                part["bounds"][3] - part["bounds"][1],
            ),
            part["name"],
        ),
    )
    for percent in range(100, 49, -5):
        scale = percent / 100
        free, placed = [(0, 0, size, size)], []
        for part in ordered:
            source_width = part["bounds"][2] - part["bounds"][0]
            source_height = part["bounds"][3] - part["bounds"][1]
            width, height = (
                math.ceil(source_width * scale) + 2 * padding,
                math.ceil(source_height * scale) + 2 * padding,
            )
            choices = [rect for rect in free if width <= rect[2] and height <= rect[3]]
            if not choices:
                break
            x, y, _, _ = min(
                choices,
                key=lambda rect: (
                    min(rect[2] - width, rect[3] - height),
                    rect[2] * rect[3] - width * height,
                    rect[1],
                    rect[0],
                ),
            )
            next_free = []
            for fx, fy, fw, fh in free:
                if x >= fx + fw or x + width <= fx or y >= fy + fh or y + height <= fy:
                    next_free.append((fx, fy, fw, fh))
                    continue
                if x > fx:
                    next_free.append((fx, fy, x - fx, fh))
                if x + width < fx + fw:
                    next_free.append((x + width, fy, fx + fw - x - width, fh))
                if y > fy:
                    next_free.append((fx, fy, fw, y - fy))
                if y + height < fy + fh:
                    next_free.append((fx, y + height, fw, fy + fh - y - height))
            candidates = list(dict.fromkeys(next_free))
            free = [
                rect
                for rect in candidates
                if not any(
                    rect != other
                    and other[0] <= rect[0]
                    and other[1] <= rect[1]
                    and other[0] + other[2] >= rect[0] + rect[2]
                    and other[1] + other[3] >= rect[1] + rect[3]
                    for other in candidates
                )
            ]
            placed.append(
                {
                    "name": part["name"],
                    "allocation": [x, y, width, height],
                    "image_origin": [x + padding, y + padding],
                    "source_size": [source_width, source_height],
                }
            )
        if len(placed) == len(parts):
            return {
                "status": "placement_proposal_not_editor_export",
                "width": size,
                "height": size,
                "uniform_scale": scale,
                "padding": padding,
                "placements": placed,
                "notes": [
                    "One atlas proposal only; not a generated runtime texture or MOC UV map.",
                    "Use the official Editor to arrange/export its own atlas and matching MOC.",
                    "Free-edition limits and actual save/export must be checked in Editor 5.1.",
                ],
            }
    raise ValueError("Could not propose a 2048 atlas placement")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def keyform_plan():
    """A small explicit plan; no heuristically invented head or hair bindings."""
    scale = 1792 / 337

    def pivot(x, y):
        return [
            round((2048 - 270 * scale) / 2 + (x - 175) * scale, 3),
            round(128 + (y - 315) * scale, 3),
        ]

    parameters = []
    for side in ["L", "R"]:
        parameters.append(
            {
                "id": f"ParamEye{side}Open",
                "minimum": 0,
                "maximum": 1,
                "default": 1,
                "key_values": [0, 1],
                "targets": [
                    {
                        "path": [f"Eye {side}", f"Eye{side}_{part}"],
                        "pivot_psd": pivot(268.44 if side == "L" else 349.95, 446.57),
                        "states": [
                            {"value": 0, "opacity": 0, "scale_y": 0.08},
                            {"value": 1, "opacity": 1, "scale_y": 1},
                        ],
                    }
                    for part in ["Open", "Highlight"]
                ]
                + [
                    {
                        "path": [f"Eye {side}", f"Eye{side}_Closed"],
                        "pivot_psd": pivot(268.44 if side == "L" else 349.95, 446.57),
                        "states": [
                            {"value": 0, "opacity": 1},
                            {"value": 1, "opacity": 0},
                        ],
                    }
                ],
            }
        )
    parameters.append(
        {
            "id": "ParamMouthOpenY",
            "minimum": 0,
            "maximum": 1,
            "default": 0,
            "key_values": [0, 1],
            "targets": [
                {
                    "path": ["Mouth", "Mouth_Closed"],
                    "pivot_psd": pivot(309.19, 493),
                    "states": [
                        {"value": 0, "opacity": 1},
                        {"value": 1, "opacity": 0},
                    ],
                },
                {
                    "path": ["Mouth", "Mouth_Open"],
                    "pivot_psd": pivot(309.19, 493),
                    "states": [
                        {"value": 0, "opacity": 0, "scale_y": 0.25},
                        {"value": 1, "opacity": 1, "scale_y": 1},
                    ],
                },
            ],
        }
    )
    return {
        "status": "manual_keyform_plan_not_applied",
        "coordinate_convention": "screen L/R",
        "pivot_coordinate_system": "PSD pixels, origin top-left; not native Cubism model coordinates",
        "parameters": parameters,
        "groups": {
            "EyeBlink": ["ParamEyeLOpen", "ParamEyeROpen"],
            "LipSync": ["ParamMouthOpenY"],
        },
        "notes": [
            "Validate the imported drawable IDs and eye/mouth pivots in Editor first.",
            "Add mesh keyforms in Editor; this JSON does not apply them.",
            "Do not auto-infer head transforms or hair physics from mascot layer names.",
            "Confirm hidden expression layers are imported as editable meshes.",
        ],
    }


def export(args):
    import numpy as np
    from PIL import Image
    from psd_tools import PSDImage
    from psd_tools.api.layers import Group

    production = args.root / "assets/production"
    original_psd = production / "sogangi-visible-parts.psd"
    source = json.loads(
        (production / "handoff-manifest.json").read_text(encoding="utf-8")
    )
    if source["psd_sha256"] != digest(original_psd):
        raise ValueError("Baseline PSD hash changed")
    parts = {part["name"]: part for part in source["parts"]}
    planned = [name for group in GROUPS.values() for name in group]
    if len(planned) != 24 or len(set(planned)) != 24 or set(planned) != set(parts):
        raise ValueError("Layer grouping must cover exactly the reviewed 24 parts")
    if args.output.exists() and any(args.output.iterdir()) and not args.overwrite:
        raise ValueError(
            "Output exists; use --overwrite for this generated import bundle"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    png_directory = args.output / "layers"
    png_directory.mkdir(exist_ok=True)
    width, height = source["canvas"]["width"], source["canvas"]["height"]
    if (width, height) != (2048, 2048):
        raise ValueError("Review the pixel pivots before importing a different canvas size")
    psd = PSDImage.new("RGBA", (width, height), depth=8)
    psd.background_color = None
    exported, originals = [], {}
    for group_name, names in GROUPS.items():
        group = Group.new(psd, name=group_name)
        for name in names:
            part = parts[name]
            image = Image.open(production / part["file"]).convert("RGBA")
            if hashlib.sha256(image.tobytes()).hexdigest() != part["rgba_sha256"]:
                raise ValueError(f"Source pixels changed: {name}")
            bounds = image.getchannel("A").getbbox()
            if bounds is None:
                raise ValueError(f"Empty source layer: {name}")
            cropped = image.crop(bounds)
            png_path = png_directory / f"{name}.png"
            cropped.save(png_path)
            layer = psd.create_pixel_layer(
                cropped, name=name, left=bounds[0], top=bounds[1]
            )
            layer.visible = part["visible"]
            group.append(layer)
            originals[name] = image
            exported.append(
                {
                    "name": name,
                    "path": [group_name, name],
                    "visible": part["visible"],
                    "bounds": list(bounds),
                    "file": f"layers/{name}.png",
                    "rgba_sha256": part["rgba_sha256"],
                    "trimmed_rgba_sha256": hashlib.sha256(
                        cropped.tobytes()
                    ).hexdigest(),
                }
            )
    # Preserve the PSD format's merged transparency marker, including group records.
    layer_info = psd._record.layer_and_mask_information.layer_info
    layer_info.layer_count = -len(layer_info.layer_records)
    psd_path = args.output / "sogangi-cubism-import.psd"
    psd.save(psd_path)
    restored = PSDImage.open(psd_path)
    leaves = [layer for layer in restored.descendants() if not layer.is_group()]
    if (
        restored.size != (width, height)
        or len(leaves) != 24
        or len(restored) != len(GROUPS)
    ):
        raise ValueError("Grouped PSD structure changed on reopen")
    for layer, part in zip(leaves, exported):
        padded = Image.new("RGBA", (width, height))
        padded.paste(layer.topil(), layer.offset)
        if (
            layer.name != part["name"]
            or layer.visible != part["visible"]
            or layer.parent.name != part["path"][0]
            or padded.tobytes() != originals[layer.name].tobytes()
        ):
            raise ValueError(
                f"Layer coordinates/pixels did not survive trimming: {layer.name}"
            )
    neutral = restored.composite(force=True, color=1.0, alpha=0.0)
    baseline = PSDImage.open(original_psd).composite(force=True, color=1.0, alpha=0.0)
    difference = np.abs(
        np.asarray(neutral).astype(int) - np.asarray(baseline).astype(int)
    )
    max_error = int(difference.max())
    changed = int(np.any(difference, axis=2).sum())
    if max_error > 1 or restored.topil().getpixel((0, 0))[3] != 0:
        raise ValueError(
            f"Grouped composite changed beyond rounding tolerance: {max_error}"
        )
    neutral.save(args.output / "neutral-preview.png")
    manifest = {
        "schema_version": 1,
        "status": "grouped_trimmed_psd_import_preparation",
        "official_layered_source": False,
        "editor_import_verified": False,
        "cmo3_available": False,
        "moc3_available": False,
        "source_psd_sha256": source["psd_sha256"],
        "psd_sha256": digest(psd_path),
        "canvas": {"width": width, "height": height},
        "group_count": len(GROUPS),
        "layer_count": len(leaves),
        "parts": exported,
        "verification": {
            "layer_pixels_and_offsets_exact": True,
            "neutral_max_channel_error_255": max_error,
            "neutral_changed_pixels": changed,
            "merged_preview_transparent": True,
        },
        "notes": [
            "Cropped PNG parts require their manifest offsets; do not center them independently.",
            "Nine semantic folders replace the flat layer list without adding artwork.",
            "PSD layer order may be represented in reverse by a different reader; use paths, not indices.",
            "Automatic inference is unverified; use the explicit minimum keyform plan first.",
        ],
    }
    (args.output / "import-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "keyform-plan.json").write_text(
        json.dumps(keyform_plan(), indent=2), encoding="utf-8"
    )
    (args.output / "atlas-layout-proposal.json").write_text(
        json.dumps(atlas_proposal(exported), indent=2), encoding="utf-8"
    )
    (args.output / "README.txt").write_text(
        "SOGANGI CUBISM IMPORT PREPARATION\n\n"
        "2048 square canvas. 24 original parts in 9 semantic folders.\n"
        "Transparent margins were trimmed per layer; PSD offsets preserve original coordinates.\n"
        "Cropped PNG files MUST use the offsets/bounds in import-manifest.json.\n"
        "Source PSD remains unchanged. No new art, Editor import or Cubism export is certified.\n"
        "keyform-plan.json describes 3 proposed parameters; it does not apply them.\n"
        "Source rights: Sogang University/relevant owners.\n"
        "https://www.sogang.ac.kr/intro/symbol/data/Sogang_UI_renewal.pdf\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(
        args.output / "sogangi-cubism-import.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for path in [
            psd_path,
            args.output / "neutral-preview.png",
            args.output / "README.txt",
            args.output / "import-manifest.json",
            args.output / "keyform-plan.json",
            args.output / "atlas-layout-proposal.json",
            *(args.output / part["file"] for part in exported),
        ]:
            archive.write(path, path.relative_to(args.output))
    print(
        json.dumps(
            {
                "psd_bytes": psd_path.stat().st_size,
                "groups": len(GROUPS),
                "parts": len(leaves),
                "verification": manifest["verification"],
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("web_tool/sogangi"))
    parser.add_argument(
        "--output", type=Path, default=Path("web_tool/sogangi/assets/cubism-import")
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    for protected in [args.root / "assets/production", args.root / "assets/layers"]:
        if (
            args.output.resolve() == protected.resolve()
            or protected.resolve() in args.output.resolve().parents
        ):
            parser.error(
                "Import preparation output must be separate from original assets"
            )
    export(args)


if __name__ == "__main__":
    main()
