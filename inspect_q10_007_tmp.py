from pathlib import Path
import cv2
from src.utils.image import ImageUtils
from src.utils.parsing import open_config_with_defaults
from src.template import Template
from src.core import ImageInstanceOps

config = open_config_with_defaults(Path('inputs/config.json'))
template = Template(Path('inputs/template.json'), config)
ops = ImageInstanceOps(config)
file_path = Path('inputs/MX-M3658N_20260731_123655_007.pdf')
name, img = ImageUtils.load_omr_image(file_path, config)[0]
img = template.image_instance_ops.apply_preprocessors(name, img, template)
img = ImageUtils.resize_util(img, template.page_dimensions[0], template.page_dimensions[1])
if img.max() > img.min():
    img = ImageUtils.normalize_util(img)

# reproduce mean collection enough to get q10 strip threshold
all_q_vals=[]; all_q_strip_arrs=[]; all_q_std_vals=[]
for field_block in template.field_blocks:
    box_w, box_h = field_block.bubble_dimensions
    for field_block_bubbles in field_block.traverse_bubbles:
        vals=[]
        for pt in field_block_bubbles:
            x,y = pt.x + field_block.shift, pt.y
            vals.append(cv2.mean(img[y:y+box_h, x:x+box_w])[0])
        all_q_strip_arrs.append(vals)
        all_q_vals.extend(vals)
        import numpy as np
        all_q_std_vals.append(round(np.std(vals),2))

global_std_thresh,_,_=ops.get_global_threshold(all_q_std_vals)
global_thr,_,_=ops.get_global_threshold(all_q_vals, looseness=4)
idx=0
for field_block in template.field_blocks:
    for field_block_bubbles in field_block.traverse_bubbles:
        label=field_block_bubbles[0].field_label
        vals=all_q_strip_arrs[idx]
        no_outliers=all_q_std_vals[idx] < global_std_thresh
        local_thr=ops.get_local_threshold(vals, global_thr, no_outliers, label, False)
        if label=='q10':
            print('name', name)
            print('global_thr', global_thr, 'global_std_thresh', global_std_thresh)
            print('q10 values A-D', vals)
            print('q10 std', all_q_std_vals[idx], 'no_outliers', no_outliers, 'local_thr', local_thr)
            print('detected', [b.field_value for b,v in zip(field_block_bubbles, vals) if local_thr > v])
        idx += 1
