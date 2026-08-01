from pathlib import Path
import cv2
import numpy as np

cases = [
    ('baseline', Path('outputs_inputs_21_baseline/CheckedOMRs')),
    ('feature_align', Path('outputs_inputs_21_feature_align/CheckedOMRs')),
]
# Around ExamId block: origin [777,396], 8 cols, 10 rows, dims [30,17], gaps x/y [44/27]
x0, y0, x1, y1 = 720, 350, 1165, 700
out_dir = Path('outputs_inputs_21_feature_align/id_coord_compare')
out_dir.mkdir(parents=True, exist_ok=True)

for label, d in cases:
    crops = []
    for p in sorted(d.glob('MX-M3658N_*.png')):
        img = cv2.imread(str(p))
        if img is None:
            continue
        crop = img[y0:y1, x0:x1]
        cv2.putText(crop, f'{label} {p.stem[-3:]}', (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,0,255), 2, cv2.LINE_AA)
        crops.append(crop)
    if crops:
        rows = []
        for i in range(0, len(crops), 3):
            chunk = crops[i:i+3]
            h = max(c.shape[0] for c in chunk)
            padded = []
            for c in chunk:
                if c.shape[0] < h:
                    c = cv2.copyMakeBorder(c, 0, h-c.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255,255,255))
                padded.append(c)
            while len(padded) < 3:
                padded.append(np.full_like(padded[0], 255))
            rows.append(np.hstack(padded))
        montage = np.vstack(rows)
        cv2.imwrite(str(out_dir / f'{label}_id_montage.png'), montage)

# side-by-side comparison per page
pairs = []
base_files = sorted(cases[0][1].glob('MX-M3658N_*.png'))
feat_files = sorted(cases[1][1].glob('MX-M3658N_*.png'))
for bp, fp in zip(base_files, feat_files):
    bi = cv2.imread(str(bp))[y0:y1, x0:x1]
    fi = cv2.imread(str(fp))[y0:y1, x0:x1]
    sep = np.full((bi.shape[0], 12, 3), 255, dtype=np.uint8)
    cv2.putText(bi, f'base {bp.stem[-3:]}', (8,22), cv2.FONT_HERSHEY_SIMPLEX, .55, (0,0,255), 2, cv2.LINE_AA)
    cv2.putText(fi, f'feature {fp.stem[-3:]}', (8,22), cv2.FONT_HERSHEY_SIMPLEX, .55, (0,0,255), 2, cv2.LINE_AA)
    pairs.append(np.hstack([bi, sep, fi]))
rows = []
for i in range(0, len(pairs), 2):
    chunk = pairs[i:i+2]
    while len(chunk) < 2:
        chunk.append(np.full_like(chunk[0], 255))
    rows.append(np.hstack(chunk))
if rows:
    cv2.imwrite(str(out_dir / 'baseline_vs_feature_id_montage.png'), np.vstack(rows))
print(out_dir / 'baseline_vs_feature_id_montage.png')
