# Báo cáo Day 09 — Lâm Trung Hiếu, 03048

## 1. Kết luận trước
**HOLD** (mã thoát 10). Vào **224 ảnh**; bước nhận loại **22 ảnh** (2 hỏng, 3 quá nhỏ, 8 trùng byte, 4 trùng gần đúng, 5 rò rỉ tập test); **202 ảnh** đi tiếp và được xuất vào `submission/export/clean_v1/` dưới dạng **bản nháp, chưa phát hành**.
Không còn lỗi bắt buộc (0 ERROR sau vòng 3), nhưng **38/202 ảnh (18,8%)** còn cảnh báo mà người chưa duyệt, vượt ngưỡng 10%: hàng đợi có 125 ảnh còn ngân sách duyệt chỉ có 80.

## 2. Lỗi và phân việc
Số liệu lấy từ `02_error_list_v1` (trước sửa, quét 202 ảnh; riêng các mã của bước nhận tính trên 224 ảnh), `03_fixes.csv`, `05_review_queue.csv`.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| CORRUPT_IMAGE | 2 ảnh / 224 | máy (loại ảnh) | không mở/decode được, không thể dùng |
| BAD_SIZE | 3 ảnh / 224 | máy (loại ảnh) | cạnh ngắn < 250 px theo guideline |
| DUP_IMAGE_EXACT | 8 ảnh / 224 | máy (loại ảnh) | trùng md5, giữ 1 bản |
| DUP_IMAGE_NEAR | 4 ảnh / 224 | máy (loại ảnh) | pHash ≤ 12 (đã mở xem cả 4 cặp: đều trùng thật) |
| LEAK_TEST | 5 ảnh / 224 | máy (loại ảnh) | trùng ảnh tập test → giữ lại sẽ thổi phồng mAP |
| BAD_CLASS_NAME | 2 tên (data.yaml) | máy (`rename_classes`) | `Person`, `Bus` → sửa theo `classes` cố định |
| BAD_CLASS_ID | 6 dòng | máy (`drop_line`) | id 93/−1/7/4 không có nghĩa, không đoán được lớp đúng |
| BAD_FORMAT | 3 dòng | máy (`drop_line`) | nan hoặc thiếu cột |
| BOX_ZERO | 4 dòng | máy (`drop_line`) | box không có diện tích |
| DUP_BOX | 7 dòng | máy (`drop_line`) | cùng lớp, IoU > 0,9 với dòng trước |
| BOX_OUT_OF_IMAGE | 8 dòng | máy (`clip_box`) | tràn 0,023–0,06; cắt về [0,1], giữ lớp |
| MISSING_LABEL_FILE | 6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn; file rỗng = "ảnh nền", khác "chưa gán" |
| POSSIBLE_MISSING | 53 | người | ý nghĩa: model lớn thấy vật mà nhãn không có |
| POSSIBLE_FALSE_POS | 29 | người | box nhãn không khớp vật nào model thấy |
| POSSIBLE_LOOSE_BOX | 28 | người | đúng vật, box lệch/lỏng |
| POSSIBLE_WRONG_CLASS | 18 | người | model và nhãn khác lớp ở cùng chỗ |
| EMPTY_LABEL / BOX_TINY / BOX_HUGE / CLASS_RARE | 12 / 6 / 3 / 4 | người | cảnh báo quy tắc, cần mắt người xác nhận |

Máy ghi **35 thay đổi** trong `03_fixes.csv` (20 `drop_line`, 8 `clip_box`, 1 `rename_classes`, 6 `needs_label`), mỗi dòng có trước → sau; `data/raw` không bị sửa.
Hệ quả phụ của tự sửa, thấy được ở `04_error_list_v2`: `EMPTY_LABEL` tăng 12 → 15 (xoá hết dòng của 3 file) và `BOX_TINY` 6 → 7 (cắt box tràn làm một box hẹp lại). Vì vậy autofix chỉ chạy trên lỗi cú pháp, còn kết quả sau sửa vẫn quay lại QC.

