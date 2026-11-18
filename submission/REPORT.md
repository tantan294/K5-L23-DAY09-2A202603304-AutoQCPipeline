# Báo cáo Day 09 — Bùi Thanh Tân, 2A202603304

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10). Lô raw có **224** ảnh vào; **22** ảnh bị loại ở cửa vào; **202** ảnh được xuất ra `submission/export/clean_v1` .

Lý do: sau sửa tự động và người duyệt, **0 lỗi bắt buộc**, nhưng **38/202 ảnh (18,8%)** còn cảnh báo chưa được duyệt, vượt ngưỡng 10%: hàng đợi có **125 ảnh**, lớn hơn ngân sách duyệt 80 ảnh.

## 2. Lỗi và phân việc
Từ `02_error_list_v1` , gom theo mã lỗi:

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT` | 8 ảnh | máy (loại ảnh) | trùng từng byte: giữ một bản, không mất thông tin |
| `DUP_IMAGE_NEAR` | 4 ảnh | máy (loại ảnh) | ảnh cắt/thu nhỏ của ảnh khác (`phash_dist` = 12, đã mở xem từng cặp) |
| `LEAK_TEST` | 5 ảnh | máy (loại ảnh) | trùng ảnh kho test/val: để lại sẽ thổi phồng điểm test |
| `BAD_SIZE` / `CORRUPT_IMAGE` | 3 / 2 ảnh | máy (loại ảnh) | cạnh ngắn < 250px / không mở được ảnh |
| `BAD_CLASS_ID` | 6 dòng | máy (`drop_line`) | id lớp ngoài 0..3 (vd. `93`): không đoán được lớp đúng |
| `BAD_FORMAT` | 3 dòng | máy (`drop_line`) | dòng không đủ 5 cột số |
| `BOX_ZERO` | 4 dòng | máy (`drop_line`) | box rộng hoặc cao bằng 0 |
| `DUP_BOX` | 7 dòng | máy (`drop_line`) | cùng lớp, IoU > 0.9 với dòng trước: xoá dòng sau |
| `BOX_OUT_OF_IMAGE` | 8 dòng | máy (`clip_box`) | cắt về [0,1], giữ nguyên lớp |
| `BAD_CLASS_NAME` | data.yaml | máy (`rename_classes`) | ghi lại `names` đúng `classes` của dự án |
| `MISSING_LABEL_FILE` | 6 ảnh | **người** (`needs_label`) | máy không bịa nhãn; file rỗng nghĩa là "ảnh nền", khác với "chưa gán" |
| `POSSIBLE_MISSING` | 52 ảnh | **người** | lỗi ngữ nghĩa, model lớn cũng có thể sai → chỉ cảnh báo |
| `POSSIBLE_FALSE_POS` | 27 ảnh | **người** | như trên |
| `POSSIBLE_LOOSE_BOX` | 24 ảnh | **người** | như trên |
| `POSSIBLE_WRONG_CLASS` | 18 ảnh | **người** | như trên |
| `EMPTY_LABEL` / `BOX_TINY` / `BOX_HUGE` | 12 / 4 / 3 ảnh | **người** | có thể đúng (ảnh nền, vật nhỏ, vật chiếm cả khung) → người quyết |

Máy đã sửa **35** thay đổi (`03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 6 `needs_label`, 1 `rename_classes`); 36 lỗi bắt buộc ở vòng 1 → 6 lỗi còn lại ở vòng 2 (đều là `MISSING_LABEL_FILE`, chờ người).

**Thứ tự hàng đợi** (`05_review_queue.csv`): `priority` = tổng trọng số `review.weights` của các mã trong ảnh. `NEEDS_LABEL` có trọng số 10 nên 6 ảnh chưa có nhãn (vd. `img_0031`, `img_0053`) luôn ở đầu; ảnh dính nhiều cờ nặng cũng lên đầu, vd. `img_0020` (11.5 = `FIXED_DROP_LINE` + `POSSIBLE_MISSING` + `POSSIBLE_WRONG_CLASS`).
**Với ngân sách 80 ảnh** (so `02` với `07`): `POSSIBLE_MISSING` 52 → 12 ảnh, `POSSIBLE_WRONG_CLASS` 18 → 3, `POSSIBLE_FALSE_POS` 27 → 21, `POSSIBLE_LOOSE_BOX` 24 → 20. Người xử lý được phần lớn lỗi thiếu nhãn/nhầm lớp (trọng số cao), còn box lỏng/thừa (trọng số thấp) phần lớn chưa được xem.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | `DUP_IMAGE_NEAR`: 1.00 / 0.50 → 1.00 / 0.67 | Ngưỡng này **xoá ảnh** nên phải giữ precision = 1.00. Trên calib, 4…14 cho cùng kết quả; trên raw, 12 bắt thêm 2 cặp trùng thật (`img_0223↔img_0077` d=6, `img_0186↔img_0061` d=10) mà không loại nhầm ảnh nào. 14 cho đúng như 12; 12 nằm giữa vùng ổn định 10–14 nên có khoảng dư. |
| `second_opinion.conf` | 0.25 | **0.6** | `MISSING`: 0.50 / 1.00 → 0.57 / 1.00; `WRONG_CLASS`: 0.56 / 0.83 → 0.62 / 0.83; `LOOSE_BOX`: 0.29 / 0.40 → 0.20 / 0.20 | Cảnh báo cho người nên ưu tiên **recall**. 0.6 là giá trị cao nhất mà recall `MISSING` vẫn = 1.00; hàng đợi trên raw giảm 145 → 125 ảnh. Cái giá: `LOOSE_BOX` bỏ sót thêm 1/5. Không lên 0.8 (sẽ ra Release, 7,9%) vì recall `MISSING` khi đó tụt còn 0.75: không hạ recall chỉ để hàng đợi vừa ngân sách. |

