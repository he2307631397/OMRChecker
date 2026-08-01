from pathlib import Path
import csv
import cv2
import numpy as np
from src.utils.image import ImageUtils
from src.utils.parsing import open_config_with_defaults
from src.template import Template

config = open_config_with_defaults(Path('inputs/config.json'))
template = Template(Path('inputs/template.json'), config)
labels = {'q9','q10','q11'}
rows=[]
for file_path in sorted(Path('inputs').glob('*.pdf')):
    name, img = ImageUtils.load_omr_image(file_path, config)[0]
    img = template.image_instance_ops.apply_preprocessors(name, img, template)
    img = ImageUtils.resize_util(img, template.page_dimensions[0], template.page_dimensions[1])
    if img.max() > img.min():
        img = ImageUtils.normalize_util(img)
    for field_block in template.field_blocks:
        box_w, box_h = field_block.bubble_dimensions
        for bubbles in field_block.traverse_bubbles:
            label=bubbles[0].field_label
            if label not in labels:
                continue
            vals=[]
            for b in bubbles:
                x,y=b.x + field_block.shift, b.y
                vals.append(cv2.mean(img[y:y+box_h, x:x+box_w])[0])
            rows.append({
                'file_id': name,
                'label': label,
                'values': ' '.join(f'{v:.2f}' for v in vals),
                'min_mean': f'{min(vals):.2f}',
                'max_mean': f'{max(vals):.2f}',
                'spread': f'{max(vals)-min(vals):.2f}',
                'full_select_candidate': str(max(vals) <= 170 and (max(vals)-min(vals)) <= 25),
            })
out=Path('outputs_inputs_21_full_select/q9_q11_full_select_stats.csv')
out.parent.mkdir(exist_ok=True, parents=True)
with out.open('w', newline='', encoding='utf-8') as f:
    w=csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)
print(out)
for r in rows:
    if r['full_select_candidate']=='True':
        print(r)
