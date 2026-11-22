"""Export the Ivory Crown Canvas draft as a layered PSD using Chromium."""

import argparse
import base64
import io
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from psd_tools import PSDImage
from psd_tools.api.layers import Group


ROOT = Path(__file__).resolve().parent
SIZE = (1024, 1536)
GROUPS = {"EyeL": "Eye L", "EyeR": "Eye R", "Mouth": "Mouth"}


def read_layers(executable):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=executable, args=["--allow-file-access-from-files"]
        )
        try:
            page = browser.new_page()
            page.goto((ROOT / "index.html").as_uri())
            page.locator("#pose:enabled").wait_for()
            return page.evaluate(
                """() => rig.layers().map(({canvas, ...part}) => ({
                    ...part,
                    png: canvas.toDataURL('image/png').split(',')[1],
                }))"""
            )
        finally:
            browser.close()


def write_psd(parts, destination):
    psd = PSDImage.new("RGBA", SIZE, depth=8)
    psd.background_color = None
    groups = {}
    expected = {}
    for part in parts:
        name = part["name"]
        prefix = name.split("_", 1)[0]
        with Image.open(io.BytesIO(base64.b64decode(part["png"]))) as image:
            pixels = image.convert("RGBA")
        layer = psd.create_pixel_layer(pixels, name=name, left=part["x"], top=part["y"])
        layer.visible = part["visible"]
        group_name = GROUPS.get(prefix)
        if group_name:
            if group_name not in groups:
                groups[group_name] = Group.new(psd, name=group_name)
            groups[group_name].append(layer)
        expected[name] = (pixels, (part["x"], part["y"]), part["visible"], group_name)

    # Match the team's PSD exporter and preserve transparent merged-image alpha.
    layer_info = psd._record.layer_and_mask_information.layer_info
    layer_info.layer_count = -len(layer_info.layer_records)
    result = io.BytesIO()
    psd.save(result)
    result.seek(0)
    restored = PSDImage.open(result)
    if restored.size != SIZE or restored.depth != 8:
        raise ValueError("PSD canvas size or bit depth changed")
    if restored.topil().getpixel((0, 0))[3] != 0:
        raise ValueError("PSD compatibility preview lost transparency")
    layers = [layer for layer in restored.descendants() if not layer.is_group()]
    if len(layers) != 7 or {layer.name for layer in layers} != expected.keys():
        raise ValueError("PSD layer names or count changed")
    for layer in layers:
        pixels, offset, visible, group_name = expected[layer.name]
        actual_group = None if layer.parent is restored else layer.parent.name
        if (layer.offset, layer.visible, actual_group) != (offset, visible, group_name):
            raise ValueError(
                f"PSD layer coordinate, visibility or group changed: {layer.name}"
            )
        if ImageChops.difference(pixels, layer.topil()).getbbox(alpha_only=False):
            raise ValueError(f"PSD layer pixels changed: {layer.name}")

    with destination.open("xb") as file:
        file.write(result.getbuffer())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "ivory-crown-facial-draft.psd"
    )
    parser.add_argument("--chromium", help="Use an existing Chromium executable")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Choose a new output path; {args.output} already exists")
    write_psd(read_layers(args.chromium), args.output)
    print(f"Verified 7 layers and alpha transparency in {args.output}")


if __name__ == "__main__":
    main()
