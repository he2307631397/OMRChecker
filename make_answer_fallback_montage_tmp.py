import cv2
import os
import numpy as np

cases = [
    ("MX-M3658N_20260731_162311_001.png", "q5", (946, 757, 29, 18)),
    ("MX-M3658N_20260731_162311_008.png", "q3", (540, 757, 29, 18)),
    ("MX-M3658N_20260731_162311_009.png", "q6", (134, 802, 29, 18)),
]
base = "outputs_inputs_10_weak_fill_adaptive_v5/CheckedOMRs"
out_dir = "outputs_inputs_10_weak_fill_adaptive_v5/review"
os.makedirs(out_dir, exist_ok=True)
imgs = []
for filename, label, box in cases:
    x, y, w, h = box
    img = cv2.imread(os.path.join(base, filename))
    if img is None:
        raise SystemExit(f"missing {filename}")
    crop = img[max(0, y - 45): y + 55, max(0, x - 25): x + 190].copy()
    crop = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3))
    cv2.putText(
        crop,
        f"{filename} {label}",
        (5, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 255),
        2,
    )
    imgs.append(crop)
montage = np.vstack(imgs)
out_path = os.path.join(out_dir, "answer_fallback_montage.png")
cv2.imwrite(out_path, montage)
print(out_path)
