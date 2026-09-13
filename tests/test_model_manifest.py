import json
from pathlib import Path


def test_model_manifest_has_expected_files():
    data = json.loads(Path('resources/model_manifest.json').read_text(encoding='utf-8'))
    files = {item['filename']: item for item in data['files']}
    assert set(files) == {
        'flux1-krea-dev.safetensors',
        'ae.safetensors',
        'clip_l.safetensors',
        't5xxl_fp16.safetensors',
    }
    assert files['flux1-krea-dev.safetensors']['requires_hf_token'] is True
    assert files['t5xxl_fp16.safetensors']['target_subdir'] == 'text_encoders'
