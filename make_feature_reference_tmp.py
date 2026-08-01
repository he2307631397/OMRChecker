from pathlib import Path
import cv2
from src.utils.image import ImageUtils
from src.utils.parsing import open_config_with_defaults

case = Path('alignment_experiments/feature_align')
config = open_config_with_defaults(case / 'config.json')
first_pdf = sorted(case.glob('*.pdf'))[0]
img_name, img = ImageUtils.load_omr_image(first_pdf, config)[0]
img = ImageUtils.resize_util(img, config.dimensions.processing_width, config.dimensions.processing_height)
if img.max() > img.min():
    img = ImageUtils.normalize_util(img)
cv2.imwrite(str(case / 'reference.png'), img)
print(case / 'reference.png')
