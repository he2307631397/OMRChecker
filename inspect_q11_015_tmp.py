from pathlib import Path
import cv2
import numpy as np
from src.utils.image import ImageUtils
from src.utils.parsing import open_config_with_defaults
from src.template import Template
from src.core import ImageInstanceOps

TARGET = 'MX-M3658N_20260731_153802_015.pdf'
LABEL = 'q11'
config = open_config_with_defaults(Path('inputs/config.json'))
template = Template(Path('inputs/template.json'), config)
ops = ImageInstanceOps(config)
file_path = Path('inputs') / TARGET
name, img = ImageUtils.load_omr_image(file_path, config)[0]
img = template.image_instance_ops.apply_preprocessors(name, img, template)
img = ImageUtils.resize_util(img, template.page_dimensions[0], template.page_dimensions[1])
if img.max() > img.min():
    img = ImageUtils.normalize_util(img)
all_q_vals=[]; all_q_strip_arrs=[]; all_q_std_vals=[]; labels=[]; bubble_groups=[]
for field_block in template.field_blocks:
    box_w, box_h = field_block.bubble_dimensions
    for bubbles in field_block.traverse_bubbles:
        vals=[]
        for pt in bubbles:
            x,y=pt.x+field_block.shift,pt.y
            vals.append(cv2.mean(img[y:y+box_h, x:x+box_w])[0])
        all_q_strip_arrs.append(vals); all_q_vals.extend(vals); all_q_std_vals.append(round(np.std(vals),2)); labels.append(bubbles[0].field_label); bubble_groups.append(bubbles)
global_std_thresh,_,_=ops.get_global_threshold(all_q_std_vals)
global_thr,_,_=ops.get_global_threshold(all_q_vals, looseness=4)
for idx,label in enumerate(labels):
    if label == LABEL:
        vals=all_q_strip_arrs[idx]
        no_outliers=all_q_std_vals[idx] < global_std_thresh
        local_thr=ops.get_local_threshold(vals, global_thr, no_outliers, LABEL, False)
        detected=[b.field_value for b,v in zip(bubble_groups[idx], vals) if local_thr > v]
        weak=ops.get_weak_multi_marked_bubbles(bubble_groups[idx], vals, [])
        full=ops.get_weak_multi_full_select_bubbles(bubble_groups[idx], vals, [], global_thr)
        print('name', name)
        print('global_thr', global_thr, 'global_std_thresh', global_std_thresh)
        print('q11 values A-D', vals)
        print('q11 std', all_q_std_vals[idx], 'no_outliers', no_outliers, 'local_thr', local_thr)
        print('detected', detected)
        print('weak_multi', [b.field_value for b in weak])
        print('full_select', [b.field_value for b in full])
        print('blank_baseline', float(np.mean(sorted(vals)[len(vals)//2:])))
