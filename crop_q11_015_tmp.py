from pathlib import Path
import cv2
img_path=Path('outputs_inputs_30_review/CheckedOMRs/MX-M3658N_20260731_153802_015.png')
img=cv2.imread(str(img_path))
# crop around q9-q11 area
crop=img[880:1010, 90:720]
out=Path('outputs_inputs_30_review/q11_015_crop.png')
cv2.imwrite(str(out), crop)
print(out)
