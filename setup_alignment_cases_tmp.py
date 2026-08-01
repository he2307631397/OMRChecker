import json
import shutil
from pathlib import Path

BASE = Path('inputs')
ROOT = Path('alignment_experiments')
ROOT.mkdir(exist_ok=True)

def copy_case(name):
    dst = ROOT / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(BASE, dst, ignore=shutil.ignore_patterns('.gitignore'))
    return dst

# Baseline copy for repeatability
copy_case('baseline')

# Core field-block horizontal auto alignment
case = copy_case('auto_align')
config_path = case / 'config.json'
config = json.loads(config_path.read_text(encoding='utf-8'))
config.setdefault('alignment_params', {})['auto_align'] = True
config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')

# Page boundary crop/warp
case = copy_case('crop_page')
template_path = case / 'template.json'
template = json.loads(template_path.read_text(encoding='utf-8'))
template['preProcessors'] = [
    {'name': 'CropPage', 'options': {'morphKernel': [10, 10]}}
]
template_path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding='utf-8')

# Feature-based alignment to first currently-good PDF-rendered page.
# Create reference from 001 using the same PDF rendering path by copying checked output if available.
# A separate script will create reference.png if needed.
case = copy_case('feature_align')
template_path = case / 'template.json'
template = json.loads(template_path.read_text(encoding='utf-8'))
template['preProcessors'] = [
    {
        'name': 'FeatureBasedAlignment',
        'options': {
            'reference': 'reference.png',
            'maxFeatures': 2000,
            'goodMatchPercent': 0.25,
            '2d': True,
        }
    }
]
template_path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding='utf-8')
print(ROOT)
