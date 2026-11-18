# Báo cáo Day 09 — Lâm Trung Hiếu, 03048

## 1. Kết luận trước
Kết luận của pipeline là **HOLD** (mã thoát 10).

Lô có 224 ảnh. Ở bước nhận, pipeline loại 22 ảnh: 2 ảnh hỏng, 3 ảnh quá nhỏ, 8 ảnh trùng byte, 4 ảnh trùng gần đúng và 5 ảnh trùng với tập test. Còn lại 202 ảnh, được xuất ra `submission/export/clean_v1/` nhưng chỉ là bản nháp, chưa phát hành.

Sau vòng 3 không còn lỗi bắt buộc nào. Lý do ra Hold là vẫn còn 38/202 ảnh (18,8%) có cảnh báo mà chưa ai duyệt, vượt ngưỡng 10%. Hàng đợi có 125 ảnh nhưng ngân sách duyệt chỉ có 80 ảnh.

## 2. Lỗi và phân việc
Số liệu em lấy từ `02_error_list_v1` (trước khi sửa, 202 ảnh; các mã ở bước nhận thì tính trên 224 ảnh), `03_fixes.csv` và `05_review_queue.csv`.

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| CORRUPT_IMAGE | 2 ảnh / 224 | máy, loại ảnh | không mở được ảnh |
| BAD_SIZE | 3 ảnh / 224 | máy, loại ảnh | cạnh ngắn dưới 250 px |
| DUP_IMAGE_EXACT | 8 ảnh / 224 | máy, loại ảnh | trùng md5, chỉ giữ 1 bản |
| DUP_IMAGE_NEAR | 4 ảnh / 224 | máy, loại ảnh | pHash ≤ 12; em đã mở xem cả 4 cặp, đều trùng thật |
| LEAK_TEST | 5 ảnh / 224 | máy, loại ảnh | trùng ảnh test, giữ lại thì mAP bị thổi phồng |
| BAD_CLASS_NAME | 2 tên trong data.yaml | máy, `rename_classes` | `Person`, `Bus` sai tên, sửa lại theo `classes` |
| BAD_CLASS_ID | 6 dòng | máy, `drop_line` | id 93, −1, 7, 4 không có nghĩa, không đoán được lớp đúng |
| BAD_FORMAT | 3 dòng | máy, `drop_line` | có nan hoặc thiếu cột |
| BOX_ZERO | 4 dòng | máy, `drop_line` | box không có diện tích |
| DUP_BOX | 7 dòng | máy, `drop_line` | cùng lớp và IoU > 0,9 với dòng trước |
| BOX_OUT_OF_IMAGE | 8 dòng | máy, `clip_box` | tràn 0,023–0,06; cắt về trong ảnh, giữ lớp |
| MISSING_LABEL_FILE | 6 ảnh | người, `needs_label` | máy không được tự bịa nhãn; file rỗng nghĩa là "ảnh nền", khác với "chưa gán" |
| POSSIBLE_MISSING | 53 | người | model lớn thấy vật mà nhãn không có |
| POSSIBLE_FALSE_POS | 29 | người | box trong nhãn không khớp vật nào model thấy |
| POSSIBLE_LOOSE_BOX | 28 | người | đúng vật nhưng box lệch hoặc lỏng |
| POSSIBLE_WRONG_CLASS | 18 | người | model và nhãn ghi hai lớp khác nhau ở cùng chỗ |
| EMPTY_LABEL / BOX_TINY / BOX_HUGE / CLASS_RARE | 12 / 6 / 3 / 4 | người | cảnh báo theo quy tắc, cần người xem |

