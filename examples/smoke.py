import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
doc = json.loads((HERE / 'demo.json').read_text(encoding='utf-8'))


def invoke(payload, expected_error=None):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'source.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        cmd = [sys.executable, '-B', '-m', 'reliefsheet', str(path)]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
    if expected_error:
        assert result.returncode == 2 and not result.stdout and expected_error in result.stderr, result
    else:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)


out = invoke(doc)
assert out['accepted'] is False
assert {f['rule'] for f in out['findings']} == {'keepout', 'opposite-face'}
assert next(r['at'] for r in out['registered_dots'] if r['dot'] == ['back', 'B-left']) == [3, 4]
doc['back'] = []
assert invoke(doc)['accepted'] is True
doc['front'][0]['at'] = [12, 0]
invoke(doc, 'dot outside its drawing')
print('production smoke: PASS (reliefsheet)')