**Hàng đợi.** `05_review_queue.csv` xếp theo điểm = tổng các cảnh báo của ảnh, mỗi cảnh báo tính `trọng số × (1 + conf của model)` (`review.weights`). Đầu hàng là `img_0020` (11,5: vừa bị xoá dòng id 93, vừa có MISSING và WRONG_CLASS), rồi đến 6 ảnh `NEEDS_LABEL` (trọng số 10, vì thiếu nhãn là lỗi bắt buộc chặn Release). Tiếp theo là các ảnh có WRONG_CLASS (3) và MISSING (2).
Với ngân sách 80/125 ảnh, người xem hết 6 ảnh thiếu nhãn và các ảnh ưu tiên cao: MISSING giảm 53 → 13, WRONG_CLASS 18 → 3, LOOSE_BOX 28 → 20, FALSE_POS 24 → 21 (`04` → `07`). Còn **45 ảnh** trong hàng đợi chưa ai xem.

## 3. Calibration (2 ngưỡng)
P/R đo trên `data/calib` (39 ảnh, đáp án `MANIFEST.csv`), trích từ `calibration_report.md` trước và sau khi đổi cấu hình.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | DUP_IMAGE_NEAR 1,00/0,50 → 1,00/0,67 | Lỗi ERROR ⇒ ảnh bị **xoá**, nên ưu tiên precision. Từ 4 đến 14, recall trên calib như nhau (0,67), nhưng trên raw thì 12 bắt thêm cặp `img_0186`/`img_0061` (cắt ảnh, dist 10) mà 8 bỏ sót, và không xoá nhầm ảnh nào (đã mở xem cả 4 cặp NEAR và 5 cặp LEAK). |
| `second_opinion.conf` | 0.25 | **0.6** | WRONG_CLASS 0,56/0,83 → 0,62/0,83 · MISSING 0,50/1,00 → 0,57/1,00 · LOOSE_BOX 0,29/0,40 → 0,20/0,20 · FALSE_POS 0,31/1,00 (không đổi) | Cảnh báo cho người nên giữ recall. 0,6 là giá trị cao nhất mà recall của MISSING vẫn là 1,00 (lên 0,7 thì còn 0,88, lên 0,8 còn 0,75). Precision tăng nên hàng đợi trên raw giảm 143 → 125. Chấp nhận LOOSE_BOX mất recall (0,40 → 0,20) vì lỗi này có trọng số thấp (1,5 so với 3 và 2) và calib chỉ có 5 ca. |

