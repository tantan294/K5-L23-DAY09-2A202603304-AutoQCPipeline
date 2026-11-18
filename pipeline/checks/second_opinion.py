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


NAME = "second_opinion"


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, (id, cx, cy, w, h))] chỉ các dòng hợp lệ; dòng hỏng bỏ qua (label_format đã báo)."""
    out = []
    for n, text in ds.read_label_lines(stem) or []:
        try:
            b = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= b[0] < len(ds.classes):
            out.append((n, b))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []

    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue                                           # không có dự đoán / chưa có file nhãn -> bỏ qua
        labels = _labels_with_lines(ds, stem)
        size = ds.image_size(stem)
        rs = [(int(p[0]), float(p[1]), tuple(map(float, p[2:6]))) for p in preds[stem]]   # (lớp, conf, box)

        # --- Phần 1: với từng dự đoán đủ tin cậy và đủ lớn -> MISSING / LOOSE_BOX / WRONG_CLASS
        for r_cls, r_conf, r_box in rs:
            if r_conf < c["conf"]:
                continue
            if size and r_box[2] * size[0] * r_box[3] * size[1] < c["min_area_px"]:
                continue
            cands = [(iou_xywh(r_box, b[1:]), b[0]) for _, b in labels]
            cands = [(iou, cls) for iou, cls in cands if iou >= c["iou_missing"]]
            same = [iou for iou, cls in cands if cls == r_cls]
            other = [iou for iou, cls in cands if cls != r_cls]
            name = ds.classes[r_cls] if 0 <= r_cls < len(ds.classes) else r_cls

            if not cands:
                issues.append(Issue(NAME, WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {name} (conf {r_conf:.2f}) nhưng nhãn không có box",
                                    extra={"conf": r_conf, "pred_class": r_cls, "box": list(r_box)}))
            elif same:
                best = max(same)
                if best < c["iou_loose"]:
                    issues.append(Issue(NAME, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box {name} lệch/lỏng so với model (IoU {best:.2f})",
                                        extra={"conf": r_conf, "iou": round(best, 4)}))
                # ngược lại: nhãn đúng lớp đã phủ vật -> im lặng
            else:
                best = max(other)
                if best >= c["iou_match"]:
                    issues.append(Issue(NAME, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                        f"model nói {name} (conf {r_conf:.2f}) nhưng nhãn là lớp khác (IoU {best:.2f})",
                                        extra={"conf": r_conf, "iou": round(best, 4), "pred_class": r_cls}))
                # IoU khác lớp trong [iou_missing, iou_match): mơ hồ -> không cờ

        # --- Phần 2: từng dòng nhãn không khớp dự đoán nào (conf >= fp_conf, mọi lớp, KHÔNG lọc diện tích)
        fp_boxes = [b for _, conf, b in rs if conf >= c["fp_conf"]]
        for n, b in labels:
            best = max((iou_xywh(b[1:], pb) for pb in fp_boxes), default=0.0)
            if best < c["iou_missing"]:
                issues.append(Issue(NAME, WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box lớp {ds.classes[b[0]]} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                                    line=n, extra={"iou": round(best, 4)}))
    return issues
