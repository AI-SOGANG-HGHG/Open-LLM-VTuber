"""Check exported Cubism 3 files and the Sogangi handoff contract.

This is a static file/reference check, not a Cubism renderer or MOC3 parser.
"""

import argparse
import json
from pathlib import Path, PureWindowsPath
import sys


def check_bundle(model_path, *, sogangi=False, model_entry=None):
    model_path = Path(model_path).resolve()
    root = model_path.parent
    errors, warnings, checked = [], [], []

    def reference(value, label):
        if (
            not isinstance(value, str)
            or not value
            or any(char in value for char in ("\\", "\0", "?", "#"))
            or ":" in value
            or Path(value).is_absolute()
            or PureWindowsPath(value).drive
        ):
            errors.append(f"{label}: expected a relative file path")
            return None
        try:
            path = (root / value).resolve()
            path.relative_to(root)
        except (OSError, ValueError):
            errors.append(f"{label}: path leaves the model bundle")
            return None
        try:
            exists = path.is_file()
        except OSError:
            exists = False
        if not exists:
            errors.append(f"{label}: missing {value}")
            return None
        checked.append(value)
        return path

    def signature(path, expected, label):
        try:
            with path.open("rb") as source:
                if source.read(len(expected)) != expected:
                    errors.append(f"{label}: invalid file signature")
        except OSError:
            errors.append(f"{label}: cannot read file")

    def read_json(path, label):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"{label}: cannot read valid JSON")
            return None

    model = read_json(model_path, "model3.json")
    if not isinstance(model, dict):
        return {
            "ok": False,
            "errors": errors or ["model3.json must be an object"],
            "warnings": warnings,
            "checked_files": checked,
        }
    if model.get("Version") != 3:
        errors.append("Expected model3.json Version 3")
    refs = model.get("FileReferences")
    if not isinstance(refs, dict):
        return {
            "ok": False,
            "errors": [*errors, "FileReferences is missing"],
            "warnings": warnings,
            "checked_files": checked,
        }
    moc = reference(refs.get("Moc"), "Moc")
    if moc:
        signature(moc, b"MOC3", "Moc")
    textures = refs.get("Textures")
    if not isinstance(textures, list) or not textures:
        errors.append("Textures must contain at least one image")
    else:
        for value in textures:
            path = reference(value, "Texture")
            if path and path.suffix.lower() == ".png":
                signature(path, b"\x89PNG\r\n\x1a\n", "Texture")
    display = None
    for key in ("Physics", "Pose", "DisplayInfo"):
        if key in refs:
            path = reference(refs[key], key)
            if path:
                data = read_json(path, key)
                if key == "DisplayInfo":
                    display = data
    expressions = refs.get("Expressions", [])
    if not isinstance(expressions, list):
        errors.append("Expressions must be an array")
        expressions = []
    names = []
    for item in expressions:
        if not isinstance(item, dict):
            errors.append("Expression entry must be an object")
            continue
        if not isinstance(item.get("Name"), str) or not item["Name"]:
            errors.append("Expression Name must be a nonempty string")
        else:
            names.append(item["Name"])
        path = reference(item.get("File"), "Expression")
        if path:
            read_json(path, "Expression")
    if len(names) != len(set(names)):
        errors.append("Expression names must be unique")
    motions = refs.get("Motions", {})
    if not isinstance(motions, dict):
        errors.append("Motions must be an object")
        motions = {}
    for group, entries in motions.items():
        if not isinstance(entries, list):
            errors.append(f"Motion {group}: expected an array")
            continue
        for item in entries:
            if not isinstance(item, dict):
                errors.append(f"Motion {group}: entry must be an object")
                continue
            path = reference(item.get("File"), f"Motion {group}")
            if path:
                read_json(path, f"Motion {group}")
            if item.get("Sound"):
                reference(item["Sound"], f"Motion {group} sound")
    raw_groups = model.get("Groups", [])
    if not isinstance(raw_groups, list):
        errors.append("Groups must be an array")
        raw_groups = []
    groups = {}
    for item in raw_groups:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("Name"), str)
            or not isinstance(item.get("Ids"), list)
            or not all(isinstance(value, str) for value in item["Ids"])
        ):
            errors.append("Group must have a name and an array of string Ids")
            continue
        if item["Name"] in groups:
            errors.append("Group names must be unique")
        groups[item["Name"]] = item["Ids"]
    if sogangi:
        expected = ["neutral", "joy", "sadness", "surprise", "anger"]
        if names[:5] != expected:
            errors.append(
                "Sogangi expression order must start with: " + ", ".join(expected)
            )
        for group, ids in {
            "EyeBlink": ["ParamEyeLOpen", "ParamEyeROpen"],
            "LipSync": ["ParamMouthOpenY"],
        }.items():
            if not all(value in groups.get(group, []) for value in ids):
                errors.append(f"Sogangi {group} group must include {', '.join(ids)}")
        if not motions.get("Idle"):
            errors.append("Sogangi requires an Idle motion group")
    elif not groups.get("LipSync"):
        warnings.append("No LipSync group is declared")
    if isinstance(display, dict) and isinstance(display.get("Parameters"), list):
        declared = {
            item.get("Id")
            for item in display["Parameters"]
            if isinstance(item, dict) and isinstance(item.get("Id"), str)
        }
        for name, ids in groups.items():
            for value in ids:
                if value not in declared:
                    warnings.append(
                        f"{name}: {value} is absent from DisplayInfo; verify in the real model"
                    )
    if model_entry is not None:
        if not isinstance(model_entry, dict) or not isinstance(
            model_entry.get("emotionMap", {}), dict
        ):
            errors.append("model_dict entry and emotionMap must be objects")
            model_entry = {}
        for emotion, index in model_entry.get("emotionMap", {}).items():
            if type(index) is not int or not 0 <= index < len(expressions):
                errors.append(f"emotionMap {emotion}: index outside Expressions array")
        idle = model_entry.get("idleMotionGroupName")
        if idle and (not isinstance(idle, str) or idle not in motions):
            errors.append("idleMotionGroupName is not present in the model")
    warnings.append(
        "Static checks do not validate MOC3 internals, Cubism Core compatibility, visual deformation or lip sync; run the actual browser model"
    )
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_files": checked,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--sogangi", action="store_true")
    parser.add_argument("--model-dict", type=Path)
    parser.add_argument("--name")
    args = parser.parse_args()
    if bool(args.model_dict) != bool(args.name):
        parser.error("Provide --model-dict and --name together")
    entry = None
    if args.model_dict:
        try:
            entries = json.loads(args.model_dict.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            parser.error("Cannot read model_dict JSON")
        if not isinstance(entries, list):
            parser.error("model_dict must be an array")
        found = [
            item
            for item in entries
            if isinstance(item, dict) and item.get("name") == args.name
        ]
        if len(found) != 1:
            parser.error("Expected exactly one matching model_dict entry")
        entry = found[0]
    result = check_bundle(args.model, sogangi=args.sogangi, model_entry=entry)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