**Calibration có thể đánh lừa ở đâu.** Trên calib, `phash_dist = 16` đẹp nhất (NEAR 1,00/0,83). Nhưng chạy trên raw thì số ảnh bị loại nhảy từ 9 lên 18 (NEAR 4 → 7, LEAK 5 → 11). Mở xem thì thấy toàn cặp **khác nhau**: `img_0011` (tennis) bị coi là trùng `img_0008` (trượt tuyết), `img_0177` (lướt sóng) trùng `img_0113` (người ngồi bàn), `img_0013` bị coi là rò rỉ `test_087`. Precision 1,00 trên calib chỉ dựa vào 6 ca NEAR. Đây là lý do mình không chọn 16.
Tương tự, `conf = 0.8` cho kết luận **Release** trên raw (hàng đợi 102), nhưng đó là vì checker "mù" bớt (recall MISSING 0,75), chứ dữ liệu không sạch hơn. Đây là Release giả, nên mình không chọn.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn thật.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`. Không có người duyệt nên 6 ảnh `MISSING_LABEL_FILE` vẫn còn. Kết quả: `REWORK — còn 6 lỗi bắt buộc (ERROR): phải sửa trước khi xuất`, **mã thoát 20**, log in `KHÔNG xuất: còn lỗi bắt buộc (Rework)`, và thư mục `work/exp_nb` **không được tạo**. Ngược lại, ở lần chạy chính, người đã gán 6 ảnh đó nên 0 ERROR, và gate chuyển sang xét tỉ lệ cảnh báo, ra Hold.
Unit test `test_error_cannot_be_hidden_by_reviewed` bảo đảm lỗi ERROR không bị bỏ qua kể cả ở ảnh đã duyệt.

**(b) Điểm mù có bằng chứng:**
1. **Ảnh trùng bị biến đổi mạnh lọt qua.** `img_0084` và `img_0074` là cùng một cảnh (người cầm ô trắng, bị cắt/thu nhỏ) nhưng pHash = 16 > 12, nên cả hai đều vào dataset. Nâng ngưỡng lên 16 thì lại xoá nhầm 3+ ảnh khác (mục 3), nên không có ngưỡng pHash nào vừa bắt được cặp này vừa không xoá nhầm.
2. **Box lỏng nhẹ.** Recall của LOOSE_BOX trên calib chỉ 0,20 (bắt 1/5). Sau người duyệt vẫn còn 20 cảnh báo LOOSE_BOX ở ảnh chưa xem, và những box lệch nhẹ (IoU ≥ 0,5) thì không bị cờ chút nào.
3. **Nhầm lớp mà model lớn cũng nhầm** (car/truck/bus giống nhau): second_opinion chỉ cờ khi model **khác** nhãn. Nếu cả nhãn lẫn yolo26l cùng gọi một chiếc truck là car thì không có cảnh báo. Calib có 1/6 WRONG_CLASS bị bỏ sót (recall 0,83), và lớp truck/bus chỉ có 41/32 box (`class_stats.csv`), nên rất khó phát hiện.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy tại thời điểm commit này. Phần train chạy trên Google Colab (máy cá nhân không có GPU): yolo26n, 20 epoch, seed 0 và 1, cùng `gold_val` và cùng `test` 100 ảnh. Mục này sẽ được cập nhật bằng `comparison.md` sau khi có `submission/results/`.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: HOLD.** Dataset `clean_v1` chỉ là bản nháp để thử nghiệm, chưa phát hành. Có 2 cách để thành Release:
- duyệt thêm ít nhất **18 ảnh** trong số 38 ảnh còn cảnh báo, để còn ≤ 20/202 = 9,9% < 10%. Nên ưu tiên các ảnh còn MISSING (13) và WRONG_CLASS (3);
- hoặc tăng ngân sách duyệt của đợt sau lên ≥ 125 ảnh, tức bằng cả hàng đợi.

Nếu phát sinh lại ERROR (ví dụ ảnh mới chưa có nhãn) thì kết luận chuyển sang Rework và không xuất dataset. **Không** được hạ recall của checker (ví dụ `conf = 0.8`) để ép Release.

**(b) Dùng AI (Claude Code).**
- *Prompt chính:* "hướng dẫn tôi viết `label_format.py`" (và tương tự cho `gate`, `autofix`, `second_opinion`). Mỗi module mình đưa đủ 4 ý: đầu vào/đầu ra lấy từ docstring, quy tắc từng mã lỗi, ngưỡng lấy từ `cfg`, và các ca biên trong test (dòng trống, dòng 2 lỗi, ảnh đã xoá). AI cũng chạy `make calibrate`, thử 14 cặp ngưỡng trên raw và ghép ảnh các cặp nghi trùng để mình xem.
- *Cách kiểm:* chạy 79 unit test (xanh hết) và `make check-core`; đối chiếu `02` → `04` → `07` với `03_fixes.csv`; mở bằng mắt các cặp DUP/LEAK; chạy `--budget 0` để thấy gate ra Rework.
- *Một lần AI sai:* khi thử lời giải `gate.py`, AI dùng `head -n 18` để giữ phần đầu file nhưng cắt mất dòng `from ..common import ERROR, WARN`, nên 8/10 test fail vì thiếu tên `ERROR`/`WARN`. Phải sửa thành `head -n 19`. Ngoài ra, khi chép code AI vào `autofix.py`, hai khối (sửa `data.yaml` và `needs_label`) bị thụt lề lọt vào trong vòng `for`: test vẫn chạy nhưng 2 test fail (`rename_classes`, `needs_label`), nên phải đọc lại thụt lề từng khối.
