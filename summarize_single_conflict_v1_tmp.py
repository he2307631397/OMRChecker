import csv
import glob
import os

p = max(glob.glob('outputs_inputs_10_single_conflict_v1/Results/*.csv'), key=os.path.getmtime)
rows = list(csv.DictReader(open(p, newline='', encoding='utf-8-sig')))
id_cols = [c for c in rows[0] if c.startswith('id')]
q_cols = [c for c in rows[0] if c.startswith('q')]
singles = [f'q{i}' for i in range(1, 9)]
print('csv=', p)
print('rows=', len(rows))
print('id_blank_cells=', sum(1 for r in rows for c in id_cols if not (r.get(c) or '').strip()))
print('q_blank_cells=', sum(1 for r in rows for c in q_cols if not (r.get(c) or '').strip()))
print('single_multi_count=', sum(1 for r in rows for c in singles if len((r.get(c) or '').strip()) > 1))
for r in rows:
    name = r['file_id']
    for c in singles:
        v = (r.get(c) or '').strip()
        if len(v) > 1:
            print('MULTI', name, c, v)
        if not v:
            print('BLANK_SINGLE', name, c)