Máy tự sửa 35 thay đổi, ghi trong `03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 1 `rename_classes`, 6 `needs_label`. Mỗi dòng đều có giá trị trước và sau. `data/raw` không bị sửa.

Em để ý là sửa tự động cũng sinh ra cảnh báo mới. Trong `04_error_list_v2`, `EMPTY_LABEL` tăng từ 12 lên 15, vì có 3 file bị xoá hết dòng. `BOX_TINY` tăng từ 6 lên 7, vì sau khi cắt box tràn thì một box bị hẹp lại. Vì vậy sau khi sửa vẫn phải cho chạy QC lại.

Về hàng đợi: `05_review_queue.csv` xếp ảnh theo điểm. Điểm của một ảnh là tổng các cảnh báo của ảnh đó, mỗi cảnh báo tính bằng `trọng số × (1 + conf của model)`, trọng số lấy từ `review.weights`.
- Đứng đầu là `img_0020` (11,5 điểm): ảnh này vừa bị xoá một dòng id 93, vừa có MISSING và WRONG_CLASS.
- Tiếp theo là 6 ảnh `NEEDS_LABEL` (trọng số 10), vì thiếu nhãn là lỗi bắt buộc, không xử lý thì không Release được.
- Sau đó là các ảnh có WRONG_CLASS (trọng số 3) và MISSING (trọng số 2).

Với ngân sách 80/125 ảnh, người duyệt xem hết 6 ảnh thiếu nhãn và các ảnh ưu tiên cao. So `04` với `07`: MISSING giảm từ 53 xuống 13, WRONG_CLASS từ 18 xuống 3, LOOSE_BOX từ 28 xuống 20, FALSE_POS từ 24 xuống 21. Còn 45 ảnh trong hàng đợi chưa ai xem.

## 3. Calibration (2 ngưỡng)
Precision và recall đo trên `data/calib` (39 ảnh, đáp án ở `MANIFEST.csv`), lấy từ `calibration_report.md` trước và sau khi đổi cấu hình.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 12 | DUP_IMAGE_NEAR 1,00/0,50 → 1,00/0,67 | Đây là lỗi ERROR, ảnh bị xoá luôn, nên em ưu tiên precision. Từ 4 đến 14 thì recall trên calib như nhau (0,67). Nhưng trên raw, ngưỡng 12 bắt thêm được cặp `img_0186`/`img_0061` (ảnh bị cắt, khoảng cách 10) mà ngưỡng 8 bỏ sót, và không xoá nhầm ảnh nào. Em đã mở xem cả 4 cặp NEAR và 5 cặp LEAK. |
| `second_opinion.conf` | 0.25 | 0.6 | WRONG_CLASS 0,56/0,83 → 0,62/0,83; MISSING 0,50/1,00 → 0,57/1,00; LOOSE_BOX 0,29/0,40 → 0,20/0,20; FALSE_POS 0,31/1,00 (không đổi) | Đây là cảnh báo cho người nên em giữ recall. 0,6 là giá trị cao nhất mà recall của MISSING vẫn là 1,00; lên 0,7 thì còn 0,88, lên 0,8 còn 0,75. Precision tăng nên hàng đợi trên raw giảm từ 143 xuống 125. Đổi lại, recall của LOOSE_BOX giảm từ 0,40 xuống 0,20. Em chấp nhận vì lỗi này có trọng số thấp (1,5, so với 3 và 2) và calib chỉ có 5 ca. |

Calibration có thể đánh lừa ở chỗ này. Nếu chỉ nhìn calib thì `phash_dist = 16` là tốt nhất (NEAR 1,00/0,83). Nhưng khi chạy trên raw, số ảnh bị loại tăng từ 9 lên 18 (NEAR từ 4 lên 7, LEAK từ 5 lên 11). Em mở ra xem thì thấy toàn là ảnh khác nhau:
- `img_0011` (đánh tennis) bị coi là trùng với `img_0008` (trượt tuyết);
- `img_0177` (lướt sóng) bị coi là trùng với `img_0113` (người ngồi bàn);
- `img_0013` bị coi là rò rỉ từ `test_087`, trong khi hai ảnh khác hẳn nhau.

Con số precision 1,00 trên calib chỉ dựa vào 6 ca NEAR, nên không đáng tin. Vì vậy em không chọn 16.

Tương tự, nếu đặt `conf = 0.8` thì pipeline ra **Release** (hàng đợi còn 102 ảnh). Nhưng đó là do checker bị "mù" bớt (recall MISSING chỉ còn 0,75), chứ dữ liệu không sạch hơn. Em coi đây là Release giả nên không chọn.

## 4. Cửa chặn và điều pipeline không bắt được
**(a) Chứng minh gate chặn thật.** Em chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`. Không có người duyệt nên 6 ảnh `MISSING_LABEL_FILE` vẫn còn. Kết quả:
- kết luận `REWORK — còn 6 lỗi bắt buộc (ERROR): phải sửa trước khi xuất`;
- mã thoát 20;
- log in ra `KHÔNG xuất: còn lỗi bắt buộc (Rework)`, và thư mục `work/exp_nb` không được tạo.

Ở lần chạy chính thì người duyệt đã gán nhãn cho 6 ảnh đó, nên không còn ERROR. Khi đó gate mới chuyển sang xét tỉ lệ cảnh báo và ra Hold. Test `test_error_cannot_be_hidden_by_reviewed` kiểm tra rằng lỗi ERROR không bị bỏ qua, kể cả ở ảnh đã duyệt.

