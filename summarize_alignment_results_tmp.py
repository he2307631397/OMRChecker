import csv
from pathlib import Path

cases = {
    'baseline': Path('outputs_inputs_21_baseline/Results'),
    'auto_align': Path('outputs_inputs_21_auto_align/Results'),
    'crop_page': Path('outputs_inputs_21_crop_page/Results'),
    'feature_align': Path('outputs_inputs_21_feature_align/Results'),
}

def find_csv(d):
    files = sorted(d.glob('Results_*.csv'))
    return files[0] if files else None

rows_out = []
for name, d in cases.items():
    csv_path = find_csv(d)
    if not csv_path:
        rows_out.append([name, '', 'NO_CSV', '', '', '', ''])
        continue
    with csv_path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []
    id_fields = [c for c in fields if c.startswith('id')]
    q_fields = [c for c in fields if c.startswith('q')]
    id_blank_cells = sum(1 for r in rows for c in id_fields if (r.get(c) or '') == '')
    id_blank_rows = sum(1 for r in rows if any((r.get(c) or '') == '' for c in id_fields))
    any_blank_rows = sum(1 for r in rows if any((r.get(c) or '') == '' for c in fields if c != 'file_id'))
    q_blank_cells = sum(1 for r in rows for c in q_fields if (r.get(c) or '') == '')
    rows_out.append([name, str(csv_path), len(rows), len(id_fields), id_blank_cells, id_blank_rows, q_blank_cells, any_blank_rows])

out = Path('outputs_inputs_21_alignment_summary.csv')
with out.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['case', 'csv_path', 'rows', 'id_fields', 'id_blank_cells', 'id_blank_rows', 'q_blank_cells', 'any_blank_rows'])
    w.writerows(rows_out)
print(out)
for row in rows_out:
    print(row)
