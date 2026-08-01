import csv
from pathlib import Path
old = Path('outputs_inputs_21_feature_final/Results/Results_12PM.csv')
new = Path('outputs_inputs_21_full_select/Results/Results_12PM.csv')
with old.open(newline='', encoding='utf-8') as f:
    old_rows = {r['file_id']: r for r in csv.DictReader(f)}
with new.open(newline='', encoding='utf-8') as f:
    new_rows = {r['file_id']: r for r in csv.DictReader(f)}
for file_id in sorted(new_rows):
    for k, v in new_rows[file_id].items():
        if old_rows[file_id].get(k) != v:
            print(file_id, k, repr(old_rows[file_id].get(k)), '->', repr(v))
