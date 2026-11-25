"""Generate a rigging/underpainting review map bound to the real preparation PSD."""

import hashlib
import json
from pathlib import Path


def main():
    from PIL import Image

    base = Path("web_tool/sogangi")
    art = base / "assets/production"
    handoff = json.loads((art / "handoff-manifest.json").read_text(encoding="utf-8"))
    psd = art / "sogangi-visible-parts.psd"
    if hashlib.sha256(psd.read_bytes()).hexdigest() != handoff["psd_sha256"]:
        raise ValueError("PSD and handoff manifest do not match")
    size = handoff["canvas"]["width"]
    margin = handoff["canvas"]["margin"]
    scale = (size - 2 * margin) / 337
    left = (size - 270 * scale) / 2

    def point(x, y):
        return [
            round(left + (x - 175) * scale, 2),
            round(margin + (y - 315) * scale, 2),
        ]

    def bounds(x, y, width, height):
        return [*point(x, y), round(width * scale, 2), round(height * scale, 2)]

    parts = []
    for part in handoff["parts"]:
        path = art / part["file"]
        with Image.open(path) as image:
            if hashlib.sha256(image.tobytes()).hexdigest() != part["rgba_sha256"]:
                raise ValueError("PNG does not match the verified PSD layer")
            box = image.getchannel("A").getbbox()
        if box is None:
            raise ValueError("Empty preparation layer")
        parts.append(
            {
                "id": part["name"],
                "label": part["name"],
                "bounds": [box[0], box[1], box[2] - box[0], box[3] - box[1]],
                "visible": part["visible"],
                "note": "PSD에 실제 있는 레이어의 투명도 경계입니다. 가려진 부분을 이어 그린 완성 원화는 아닙니다.",
            }
        )
    ids = [part["id"] for part in parts]
    upper = [name for name in ids if not name.startswith("Leg")]
    head = [name for name in ids if name.startswith(("Hood", "Face", "Eye", "Mouth"))]
    deformers = []
    for id, label, parent, pivot, affected, note in [
        (
            "Root",
            "전체 기준",
            "",
            (309.19, 645.4),
            ids,
            "발의 기준선과 화면 배치 기준. Idle에서 전체를 위아래로 띄우지 않습니다.",
        ),
        (
            "BodyBreath",
            "상체 호흡",
            "Root",
            (309.19, 626.8),
            upper,
            "다리는 유지하고 몸통·팔·머리의 작은 호흡을 함께 조정합니다.",
        ),
        (
            "BodyTilt",
            "몸 기울기",
            "BodyBreath",
            (309.19, 617),
            upper,
            "의상·문양은 같은 변형 계층에 둡니다. 발 접지와 허리 경계는 원화 보완 후 검수합니다.",
        ),
        (
            "HeadTurn",
            "머리·후드",
            "BodyTilt",
            (309.19, 517),
            head,
            "얼굴·후드·새 눈·부리·눈·입의 상대 위치를 유지합니다. 목과 후드 아래 틈을 먼저 보완합니다.",
        ),
        (
            "ArmLWave",
            "화면 왼팔",
            "BodyTilt",
            (282, 533),
            ["ArmL_Base"],
            "어깨 피벗은 검토용 초안입니다. 팔 안쪽의 가려진 부분을 보완한 뒤 확정합니다.",
        ),
        (
            "ArmRWave",
            "화면 오른팔 인사",
            "BodyTilt",
            (337, 533),
            ["ArmR_Base"],
            "현재 SVG 인사는 화면 오른팔을 사용합니다. ParamArmRWave와 연결하고 어깨 접합을 검수합니다.",
        ),
        (
            "EyeL",
            "화면 왼눈",
            "HeadTurn",
            (268.44, 446.57),
            [name for name in ids if name.startswith("EyeL_")],
            "검은 눈·하이라이트·감은 눈 후보를 함께 정렬합니다. 중간 닫힘 모양은 검토가 필요합니다.",
        ),
        (
            "EyeR",
            "화면 오른눈",
            "HeadTurn",
            (349.95, 446.57),
            [name for name in ids if name.startswith("EyeR_")],
            "좌우 눈을 독립 조작해 완전 닫힘과 반사광 잔상을 확인합니다.",
        ),
        (
            "Mouth",
            "입",
            "HeadTurn",
            (309.19, 493),
            [name for name in ids if name.startswith("Mouth_")],
            "닫힘/열림 두 후보만 있습니다. 중간 벌림과 입 모양 원화를 보완해야 합니다.",
        ),
    ]:
        deformers.append(
            {
                "id": id,
                "label": label,
                "parent": parent or None,
                "pivot": point(*pivot),
                "source_svg_pivot": list(pivot),
                "parts": affected,
                "note": note,
                "status": "proposed_for_artist_review",
            }
        )
    zones = []
    for id, label, rect, affected, note in [
        (
            "face-hood",
            "얼굴·후드 겹침",
            (219, 366, 182, 170),
            ["Face_Base", "Hood_Base"],
            "좌우 회전 시 드러나는 얼굴/후드 안쪽을 검토합니다. 경계선이 벌어지거나 두 겹으로 보이지 않도록 겹침 여유를 보완합니다.",
        ),
        (
            "shoulder-left",
            "왼쪽 어깨",
            (242, 504, 46, 50),
            ["ArmL_Base", "Body_Tunic"],
            "팔이 움직여도 어깨가 끊어지지 않도록 의상 아래까지 연장해 그릴 영역입니다.",
        ),
        (
            "shoulder-right",
            "오른쪽 어깨",
            (330, 504, 47, 50),
            ["ArmR_Base", "Body_Tunic"],
            "인사 끝 자세에서 팔이 머리 뒤로 사라지거나 어깨에서 떨어져 보이는지 확인합니다.",
        ),
        (
            "mouth-shapes",
            "입의 중간 원화",
            (282, 478, 55, 35),
            ["Mouth_Closed", "Mouth_Open"],
            "작은 벌림·큰 벌림 사이의 모양과 웃는 입 형태를 보완합니다. 두 이미지를 단순 교체하는 것으로 리깅 완료 판정하지 않습니다.",
        ),
        (
            "eyes",
            "눈 닫힘 중간 형태",
            (246, 422, 126, 39),
            [name for name in ids if name.startswith("Eye")],
            "검은 눈이 얇아지는 중간 형태와 감은 눈 곡선의 연결, 반사광 숨김을 검수합니다.",
        ),
        (
            "tunic",
            "의상 문양과 다리 경계",
            (240, 516, 138, 126),
            ["Body_Tunic", "Body_Stripe", "Body_Emblem", "LegL_Base", "LegR_Base"],
            "문양은 몸통과 같은 변형 계층으로 유지합니다. 상체 기울기에서 의상 아래 다리와 발이 어색하게 분리되지 않도록 겹침을 검수합니다.",
        ),
    ]:
        zones.append(
            {
                "id": id,
                "label": label,
                "bounds": bounds(*rect),
                "parts": affected,
                "note": note,
                "status": "review_and_underpaint_required",
            }
        )
    bindings = [
        {
            "parameter": "ParamAngleX",
            "deformer": "HeadTurn",
            "initial_keys": [-10, 0, 10],
            "note": "단위는 파라미터 값입니다. 큰 회전은 가림 보완 후 확장합니다.",
        },
        {
            "parameter": "ParamAngleY",
            "deformer": "HeadTurn",
            "initial_keys": [-10, 0, 10],
            "note": "얼굴·후드·부리 원근과 안쪽 원화를 함께 검수합니다.",
        },
        {
            "parameter": "ParamAngleZ",
            "deformer": "HeadTurn",
            "initial_keys": [-5, 0, 5],
            "note": "작은 기울기로 시작해 후드/목 경계가 유지되는지 확인합니다.",
        },
        {
            "parameter": "ParamEyeLOpen",
            "deformer": "EyeL",
            "initial_keys": [0, 0.5, 1],
            "note": "감음·중간·열림을 따로 검수합니다.",
        },
        {
            "parameter": "ParamEyeROpen",
            "deformer": "EyeR",
            "initial_keys": [0, 0.5, 1],
            "note": "감음·중간·열림을 따로 검수합니다.",
        },
        {
            "parameter": "ParamMouthOpenY",
            "deformer": "Mouth",
            "initial_keys": [0, 0.3, 0.65, 1],
            "note": "음성 크기와 연결. 종료/중단 시 0으로 돌아옵니다.",
        },
        {
            "parameter": "ParamMouthForm",
            "deformer": "Mouth",
            "initial_keys": [-1, 0, 1],
            "note": "새 중간 원화와 입 모양 검토 후 제작합니다.",
        },
        {
            "parameter": "ParamBreath",
            "deformer": "BodyBreath",
            "initial_keys": [0, 1],
            "note": "상체의 작은 호흡. 발은 유지합니다.",
        },
        {
            "parameter": "ParamBodyAngleZ",
            "deformer": "BodyTilt",
            "initial_keys": [-3, 0, 3],
            "note": "문양과 다리 접합을 먼저 검수합니다.",
        },
        {
            "parameter": "ParamArmRWave",
            "deformer": "ArmRWave",
            "initial_keys": [0, 0.5, 1],
            "note": "화면 오른팔 인사. PSD 좌우 명명 규칙과 일치시킵니다.",
        },
    ]
    spec = json.loads((base / "workshop/live2d-plan/live2d-spec.json").read_text(encoding="utf-8"))
    known = {item["id"]: item for item in spec["parameters"]}
    for binding in bindings:
        parameter = known[binding["parameter"]]
        if any(
            not parameter["min"] <= value <= parameter["max"]
            for value in binding["initial_keys"]
        ):
            raise ValueError("Key exceeds parameter range")
    report = {
        "schema_version": 1,
        "status": "rigging_design_not_cubism_project",
        "psd_sha256": handoff["psd_sha256"],
        "canvas": {
            "width": size,
            "height": size,
            "coordinate_system": "PSD pixels; origin top-left; L/R use screen coordinates",
        },
        "preview": "./assets/production/neutral-preview.png",
        "parts": parts,
        "deformers": deformers,
        "underpainting": zones,
        "bindings": bindings,
        "scope": "Visible-layer bounds are measured; pivots, deformation hierarchy and repair zones are review proposals. No underpainting or Cubism mesh has been completed.",
    }
    (base / "workshop/rigging-map/rigging-map.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "parts": len(parts),
                "deformers": len(deformers),
                "underpainting_zones": len(zones),
                "parameter_bindings": len(bindings),
            }
        )
    )


if __name__ == "__main__":
    main()
