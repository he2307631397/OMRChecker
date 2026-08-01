import json
import shutil
from pathlib import Path

src_ref = Path('alignment_experiments/feature_align/reference.png')
dst_ref = Path('inputs/reference.png')
if not src_ref.exists():
    raise SystemExit(f'Missing {src_ref}')
shutil.copy2(src_ref, dst_ref)

template_path = Path('inputs/template.json')
template = json.loads(template_path.read_text(encoding='utf-8'))
template['preProcessors'] = [
    {
        'name': 'FeatureBasedAlignment',
        'options': {
            'reference': 'reference.png',
            'maxFeatures': 2000,
            'goodMatchPercent': 0.25,
            '2d': True,
        },
    }
]
template_path.write_text(json.dumps(template, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('updated', template_path, 'and', dst_ref)
