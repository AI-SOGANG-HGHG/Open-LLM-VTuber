"""Fetch pinned browser preview libraries from npm; verify integrity and retain notices."""

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def download(url):
    request = Request(url, headers={"User-Agent": "Sogangi-local-preview-setup"})
    with urlopen(request, timeout=30) as response:
        data = response.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("Unexpected download size")
    return data


def main():
    output = Path("web_tool/shared/vendor")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for name, version, member, target in [
        ("pixi.js", "6.5.10", "package/dist/browser/pixi.min.js", "pixi.min.js"),
        (
            "pixi-live2d-display",
            "0.4.0",
            "package/dist/cubism4.min.js",
            "cubism4.min.js",
        ),
    ]:
        metadata = json.loads(download(f"https://registry.npmjs.org/{name}/{version}"))
        if (
            metadata.get("name") != name
            or metadata.get("version") != version
            or metadata.get("license") != "MIT"
        ):
            raise ValueError("Unexpected package metadata")
        url = metadata["dist"]["tarball"]
        if (
            urlparse(url).scheme != "https"
            or urlparse(url).hostname != "registry.npmjs.org"
        ):
            raise ValueError("Unexpected package registry")
        archive = download(url)
        algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
        actual = base64.b64encode(hashlib.new(algorithm, archive).digest()).decode()
        if actual != expected:
            raise ValueError("Package integrity mismatch")
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
            code = package.extractfile(member).read()
            notice = package.extractfile("package/LICENSE").read()
        (output / target).write_bytes(code)
        (output / (name + ".LICENSE.txt")).write_bytes(notice)
        records.append(
            {
                "package": name,
                "version": version,
                "tarball": url,
                "npm_integrity": metadata["dist"]["integrity"],
                "file": target,
                "sha256": hashlib.sha256(code).hexdigest(),
            }
        )
    framework_url = (
        "https://raw.githubusercontent.com/Live2D/CubismWebFramework/4bbfb54/LICENSE.md"
    )
    (output / "CubismFramework.NOTICE.md").write_bytes(download(framework_url))
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "packages": records,
                "cubism_framework_notice_source": framework_url,
                "core": "Existing /libs/live2dcubismcore.min.js from frontend; not copied here",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"files": [item["file"] for item in records], "integrity_verified": True}
        )
    )


if __name__ == "__main__":
    main()
