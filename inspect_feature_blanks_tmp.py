import csv
from pathlib import Path
p = Path('outputs_inputs_21_feature_align/Results/Results_12PM.csv')
with p.open(newline='', encoding='utf-8') as f:
    r = csv.DictReader(f)
    for row in r:
        blanks = [k for k,v in row.items() if k != 'file_id' and (v or '') == '']
        if blanks:
            print(row['file_id'], blanks)
