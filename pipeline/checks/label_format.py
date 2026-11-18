"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    # --- Bước 1: đọc ngưỡng từ cfg (không viết cứng số) ---
    lf = cfg["label_format"]
    tol = lf["overflow_tol"]          # mức tràn cho phép
    min_px = lf["min_box_px"]         # cạnh ngắn tối thiểu (px)
    max_frac = lf["max_box_frac"]     # diện tích tối đa (tỉ lệ ảnh)
    dup_iou = lf["dup_box_iou"]       # IoU để coi 2 box là trùng
    n_cls = len(ds.classes)           # số lớp hợp lệ
    issues = []

    for p in ds.label_files():                    # mỗi file nhãn .txt
        stem = p.stem                             # tên ảnh không đuôi
        size = ds.image_size(stem)                # (rộng, cao) px hoặc None
        kept = []                                 # box hợp lệ đã gặp, để bắt DUP_BOX
        for ln_no, text in ds.read_label_lines(stem) or []:   # (số dòng gốc, nội dung)

            # --- Bước 2: 3 lỗi làm hỏng cả dòng -> báo rồi continue ---
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    f"dòng sai định dạng: {e}", line=ln_no))
                continue
            if not (0 <= cls < n_cls):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {cls} ngoài 0..{n_cls - 1}", line=ln_no))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    "box có w hoặc h <= 0", line=ln_no))
                continue

            # --- Bước 3: box tràn ảnh, box trùng ---
            x1, x2 = cx - w / 2, cx + w / 2       # mép trái, phải
            y1, y2 = cy - h / 2, cy + h / 2       # mép trên, dưới
            overflow = max(0 - x1, x2 - 1, 0 - y1, y2 - 1, 0)
            if overflow > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {overflow:.4f}", line=ln_no,
                                    extra={"overflow": round(overflow, 6)}))

            box = (cx, cy, w, h)
            for k_cls, k_box in kept:             # so với các dòng TRƯỚC
                if k_cls == cls and iou_xywh(box, k_box) > dup_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                        "box trùng với một dòng trước", line=ln_no))
                    break
            kept.append((cls, box))

            # --- Bước 4: 2 cảnh báo cho người xem ---
            if size is not None:
                W, H = size
                short = min(w * W, h * H)         # cạnh ngắn, tính bằng px
                if short < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn {short:.1f}px < {min_px}px", line=ln_no))
            if w * h > max_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"box chiếm {w * h:.0%} ảnh", line=ln_no))

    return issues
