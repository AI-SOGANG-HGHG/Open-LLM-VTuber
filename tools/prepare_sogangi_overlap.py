"""Build separately reviewable shoulder underlaps and reproducible pose comparisons.

Requires the optional art environment. Existing official vector/PSD files are read
only. The extra shoulder shapes are authored candidates, not official artwork or
a Cubism rig. Pixel counts describe differences; they do not certify anatomy.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from export_sogangi_psd import BrowserRasterizer, rasterize

NS = "{http://www.w3.org/2000/svg}"
ET.register_namespace("", NS[1:-1])
POSES = [
    {"id": "neutral", "label": "정면 기준", "head": 0, "arm": 0},
    {"id": "head-left", "label": "고개 왼쪽 3°", "head": -3, "arm": 0},
    {"id": "head-right", "label": "고개 오른쪽 3°", "head": 3, "arm": 0},
    {"id": "greet-middle", "label": "인사 중간 18°", "head": 1.2, "arm": -18},
    {"id": "greet-peak", "label": "인사 최대 36°", "head": 1.6, "arm": -36},
    {"id": "combined", "label": "고개·팔 동시 극값", "head": -3, "arm": -36},
    {
        "id": "stress",
        "label": "범위 밖 점검 60°",
        "head": 8,
        "arm": -60,
        "outside_initial_scope": True,
    },
]
JOINTS = [
    {"name": "ArmL_JointUnderlap", "parent": "ArmL_Base", "pivot": [282, 533]},
    {"name": "ArmR_JointUnderlap", "parent": "ArmR_Base", "pivot": [337, 533]},
]


def candidate_layer(joint):
    root = ET.Element(NS + "svg", width="270", height="337", viewBox="175 315 270 337")
    group = ET.SubElement(root, NS + "g", {"data-layer": joint["name"]})
    x, y = joint["pivot"]
    # A small closed shoulder cap sits wholly behind the torso at rest. Use a
    # path so the candidate also follows the existing SVG element allowlist.
    ET.SubElement(
        group,
        NS + "path",
        {
            "d": f"M{x - 10} {y}a10 10 0 1 0 20 0a10 10 0 1 0 -20 0Z",
            "fill": "#f2efe9",
            "stroke": "#2c292a",
            "stroke-width": "3.439",
        },
    )
    return root


def posed(root, pose):
    root = copy.deepcopy(root)
    head = ET.Element(
        NS + "g",
        {
            "transform": f"rotate({pose['head']} 309.19 517)",
        },
    )
    for node in list(root):
        name = node.get("data-layer", "")
        if name.startswith(("Hood", "Face", "Eye", "Mouth")):
            root.remove(node)
            head.append(node)
        elif name in {"ArmR_Base", "ArmR_JointUnderlap"}:
            node.set("transform", f"rotate({pose['arm']} 337 533)")
    root.append(head)
    return root


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_svg(path, root):
    path.write_bytes(ET.tostring(root))
    return path


def export(args, render):
    import numpy as np
    from PIL import Image
    from psd_tools import PSDImage

    production = args.root / "assets/production"
    layers = args.root / "assets/layers"
    source = json.loads(
        (production / "handoff-manifest.json").read_text(encoding="utf-8")
    )
    if source["psd_sha256"] != digest(production / "sogangi-visible-parts.psd"):
        raise ValueError("Baseline PSD does not match its reviewed manifest")
    if len(source["parts"]) != 24 or source["canvas"]["width"] != 2048:
        raise ValueError("Regenerate/review this tool for a changed baseline")
    output = args.output
    if output.exists() and any(output.iterdir()) and not args.overwrite:
        raise ValueError("Output exists; use --overwrite for this candidate directory")
    output.mkdir(parents=True, exist_ok=True)
    for directory in ["vectors", "layers", "poses"]:
        (output / directory).mkdir(exist_ok=True)

    original = ET.parse(layers / "sogangi-visible-layers.svg").getroot()
    candidate = copy.deepcopy(original)
    candidates = {}
    for joint in JOINTS:
        root = candidate_layer(joint)
        path = write_svg(output / "vectors" / f"{joint['name']}.svg", root)
        image, png = rasterize(path, 2048, 128, render)
        (output / "layers" / f"{joint['name']}.png").write_bytes(png)
        candidates[joint["name"]] = image
        first = next(
            node for node in candidate if node.get("data-layer") == joint["parent"]
        )
        candidate.insert(
            list(candidate).index(first), copy.deepcopy(root.find(NS + "g"))
        )
    write_svg(output / "sogangi-shoulder-candidate.svg", candidate)

    neutral_images = {}
    reports = []
    for pose in POSES:
        images = []
        for label, root in [("original", original), ("candidate", candidate)]:
            path = write_svg(
                output / "poses" / f"{pose['id']}-{label}.svg", posed(root, pose)
            )
            image, png = rasterize(path, 1024, 64, render)
            (output / "poses" / f"{pose['id']}-{label}.png").write_bytes(png)
            images.append(np.asarray(image))
            if pose["id"] == "neutral":
                neutral_images[label], _ = rasterize(path, 2048, 128, render)
        before, after = images
        changed = np.any(before != after, axis=2)
        alpha_gained = (after[:, :, 3].astype(int) - before[:, :, 3].astype(int)) > 8
        reports.append(
            {
                **pose,
                "changed_pixels_1024": int(changed.sum()),
                "added_alpha_pixels_1024": int(alpha_gained.sum()),
                "judgment": "manual_review_required"
                if changed.any()
                else "no_visible_change",
            }
        )
    neutral_exact = (
        neutral_images["original"].tobytes() == neutral_images["candidate"].tobytes()
    )
    if not neutral_exact:
        raise ValueError("Candidate changes the neutral artwork; do not deliver it")

    psd = PSDImage.new("RGBA", (2048, 2048), depth=8)
    psd.background_color = None
    exported = []
    source_images = {}
    for part in source["parts"]:
        for joint in JOINTS:
            if joint["parent"] == part["name"]:
                name = joint["name"]
                image = candidates[name]
                psd.create_pixel_layer(image, name=name, top=0, left=0)
                exported.append(
                    {"name": name, "visible": True, "authored_candidate": True}
                )
        image = Image.open(production / part["file"]).convert("RGBA")
        if hashlib.sha256(image.tobytes()).hexdigest() != part["rgba_sha256"]:
            raise ValueError(f"Baseline PNG changed: {part['name']}")
        source_images[part["name"]] = image
        image.save(output / "layers" / f"{part['name']}.png")
        layer = psd.create_pixel_layer(image, name=part["name"], top=0, left=0)
        layer.visible = part["visible"]
        exported.append(
            {
                "name": part["name"],
                "visible": part["visible"],
                "authored_candidate": False,
            }
        )
    psd._record.layer_and_mask_information.layer_info.layer_count = -len(psd)
    psd_path = output / "sogangi-shoulder-candidate.psd"
    psd.save(psd_path)
    restored = PSDImage.open(psd_path)
    if len(restored) != 26 or restored.size != (2048, 2048):
        raise ValueError("Candidate PSD structure changed")
    for layer, part in zip(restored, exported):
        expected = (
            candidates[part["name"]]
            if part["authored_candidate"]
            else source_images[part["name"]]
        )
        if (
            layer.name != part["name"]
            or layer.visible != part["visible"]
            or layer.offset != (0, 0)
            or layer.topil().tobytes() != expected.tobytes()
        ):
            raise ValueError(f"Candidate PSD round-trip failed: {part['name']}")
        part["file"] = f"layers/{part['name']}.png"
        part["rgba_sha256"] = hashlib.sha256(expected.tobytes()).hexdigest()
    merged = restored.composite(force=True, color=1.0, alpha=0.0)
    baseline = PSDImage.open(production / "sogangi-visible-parts.psd").composite(
        force=True, color=1.0, alpha=0.0
    )
    psd_diff = np.abs(np.asarray(merged).astype(int) - np.asarray(baseline).astype(int))
    # psd-tools' float compositing can round an occluded layer differently by one
    # code value; report this instead of claiming exact PSD composite identity.
    psd_max_error = int(psd_diff.max())
    psd_changed = int(np.any(psd_diff, axis=2).sum())
    if psd_max_error > 1 or restored.topil().getpixel((0, 0))[3] != 0:
        raise ValueError(
            "PSD neutral composite/alpha exceeds the one-code-value tolerance"
        )
    merged.save(output / "neutral-preview.png")

    # Measure existing hidden drawing; an overlap is not a missing-art diagnosis.
    overlap = []
    for index, part in enumerate(source["parts"]):
        if part["name"] not in {"ArmL_Base", "ArmR_Base", "Face_Base", "Hood_Base"}:
            continue
        foreground = Image.new("RGBA", (2048, 2048))
        for front in source["parts"][index + 1 :]:
            if front["visible"]:
                foreground.alpha_composite(source_images[front["name"]])
        opaque = np.asarray(source_images[part["name"]])[:, :, 3] == 255
        covered = opaque & (np.asarray(foreground)[:, :, 3] == 255)
        overlap.append(
            {
                "part": part["name"],
                "opaque_pixels_2048": int(opaque.sum()),
                "fully_covered_pixels_2048": int(covered.sum()),
            }
        )
    report = {
        "schema_version": 1,
        "status": "shoulder_underlap_candidate_not_approved",
        "recommendation": "keep_baseline_for_initial_rigid_motion"
        if all(
            not pose["changed_pixels_1024"]
            for pose in reports
            if not pose.get("outside_initial_scope")
        )
        else "manual_contour_review_before_acceptance",
        "official_artwork": False,
        "cubism_import_verified": False,
        "rig_ready": False,
        "baseline_psd_sha256": source["psd_sha256"],
        "candidate_psd_sha256": digest(psd_path),
        "canvas": {"width": 2048, "height": 2048},
        "pose_preview_canvas": 1024,
        "coordinate_convention": "SVG source viewBox 175 315 270 337; L/R are screen coordinates",
        "candidate_joints": JOINTS,
        "layer_count": len(restored),
        "parts": exported,
        "verification": {
            "neutral_browser_rgba_exact_2048": neutral_exact,
            "neutral_psd_rgba_exact_2048": psd_changed == 0,
            "neutral_psd_max_channel_error_255": psd_max_error,
            "neutral_psd_changed_pixels_2048": psd_changed,
            "layer_roundtrip_exact": True,
            "baseline_layers_unchanged": True,
        },
        "existing_hidden_art": overlap,
        "poses": reports,
        "limitations": [
            "SVG rigid transforms, not Cubism mesh deformation",
            "Candidate shoulder caps are not automatically used in the conversation app",
            "No inferred repair success from added-alpha counts; inspect contours manually",
            "Face yaw, back-of-head artwork and mouth topology remain unverified",
        ],
    }
    (output / "review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "README.txt").write_text(
        "SOGANGI SHOULDER UNDERLAP CANDIDATE (NOT APPROVED)\n\n"
        "24 unchanged preparation layers + 2 authored shoulder caps. Screen L/R.\n"
        "Browser neutral RGBA matches exactly; PSD composite rounding is reported in review.json.\n"
        "Pose PNG/SVG pairs use rigid SVG transforms, not Cubism deformation.\n"
        "Review silhouette, interior outlines and clothing occlusion before accepting caps.\n"
        "Changed-pixel counts do not establish a visible defect or a successful repair.\n"
        "No Cubism import, CMO3 or MOC3 export has been performed.\n"
        "Original source rights remain with Sogang University/relevant owners:\n"
        "https://www.sogang.ac.kr/intro/symbol/data/Sogang_UI_renewal.pdf\n",
        encoding="utf-8",
    )
    allowed = [
        psd_path,
        output / "review.json",
        output / "README.txt",
        output / "neutral-preview.png",
        output / "sogangi-shoulder-candidate.svg",
        *(output / "vectors" / f"{item['name']}.svg" for item in JOINTS),
        *(output / item["file"] for item in exported),
        *(
            output / "poses" / f"{pose['id']}-{label}.{extension}"
            for pose in POSES
            for label in ["original", "candidate"]
            for extension in ["svg", "png"]
        ),
    ]
    with zipfile.ZipFile(
        output / "sogangi-shoulder-candidate.zip", "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in allowed:
            bundle.write(path, path.relative_to(output))
    print(
        json.dumps(
            {
                "verification": report["verification"],
                "poses": reports,
                "existing_hidden_art": overlap,
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("web_tool/sogangi"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("web_tool/sogangi/assets/overlap-candidates"),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    baseline = (args.root / "assets/production").resolve()
    if args.output.resolve() == baseline or baseline in args.output.resolve().parents:
        parser.error(
            "Candidate output must be separate from baseline production assets"
        )
    with BrowserRasterizer() as render:
        export(args, render)


if __name__ == "__main__":
    main()