**(b) Những chỗ pipeline không bắt được:**
1. **Ảnh trùng bị biến đổi nhiều.** `img_0084` và `img_0074` là cùng một cảnh (người cầm ô trắng, bị cắt và thu nhỏ), nhưng pHash = 16 > 12 nên cả hai vẫn vào dataset. Tăng ngưỡng lên 16 thì bắt được cặp này, nhưng lại xoá nhầm 3 ảnh khác (xem mục 3). Không có ngưỡng nào vừa bắt được cặp này vừa không xoá nhầm.
2. **Box lỏng nhẹ.** Recall của LOOSE_BOX trên calib chỉ có 0,20 (bắt được 1/5). Sau khi người duyệt vẫn còn 20 cảnh báo LOOSE_BOX ở các ảnh chưa xem. Box chỉ lệch nhẹ (IoU ≥ 0,5) thì hoàn toàn không bị cờ.
3. **Nhầm lớp mà model lớn cũng nhầm.** `second_opinion` chỉ báo khi model nói khác với nhãn. Nếu cả nhãn lẫn yolo26l cùng gọi một chiếc truck là car thì không có cảnh báo nào. Trên calib vẫn sót 1/6 WRONG_CLASS (recall 0,83). Lớp truck và bus lại ít (41 và 32 box, theo `class_stats.csv`), nên lỗi này càng khó phát hiện.

## 5. Train: raw vs clean
Em train trên Google Colab (GPU T4) bằng `scripts/train_compare.py`, với yolo26n.pt, 20 epoch, imgsz 640, batch 16, seed 0 và 1. Hai biến thể dùng chung val (`gold_val`, 40 ảnh) và chung test (`data/test`, 100 ảnh nhãn người); chỉ khác nhau ở dữ liệu train. Bảng lấy từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

mAP50 của clean thấp hơn raw 0,025. Con số này gần bằng độ lệch giữa 2 seed của clean (0,025): riêng clean đã dao động từ 0,683 đến 0,718. Vì vậy em chưa kết luận được clean tốt hơn hay kém hơn raw ở mAP50.

Ở mAP50-95, clean thấp hơn 0,024, lớn hơn độ lệch giữa các seed (0,004 và 0,008). Như vậy có dấu hiệu clean thấp hơn thật, nhưng chỉ có 2 seed nên em chưa dám chắc.

Nói chung, **thí nghiệm này không cho thấy dữ liệu sau pipeline làm model tốt hơn.**

Xem AP50 theo từng lớp (seed 0/1) thì phần chênh lệch nằm gần hết ở truck:
- truck: raw 0,657/0,640, clean 0,590/0,486;
- person gần như bằng nhau: raw 0,813/0,832, clean 0,816/0,830;
- bus tương đương: raw 0,681/0,709, clean 0,726/0,681.

Truck cũng là lớp dao động mạnh nhất giữa 2 seed của clean (chênh 0,10).

Em nghĩ có 3 nguyên nhân có thể giải thích:
1. **Raw bị rò rỉ test nên điểm cao hơn thực tế.** Pipeline tìm ra 5 ảnh `LEAK_TEST` trong raw, trùng với `test_009`, `test_033`, `test_039`, `test_044`, `test_085`. Nghĩa là raw đã được train trên chính 5/100 ảnh test, còn clean thì không. Cách kiểm: đánh giá lại cả 2 model trên 95 ảnh test còn lại (bỏ 5 ảnh này) rồi so lại.
2. **Clean ít ảnh hơn và nhãn vẫn chủ yếu là nhãn máy.** Clean có 202 ảnh so với 224 của raw; trong 22 ảnh bị loại có 8 ảnh là bản trùng byte nên không mất thông tin. Người mới duyệt 80/125 ảnh trong hàng đợi, còn 38 ảnh có cảnh báo. Autofix xoá 20 dòng nhãn, có thể làm mất vật thật. Cách kiểm: đếm số box truck trong `clean_v1` so với raw; train thêm biến thể `oracle` (nhãn người) để xem mức tốt nhất có thể đạt.
3. **Truck ít và tập test nhỏ.** Truck chỉ có 41 box trong train, test chỉ có 100 ảnh, nên AP của truck thay đổi nhiều chỉ vì vài box. Một lỗi nhầm car/truck còn sót (điểm mù số 3 ở mục 4) cũng đủ làm lệch. Cách kiểm: chạy từ 5 seed trở lên để biết mức nhiễu chính xác hơn; đếm số truck trong test; xem `ap50_per_class` của từng seed.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: HOLD.** `clean_v1` chỉ là bản nháp để thử nghiệm, chưa phát hành. Có 2 cách để chuyển sang Release:
- Duyệt thêm ít nhất 18 ảnh trong số 38 ảnh còn cảnh báo, để chỉ còn ≤ 20/202 = 9,9% (dưới 10%). Nên ưu tiên các ảnh còn MISSING (13 ảnh) và WRONG_CLASS (3 ảnh).
- Hoặc tăng ngân sách duyệt ở đợt sau lên ít nhất 125 ảnh, tức đủ để xem hết hàng đợi.