Thử trên raw (cùng `conf` = 0.25): `phash_dist` 2 → loại 19 ảnh; 8 → 21; 12 → 22; 14 → 22; 16 → **31**. Với `phash_dist` = 12: `conf` 0.25 → hàng đợi 143 (Hold 28,7%); 0.6 → 125 (Hold 18,8%); 0.7 → 118 (Hold 14,4%); 0.8 → 102 (Release 7,9%).

**Một chỗ calibration có thể đánh lừa:** trên calib, `phash_dist` = 16 cho recall `DUP_IMAGE_NEAR` cao nhất (0.83) và precision vẫn 1.00, nhìn bảng sẽ chọn 16. Nhưng trên raw, mở xem các cặp ở d=16: `img_0011` (tennis) bị coi là trùng với `img_0008` (trượt tuyết), `img_0177` (lướt sóng) với `img_0113` (người ngồi bàn) — hai ảnh khác hẳn nhau. Số ảnh bị loại tăng 22 → 31, trong đó `LEAK_TEST` tăng 5 → 11 vì cùng ngưỡng còn dùng để so với kho test/val. Calib chỉ có 6 cặp gần trùng, nên mức tăng 0.67 → 0.83 chỉ là **1 cặp**, không đủ làm bằng chứng.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt):
kết luận **`REWORK — còn 6 lỗi bắt buộc (MISSING_LABEL_FILE): phải sửa rồi chạy lại`**, mã thoát **20**, log in `KHÔNG xuất: còn lỗi bắt buộc (Rework)` và `Test-Path work/exp_nb/clean_v1` → `False` (không xuất dataset). Lỗi bắt buộc không bị che dù cảnh báo có thể ít: unit test `test_error_cannot_be_hidden_by_reviewed` cũng kiểm điều này.

