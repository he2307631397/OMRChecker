import csv
import glob
import os

p = max(glob.glob('outputs_inputs_10_weak_fill_adaptive_v7/Results/*.csv'), key=os.path.getmtime)
rows = list(csv.DictReader(open(p, newline='', encoding='utf-8-sig')))
singles = [f'q{i}' for i in range(1, 9)]
print('csv=', p)
multi = []
blanks = []
for r in rows:
    name = r['file_id']
    for q in singles:
        v = (r.get(q) or '').strip()
        if len(v) > 1:
            multi.append((name, q, v))
        if not v:
            blanks.append((name, q))
print('single_multi_count=', len(multi))
for item in multi:
    print('MULTI', *item)
print('single_blank_count=', len(blanks))
for item in blanks:
    print('BLANK', *item)