Nếu lại có ERROR (ví dụ thêm ảnh mới chưa có nhãn) thì kết luận chuyển thành Rework và không xuất dataset. Em không hạ recall của checker (ví dụ đặt `conf = 0.8`) chỉ để ép ra Release.

**(b) Dùng AI.** Em có dùng Claude Code.
- *Prompt chính:* "hướng dẫn tôi viết `label_format.py`", và tương tự cho `gate`, `autofix`, `second_opinion`. Với mỗi module em đưa đủ 4 ý: đầu vào và đầu ra theo docstring, quy tắc cho từng mã lỗi, ngưỡng lấy từ `cfg`, và các ca biên trong test (dòng trống, một dòng có 2 lỗi, ảnh đã bị xoá). Em cũng nhờ AI chạy `make calibrate`, thử 14 cặp ngưỡng trên raw và ghép ảnh các cặp nghi trùng để em xem bằng mắt.
- *Cách em kiểm:* chạy 79 unit test (xanh hết) và `make check`; đối chiếu `02` → `04` → `07` với `03_fixes.csv`; tự mở xem các cặp DUP và LEAK; chạy `--budget 0` để thấy gate ra Rework.
- *Một lần AI sai:* khi thử lời giải `gate.py`, AI dùng `head -n 18` để giữ phần đầu file, nhưng làm mất dòng `from ..common import ERROR, WARN`, nên 8/10 test fail vì thiếu tên `ERROR`/`WARN`. Phải sửa thành `head -n 19`. Ngoài ra, khi chép code vào `autofix.py`, em để hai khối (sửa `data.yaml` và `needs_label`) bị thụt lề lọt vào trong vòng `for`. Code vẫn chạy nhưng 2 test fail (`rename_classes`, `needs_label`), nên em phải đọc lại thụt lề của từng khối.

**(c) Thưởng: CVAT, lọc box nhỏ.**
*Cách làm:* em tạo project trên CVAT bằng [cvat/labels.json](../cvat/labels.json) (4 lớp `car, person, truck, bus` và thuộc tính `can_review`). Task gồm 20 ảnh từ `work/run/ds/images/`: 5 ảnh pipeline báo `BOX_TINY` và 15 ảnh đầu `05_review_queue.csv`. Em import nhãn dạng YOLO 1.1, rồi trong job bật bộ lọc `width < 20` và dùng `→`/`←` để duyệt các ảnh khớp.

*So với `BOX_TINY` của pipeline:* em tính trực tiếp từ file nhãn của 20 ảnh này. Bộ lọc `width < 20` (px) khớp 23 box trên 7 ảnh: `img_0026` (6), `img_0030` (4), `img_0051` (3), `img_0069` (2), `img_0161` (3), `img_0020` (4), `img_0078` (1). Pipeline chỉ báo `BOX_TINY` 7 box trên 5 ảnh, là các box có cạnh ngắn dưới 12 px: `img_0026:6`, `img_0030:9`, `img_0051:5`, `img_0069:2`, `img_0161:2–4`.

Mọi box mà pipeline báo đều nằm trong tập của CVAT, vì đó là cùng một box và 12 < 20. 16 box còn lại rộng 12–20 px, hầu hết là người đứng xa, ví dụ 4 box ở `img_0020`. Ngưỡng 12 px là quy tắc cố định của dự án (`label_format.min_box_px`), còn 20 px là ví dụ trong slide. Nếu dùng 20 px thì số cảnh báo tăng hơn 3 lần, phần lớn là người thật đứng xa, trong khi hàng đợi duyệt vốn đã vượt ngân sách 80.

Một khác biệt nữa: pipeline xét cạnh ngắn (`min(w, h)`), còn bộ lọc CVAT ở đây chỉ xét width. Một box dẹt, cao dưới 12 px nhưng rộng từ 20 px trở lên, sẽ bị pipeline bắt nhưng không khớp bộ lọc `width < 20`. Muốn CVAT lọc đúng như pipeline thì phải dùng 2 rule `width < 12` hoặc `height < 12`.

*Kết quả quan sát trên CVAT:* (điền sau khi làm: số ảnh, số box khớp thấy trên CVAT, ảnh chụp ở `submission/cvat/`)

*`can_review`:* người gán tick ô này khi không chắc chắn về box, ví dụ vật bị che, quá nhỏ, hoặc khó phân biệt car/truck/bus, để người kiểm xem lại. Pipeline làm việc tương tự nhưng bằng máy: các cảnh báo WARN như `BOX_TINY`, `POSSIBLE_WRONG_CLASS` không bị sửa tự động mà được cộng trọng số trong `05_review_queue.csv` để đẩy ảnh lên đầu hàng đợi duyệt. Khác ở chỗ `can_review` do người tự đánh dấu khi gán, còn pipeline tự suy ra từ quy tắc và từ model yolo26l.
