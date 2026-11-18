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


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # + mọi code bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fmt(v):
    return f"{v:.6f}".rstrip("0").rstrip(".") or "0"


def _clip(text):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích (nằm hẳn ngoài ảnh)."""
    cid, x, y, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    return " ".join([str(cid), _fmt((x1 + x2) / 2), _fmt((y1 + y2) / 2), _fmt(x2 - x1), _fmt(y2 - y1)])


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]     # không bao giờ động tới WARN
    fixes = []

    def log(image, line, action, before, after):
        fixes.append({"image": image, "line": line, "action": action, "before": before, "after": after})

    # 1) Xoá ảnh (trùng / rò rỉ test / hỏng / sai cỡ) — làm TRƯỚC để các issue dòng của ảnh đó bị bỏ qua êm.
    removed = set()
    for i in errors:
        if _is_remove(i.code) and i.image not in removed:
            removed.add(i.image)
            img_paths = [p for p in ds.image_files() if p.stem == i.image]
            lab = ds.label_path(i.image)
            if not img_paths and not lab.exists():
                continue                                       # đã xoá ở lần chạy trước -> không ghi gì (idempotent)
            for p in img_paths:
                p.unlink()
            if lab.exists():
                lab.unlink()
            log(i.image, None, "remove_image", ", ".join(p.name for p in img_paths) or "(chỉ có nhãn)", f"đã xoá ({i.code})")

    # 2) data.yaml: ghi lại names đúng cfg["classes"], giữ các khoá khác.
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else {}
        d = d or {}
        before = d.get("names")
        new_names = {k: v for k, v in enumerate(cfg["classes"])}
        if before != new_names:
            d["names"] = new_names
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            log("data.yaml", None, "rename_classes", str(before), str(new_names))

    # 3) Ảnh chưa có nhãn: KHÔNG tạo file (rỗng = "ảnh nền"), chỉ ghi lại để chuyển người gán.
    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE"} - removed):
        log(stem, None, "needs_label", "(không có file)", "chuyển người gán")

    # 4) Lỗi dòng: gom theo file, dùng số dòng GỐC, ghi lại MỘT lần. Xoá dòng thắng cắt box.
    drop, clip = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.line is None or i.image in removed:
            continue
        if i.code in DROP_CODES:
            drop[i.image].add(i.line)
        elif i.code == "BOX_OUT_OF_IMAGE":
            clip[i.image].add(i.line)

    for stem in sorted(set(drop) | set(clip)):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()   # giữ cả dòng trống => số dòng gốc
        out = []
        for n, text in enumerate(raw, 1):
            if n in drop[stem]:
                log(stem, n, "drop_line", text, "")
                continue
            if n in clip[stem]:
                try:
                    new = _clip(text)
                except ValueError:
                    new = None
                if new is None:
                    log(stem, n, "drop_line", text, "")       # box nằm hẳn ngoài ảnh -> xoá thay vì ghi box rỗng
                    continue
                log(stem, n, "clip_box", text, new)
                out.append(new)
                continue
            out.append(text)
        path.write_text("".join(l + "\n" for l in out), encoding="utf-8")
    return fixes
