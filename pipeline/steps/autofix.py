"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}       # lỗi -> xoá dòng
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}                # lỗi -> xoá ảnh (cùng DUP_IMAGE_*)


def _clip(text):
    """Cắt box về trong [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích."""
    cls, cx, cy, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)     # kẹp mép trái/phải vào [0,1]
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)     # kẹp mép trên/dưới
    if x2 <= x1 or y2 <= y1:                                # box nằm hẳn ngoài ảnh
        return None
    return f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]     # không động tới WARN
    fixes = []

    # 1) Xoá ảnh hỏng / trùng / rò rỉ (cả ảnh lẫn nhãn)
    removed = set()
    for i in errors:
        is_remove = i.code in REMOVE_CODES or i.code.startswith("DUP_IMAGE_")
        if not is_remove or i.image in removed:
            continue
        img = ds.image_path(i.image)
        if img is not None:
            img.unlink()                                    # xoá file ảnh
        lab = ds.label_path(i.image)
        if lab.exists():
            lab.unlink()                                    # xoá file nhãn
        removed.add(i.image)
        fixes.append({"image": i.image, "line": "", "action": "remove_image",
                      "before": img.name if img else i.image, "after": f"(đã xoá, lý do {i.code})"})

    # 2) Tên lớp sai -> ghi lại đúng cfg["classes"]
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        before = d.get("names")
        d["names"] = list(cfg["classes"])
        ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        fixes.append({"image": "data.yaml", "line": "", "action": "rename_classes",
                      "before": str(before), "after": str(d["names"])})

    # 3) Thiếu file nhãn -> máy không bịa nhãn, chuyển người gán
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed:
            fixes.append({"image": i.image, "line": "", "action": "needs_label",
                          "before": "(không có file)", "after": "chuyển người gán"})

    # 4) Gom lỗi: stem -> số dòng -> {các mã lỗi}
    by_file = defaultdict(lambda: defaultdict(set))
    for i in errors:
        if i.line and (i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE"):
            by_file[i.image][int(i.line)].add(i.code)

    for stem in sorted(by_file):
        lab = ds.label_path(stem)
        if stem in removed or not lab.exists():             # ảnh đã xoá: bỏ qua êm
            continue
        bad = by_file[stem]
        new_lines = []
        # enumerate(..., 1) đếm cả dòng trống -> khớp số dòng gốc trong issue
        for ln_no, text in enumerate(lab.read_text(encoding="utf-8").splitlines(), 1):
            codes = bad.get(ln_no)
            if not codes:                                   # dòng không lỗi: giữ nguyên
                new_lines.append(text)
                continue
            if codes & DROP_CODES:                          # có lỗi cần xoá -> xoá thắng clip
                fixes.append({"image": stem, "line": ln_no, "action": "drop_line",
                              "before": text, "after": ""})
                continue
            try:                                            # chỉ còn BOX_OUT_OF_IMAGE -> cắt
                clipped = _clip(text)
            except ValueError:
                clipped = None
            if clipped is None:                             # cắt xong không còn diện tích
                fixes.append({"image": stem, "line": ln_no, "action": "drop_line",
                              "before": text, "after": ""})
            else:
                new_lines.append(clipped)
                fixes.append({"image": stem, "line": ln_no, "action": "clip_box",
                              "before": text, "after": clipped})
        lab.write_text("".join(l + "\n" for l in new_lines), encoding="utf-8")   # ghi MỘT lần

    return fixes

