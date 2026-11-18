"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    so = cfg["second_opinion"]                    # mọi ngưỡng lấy từ đây
    if preds is None:                             # khi chạy thật: đọc cache dự đoán
        preds = get_preds(ds, cfg, "checker")
    issues = []

    for img in ds.image_files():                  # đúng thứ tự ảnh mà đề yêu cầu
        stem = img.stem
        lines = ds.read_label_lines(stem)         # None nếu không có file nhãn
        size = ds.image_size(stem)                # (W, H) px
        if stem not in preds or lines is None or size is None:
            continue                              # không có dự đoán / không có nhãn: bỏ qua
        W, H = size

        # Nhãn hợp lệ, giữ số dòng gốc (valid_boxes không giữ số dòng)
        labels = []                               # [(số dòng, lớp, box)]
        for ln_no, text in lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:                    # dòng hỏng: bỏ qua, không chết
                continue
            if 0 <= cls < len(ds.classes):        # id lớp lạ: bỏ qua
                labels.append((ln_no, cls, (cx, cy, w, h)))

        # Mỗi dự đoán đủ chắc, đủ lớn -> tối đa 1 cảnh báo
        for p_cls, conf, *p_box in preds[stem]:
            if conf < so["conf"] or p_box[2] * W * p_box[3] * H < so["min_area_px"]:
                continue

            cands = []                            # nhãn (mọi lớp) có IoU >= iou_missing
            for ln_no, l_cls, l_box in labels:
                iou = iou_xywh(p_box, l_box)
                if iou >= so["iou_missing"]:
                    cands.append((iou, l_cls))
            same = [iou for iou, c in cands if c == p_cls]
            other = [iou for iou, c in cands if c != p_cls]

            if not cands:                                       # (1) không nhãn nào ở đó
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy lớp {p_cls} (conf {conf:.2f}) mà nhãn không có box",
                                    extra={"conf": conf}))
            elif same:                                          # (2) có nhãn cùng lớp
                if max(same) < so["iou_loose"]:                 #     nhưng lệch -> box lỏng
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box lỏng/lệch: IoU {max(same):.2f}",
                                        extra={"conf": conf, "iou": round(max(same), 4)}))
            elif max(other) >= so["iou_match"]:                 # (3) chỉ nhãn khác lớp, trùng khít
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"model nói lớp {p_cls} (conf {conf:.2f}), nhãn ghi lớp khác",
                                    extra={"conf": conf, "iou": round(max(other), 4)}))
            # còn lại: khác lớp, IoU mơ hồ trong [iou_missing, iou_match) -> không cờ

        # Mỗi dòng nhãn không khớp dự đoán nào (conf >= fp_conf, không lọc diện tích) -> FALSE_POS
        fp_boxes = [p[2:] for p in preds[stem] if p[1] >= so["fp_conf"]]
        for ln_no, l_cls, l_box in labels:
            if all(iou_xywh(l_box, pb) < so["iou_missing"] for pb in fp_boxes):
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    "box nhãn không khớp vật nào model thấy", line=ln_no))

    return issues
