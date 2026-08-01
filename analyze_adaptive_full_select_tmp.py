from pathlib import Path
import csv
import cv2
import numpy as np
from src.utils.image import ImageUtils
from src.utils.parsing import open_config_with_defaults
from src.template import Template

config = open_config_with_defaults(Path('inputs/config.json'))
template = Template(Path('inputs/template.json'), config)
rows=[]
for file_path in sorted(Path('inputs').glob('*.pdf')):
    name, img = ImageUtils.load_omr_image(file_path, config)[0]
    img = template.image_instance_ops.apply_preprocessors(name, img, template)
    img = ImageUtils.resize_util(img, template.page_dimensions[0], template.page_dimensions[1])
    if img.max() > img.min():
        img = ImageUtils.normalize_util(img)
    all_vals=[]; groups=[]
    for field_block in template.field_blocks:
        box_w, box_h = field_block.bubble_dimensions
        for bubbles in field_block.traverse_bubbles:
            vals=[]
            for b in bubbles:
                x,y=b.x + field_block.shift,b.y
                vals.append(cv2.mean(img[y:y+box_h, x:x+box_w])[0])
            all_vals.extend(vals)
            groups.append((bubbles[0].field_label, vals, bubbles[0].multi_select))
    sorted_vals=sorted(all_vals)
    lighter_quartile=sorted_vals[int(len(sorted_vals)*0.75):]
    blank_baseline=float(np.mean(lighter_quartile))
    for label, vals, multi in groups:
        if multi:
            rows.append({
                'file_id': name,
                'label': label,
                'values': ' '.join(f'{v:.2f}' for v in vals),
                'max_mean': f'{max(vals):.2f}',
                'spread': f'{max(vals)-min(vals):.2f}',
                'page_blank_baseline': f'{blank_baseline:.2f}',
                'delta_from_page_blank': f'{blank_baseline-max(vals):.2f}',
                'adaptive_candidate': str(max(vals) <= 170 and max(vals)-min(vals) <= 25 and blank_baseline-max(vals) >= 35),
            })
out=Path('outputs_inputs_30_full_select_35/adaptive_full_select_stats.csv')
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('w', newline='', encoding='utf-8') as f:
    w=csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)
print(out)
for r in rows:
    if r['adaptive_candidate']=='True':
        print(r)
