import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
doc = json.loads((HERE / 'demo.json').read_text(encoding='utf-8'))
heads_doc = json.loads((HERE / 'heads.json').read_text(encoding='utf-8'))


def invoke(payload, expected_error=None, args=()):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'source.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        cmd = [sys.executable, '-B', '-m', 'reliefsheet', str(path), *args]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
    if expected_error:
        assert result.returncode == 2 and not result.stdout and expected_error in result.stderr, result
    else:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)


def finding_key(finding):
    if 'keepout' in finding:
        return ('keepout', tuple(finding['dot']), finding['keepout'])
    if 'dots' in finding:
        return (finding['rule'], tuple(finding['dots'][0]), tuple(finding['dots'][1]))
    return (finding['rule'], tuple(finding['dot']))


def registered(report):
    return {tuple(row['dot']): row for row in report['registered_dots']}


# --- Ordinary single-cell report is unchanged. -----------------------------
out = invoke(doc)
assert out['accepted'] is False
assert {f['rule'] for f in out['findings']} == {'keepout', 'opposite-face'}
assert next(r['at'] for r in out['registered_dots'] if r['dot'] == ['back', 'B-left']) == [3, 4]
assert all(set(row) == {'dot', 'at'} for row in out['registered_dots'])
doc['back'] = []
assert invoke(doc)['accepted'] is True
doc['front'][0]['at'] = [12, 0]
invoke(doc, 'dot outside its drawing')

# --- One model on both faces; original identity and paper/drawing evidence. -
report = invoke(heads_doc)
rows = registered(report)
faces = {row['dot'][0] for row in report['registered_dots'] if row.get('head') == 'dual-pad'}
assert faces == {'front', 'back'}

back_dual = rows['back', 'B-dual']
front_dual = rows['front', 'F-dual']
assert back_dual['drawing'] == [12, 5] and back_dual['at'] == [8, 5]
assert back_dual['paper'] == [6, 5, 9, 6]      # mirrored head, no double reflection
assert front_dual['paper'] == [5, 5, 8, 6]

# Marker centres meet the opposite-face minimum, but the occupied bodies clash.
centre = max(abs(front_dual['at'][0] - back_dual['at'][0]),
             abs(front_dual['at'][1] - back_dual['at'][1]))
assert centre >= heads_doc['min_opposite']
pair = next(f for f in report['findings']
            if f.get('dots') == [['back', 'B-dual'], ['front', 'F-dual']])
assert pair['rule'] == 'opposite-face' and pair['distance'] == 0
assert pair['drawing'] == [[14, 5], [6, 5]]    # back evidence maps to its drawing cell

# --- Every evidence piece traces back to its source drawing cell. ----------
for finding in report['findings']:
    if finding.get('head') is None:
        continue
    assert len(finding['drawing']) in (2, 4)
edge = next(f for f in report['findings']
            if f['rule'] == 'outside' and f['dot'] == ['back', 'B-edge'])
assert edge['paper'] == [-1, 5] and edge['drawing'] == [21, 5]

# A head that ends exactly at a keepout edge does not overlap it, so the dot
# is never reported for that keepout.
touch = rows['front', 'F-touch']
assert touch['paper'] == [12, 2, 15, 3]
assert not any(f['rule'] == 'keepout' and f['dot'] == ['front', 'F-touch']
               for f in report['findings'])

# --- Replace one model definition; three classes, only affected objects. ----
REPLACEMENT = [0, -2, 2, 1]
rev = invoke(heads_doc, args=('--replace-head', 'dual-pad:0,-2,2,1'))['revision']
assert rev['head'] == 'dual-pad'
assert rev['before'] == [0, 0, 3, 1] and rev['after'] == REPLACEMENT
assert rev['added'] and rev['removed'] and rev['changed']
assert all(row['head'] == 'dual-pad' for row in rev['affected_dots'])

# The correction touches the hanger keepout exactly instead of overlapping it.
assert any(f['rule'] == 'keepout' and f.get('dot') == ['front', 'F-dual']
           and f['keepout'] == 'hanger' for f in rev['removed'])
assert rows['front', 'F-dual']['paper'] == [5, 5, 8, 6]

# Compare against a full rerun with the same definition swapped in place.
edited = json.loads(json.dumps(heads_doc))
for row in edited['heads']:
    if row['id'] == 'dual-pad':
        row['rect'] = REPLACEMENT
full = {finding_key(f): f for f in invoke(edited)['findings']}
for finding in rev['added']:
    assert full[finding_key(finding)] == finding
for finding in rev['removed']:
    assert finding_key(finding) not in full
for change in rev['changed']:
    assert change['before'] != change['after']
    assert full[finding_key(change['after'])] == change['after']

# Objects that do not select the model are never re-judged.
selects = {(row['dot'][0], row['dot'][1]): row.get('head')
           for row in report['registered_dots']}
for finding in rev['added'] + rev['removed']:
    dots = [finding['dot']] if 'dot' in finding else finding['dots']
    assert any(selects[tuple(dot)] == 'dual-pad' for dot in dots)

# A replacement that widens the head adds keepout evidence on the far side.
wider = invoke(heads_doc, args=('--replace-head', 'pad-3x1:0,0,4,1'))['revision']
assert any(f['rule'] == 'keepout' and f['dot'] == ['front', 'F-touch']
           for f in wider['added'])

# Revision requests embedded in the source document behave like the flag.
embedded = json.loads(json.dumps(heads_doc))
embedded['revision'] = {'head': 'dual-pad', 'rect': REPLACEMENT}
assert invoke(embedded)['revision']['removed'] == rev['removed']

invoke(heads_doc, 'unknown head to replace', args=('--replace-head', 'nope:0,0,1,1'))
invoke(heads_doc, 'containing the marker cell', args=('--replace-head', 'dual-pad:1,0,3,1'))
stray = json.loads(json.dumps(heads_doc))
stray['front'][0]['head'] = 'missing-model'
invoke(stray, 'unknown head')
print('production smoke: PASS (reliefsheet)')
