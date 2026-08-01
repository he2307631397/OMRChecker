import json
from pathlib import Path

import cv2
import numpy as np

img = cv2.imread('outputs_inputs_56_current_params/CheckedOMRs/MX-M3658N_20260731_160125_005.png', cv2.IMREAD_GRAYSCALE)
if img is None:
    raise SystemExit('image not found')

tpl = json.load(open('inputs/template.json', encoding='utf-8'))
fb = tpl['fieldBlocks']['ExamId']
origin = fb['origin']
bw, bh = fb['bubbleDimensions']
bg = fb['bubblesGap']
lg = fb['labelsGap']

x0 = origin[0] + 7 * lg
y0 = origin[1]
vals = []
for digit in range(10):
    x = x0
    y = y0 + digit * bg
    roi = img[y:y + bh, x:x + bw]
    vals.append(float(np.mean(roi)))

print('id8 origin', x0, y0, 'bubble', bw, bh)
print('means', ', '.join(f'{i}:{v:.2f}' for i, v in enumerate(vals)))
order = sorted(enumerate(vals), key=lambda item: item[1])
print('darkest3', order[:3], 'gap', order[1][1] - order[0][1])

best = []
for digit in range(10):
    best_digit = (999.0, None, None)
    for dy in range(-16, 17, 2):
        for dx in range(-16, 17, 2):
            x = x0 + dx
            y = y0 + digit * bg + dy
            roi = img[y:y + bh, x:x + bw]
            mean = float(np.mean(roi))
            if mean < best_digit[0]:
                best_digit = (mean, dx, dy)
    best.append((digit,) + best_digit)

print('best offsets per digit:')
for digit, mean, dx, dy in best:
    print(f'{digit}: mean={mean:.2f} dx={dx} dy={dy}')
print('overall best', sorted(best, key=lambda row: row[1])[:3])
