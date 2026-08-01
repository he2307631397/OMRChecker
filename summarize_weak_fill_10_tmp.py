import csv
import json
import re
from pathlib import Path

import cv2
import numpy as np

csv_path = next(Path('outputs_inputs_10_weak_fill/Results').glob('Results_*.csv'))
rows = list(csv.DictReader(open(csv_path, newline='', encoding='utf-8')))
ids = [c for c in rows[0] if c.startswith('id')]
qs = [c for c in rows[0] if c.startswith('q')]
blanks = [(r['file_id'], c) for r in rows for c in ids + qs if not r[c]]
print('csv', csv_path)
print('rows', len(rows))
print('id_blank_cells', sum(1 for _, c in blanks if c in ids))
print('q_blank_cells', sum(1 for _, c in blanks if c in qs))
print('blank_cells', len(blanks))
print('blank_rows', len({fid for fid, _ in blanks}))
print('blank details:')
for r in rows:
    row_blanks = [c for c in ids + qs if not r[c]]
    if row_blanks:
        print(r['file_id'], row_blanks, 'id=' + ''.join(r[c] or '_' for c in ids), 'answers=' + ','.join(c + '=' + (r[c] or '_') for c in qs))

log_path = Path('weak_fill_10.log')
text = log_path.read_text(encoding='utf-8', errors='ignore').splitlines()
patterns = ['Weak identifier fallback', 'Weak mark fallback', 'Weak multi-mark fallback', 'Weak multi full-select fallback']
print('\nfallback summary:')
for pattern in patterns:
    lines = [line for line in text if pattern in line]
    print(pattern, len(lines))
    for line in lines[:20]:
        print(' ', line.strip())

print('\nblank candidate stats:')
tpl = json.load(open('inputs/template.json', encoding='utf-8'))
field_blocks = tpl['fieldBlocks']
# Build coordinates for this known template. Handles current ExamId and Q1-Q11 field blocks.
for fid, label in blanks:
    img_path = Path('outputs_inputs_10_weak_fill/CheckedOMRs') / fid
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        print(fid, label, 'image not found')
        continue
    target_fb_name = None
    field_index = 0
    for name, fb in field_blocks.items():
        labels = fb['fieldLabels']
        expanded = []
        for item in labels:
            if '..' in item:
                prefix = re.match(r'([a-zA-Z_]+)', item).group(1)
                nums = re.findall(r'\d+', item)
                start, end = map(int, nums[:2])
                expanded.extend([f'{prefix}{i}' for i in range(start, end + 1)])
            else:
                expanded.append(item)
        if label in expanded:
            target_fb_name = name
            field_index = expanded.index(label)
            break
    if target_fb_name is None:
        print(fid, label, 'template label not found')
        continue
    fb = field_blocks[target_fb_name]
    bw, bh = fb.get('bubbleDimensions', tpl['bubbleDimensions'])
    bg = fb['bubblesGap']
    lg = fb.get('labelsGap', 0)
    origin = fb['origin']
    values = ['A', 'B', 'C', 'D'] if fb['fieldType'] == 'QTYPE_MCQ4' else [str(i) for i in range(10)]
    direction = fb.get('direction', 'vertical')
    means = []
    for value_index, value in enumerate(values):
        if direction == 'vertical':
            x = origin[0] + field_index * lg
            y = origin[1] + value_index * bg
        else:
            x = origin[0] + value_index * bg
            y = origin[1] + field_index * lg
        roi = img[y:y+bh, x:x+bw]
        means.append((value, float(np.mean(roi))))
    sorted_means = sorted(means, key=lambda item: item[1])
    lighter_half = [m for _, m in sorted_means[len(sorted_means)//2:]]
    blank_baseline = float(np.mean(lighter_half))
    darkest_value, darkest_mean = sorted_means[0]
    second_mean = sorted_means[1][1]
    print(fid, label, 'darkest=', darkest_value, f'{darkest_mean:.2f}', 'second_gap=', f'{second_mean-darkest_mean:.2f}', 'blank_baseline=', f'{blank_baseline:.2f}', 'delta=', f'{blank_baseline-darkest_mean:.2f}', 'all=', ', '.join(f'{v}:{m:.1f}' for v,m in means))