**(b) Điểm mù có bằng chứng.**
1. **Ảnh trùng bị cắt mạnh:** `img_0084` là bản cắt của `img_0074` (cùng người phụ nữ cầm ô ren, đã mở xem), nhưng khoảng cách phash = 16 > 12 nên **lọt**. Không thể nâng ngưỡng để bắt vì ở d=16 có 2 cặp ảnh khác hẳn nhau (mục 3): phash không tách được hai trường hợp này.
2. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` trên calib chỉ recall **0.20** (bắt 1/5 lỗi chèn) ở `conf` = 0.6; sau người duyệt raw vẫn còn 20 ảnh `LOOSE_BOX` chưa ai xem.
3. **Nhầm lớp mà model lớn cũng nhầm:** `second_opinion` chỉ thấy lỗi khi yolo26l khác ý nhãn; nếu cả hai cùng sai (vd. truck/bus) thì không có cờ. `WRONG_CLASS` trên calib recall 0.83 ở mọi `conf` (1/6 lỗi chèn không bao giờ bắt được).

**Lỗi tự nhìn thấy khi xem ảnh (`viz_labels.py`, Bước 1)** — đối chiếu với pipeline:
- `img_0020` dòng 3: id lớp `93` (khung màu đen); cả xe buýt bị gán sai lớp → pipeline bắt được (`BAD_CLASS_ID` dòng 3; `POSSIBLE_WRONG_CLASS` "model nói bus", IoU 0.94).
- `img_0001` dòng 3: hai khung chồng khít nhau; một người không có khung → bắt được (`DUP_BOX` dòng 3; `POSSIBLE_MISSING` person conf 0.95).
- `img_0030` dòng 9: khung tràn ra ngoài mép ảnh và không ôm vật nào → bắt được (`BOX_OUT_OF_IMAGE` 0.023, `POSSIBLE_FALSE_POS` dòng 9).

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Cấu hình (Colab T4, `scripts/train_compare.py`): `yolo26n.pt`, 20 epoch, imgsz 640, seed 0 và 1; cùng val (`gold_val`, 40 ảnh) và cùng test (`data/test`, 100 ảnh nhãn người). Chỉ khác dữ liệu train: `raw` = 224 ảnh nhãn gốc, `clean` = 202 ảnh của `export/clean_v1` (bản nháp Hold).

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

Chênh mAP50 (clean − raw) = **−0.025**. Theo từng seed: seed 0 là 0.718 vs 0.726 (−0.008), seed 1 là 0.683 vs 0.726 (−0.043).

**So với nhiễu:** chênh −0.025 bằng đúng độ lệch giữa 2 seed của `clean` (±0.025); seed 0 gần như hoà, seed 1 thua rõ. Với chỉ 2 seed, độ lệch chuẩn ước lượng rất không chắc (`raw` ±0.000 chỉ là trùng hợp của 2 lần chạy). → **Chưa kết luận được** clean tốt hơn hay kém hơn raw; số liệu **không** ủng hộ "dữ liệu sạch giúp model tốt hơn" ở quy mô này.

**AP50 theo lớp** (seed 0 / seed 1): car raw 0.751/0.724 – clean 0.740/0.736 (hoà); person 0.813/0.832 – 0.816/0.830 (hoà); **truck** 0.657/0.639 – **0.590/0.486** (clean kém nhất, dao động lớn); bus 0.681/0.709 – 0.726/0.681 (hoà). Phần chênh chủ yếu đến từ **truck**, lớp ít box nhất (41 box trong `class_stats.csv`).

**Giả thuyết và cách kiểm:**
1. **Ít dữ liệu hơn:** `clean` có ít hơn 22 ảnh (−10%); với 20 epoch và yolo26n, mất 10% ảnh có thể nặng hơn lợi ích từ nhãn sạch. *Kiểm:* train `raw` trên đúng 202 ảnh của manifest nhưng giữ nhãn gốc, để tách tác dụng "bớt ảnh" khỏi tác dụng "sửa nhãn".
2. **Rò rỉ test thổi phồng `raw`:** `raw` còn 5 ảnh `LEAK_TEST` trùng ảnh trong `data/test` (`01_intake.csv`), model raw đã "thấy" một phần đề thi. *Kiểm:* đánh giá lại cả hai model trên test sau khi bỏ 5 ảnh test bị trùng; nếu khoảng cách thu hẹp thì điểm raw bị thổi phồng.
3. **Nhãn `clean` chưa sạch hết, nhất là truck:** bản xuất là Hold, 38 ảnh còn cảnh báo chưa duyệt (20 `LOOSE_BOX`, 3 `WRONG_CLASS` trong `07_error_list_v3`); `drop_line` xoá 20 dòng có thể đã xoá cả box truck/bus đúng mà bị nhầm id. *Kiểm:* đếm box truck trong `work/train/raw` vs `work/train/clean` (ô 5 notebook) và xem `03_fixes.csv` các dòng bị xoá thuộc lớp nào.
4. **Test nhỏ:** 100 ảnh, truck/bus có rất ít vật, một vài box thay đổi làm AP lớp đó nhảy 0.05–0.1. *Kiểm:* thêm seed (≥ 5) và báo khoảng tin cậy.

**Việc tiếp theo:** chạy ≥ 5 seed mỗi biến thể; thêm biến thể `raw` giới hạn 202 ảnh; đánh giá trên test đã bỏ ảnh rò rỉ; duyệt nốt 38 ảnh còn cảnh báo (đưa lô về Release) rồi train lại `clean`.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối: Hold.** Không còn lỗi bắt buộc, nhưng 38/202 ảnh (18,8%) còn cảnh báo chưa duyệt. Để thành Release cần người duyệt thêm ít nhất ~18 ảnh trong số 38 ảnh còn cảnh báo (để xuống dưới 10% = 20 ảnh), ưu tiên `POSSIBLE_MISSING` (12 ảnh) và `POSSIBLE_FALSE_POS`; hoặc tăng ngân sách duyệt lên ~125 ảnh. Không hạ `conf` xuống chỉ để đạt Release (mục 3).

**(b) Dùng AI (Claude Code):**
- *Prompt chính:* phối hợp viết 4 module, định nghĩa các định nghĩa từ vựng chuyên ngành (`label_format`, `gate`, `autofix`, `second_opinion`).
- *Cách kiểm:* chạy 79 unit test xanh hết; dòng trống giữa file → số dòng không lệch; chạy autofix lần 2 → không đổi gì; ảnh nhiều dự đoán → chỉ 1 cờ `MISSING` đúng; đối chiếu lỗi chèn trên calib: mọi lỗi cú pháp P = R = 1.00.
- *Một lần AI sai:* script thử ca khó lần đầu chết vì `ModuleNotFoundError: PIL` (chạy Python với cờ `-I` nên mất site-packages).