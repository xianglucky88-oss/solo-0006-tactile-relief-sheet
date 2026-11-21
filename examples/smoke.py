import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MERGE = HERE / 'merge'
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


def _label(obj):
    if obj['kind'] == 'setting':
        return f"setting:{obj['name']}"
    if obj['kind'] == 'dot':
        return f"dot:{obj['face']}/{obj['id']}"
    return f"keepout:{obj['id']}"


def merge(name_base, name_left, name_right):
    paths = [MERGE / f'{name}.json' for name in (name_base, name_left, name_right)]
    cmd = [sys.executable, '-B', '-m', 'reliefsheet', '--merge',
           *[str(path) for path in paths]]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# --- single-document report -------------------------------------------------
out = invoke(doc)
assert out['accepted'] is False
assert {f['rule'] for f in out['findings']} == {'keepout', 'opposite-face'}
assert next(r['at'] for r in out['registered_dots'] if r['dot'] == ['back', 'B-left']) == [3, 4]
doc['back'] = []
assert invoke(doc)['accepted'] is True
doc['front'][0]['at'] = [12, 0]
invoke(doc, 'dot outside its drawing')

# --- merge: both revisions pass, the merge does not -------------------------
merged = merge('base', 'both-pass-left', 'both-pass-right')
assert merged['mergeable'] is True
assert merged['reports']['left']['accepted'] is True
assert merged['reports']['right']['accepted'] is True
assert merged['reports']['merged']['accepted'] is False
summary = merged['comparison']['summary']
assert summary['merge_new_count'] == 1
assert summary['branch_existing_count'] == 0
new = [entry for entry in merged['comparison']['findings']
       if entry['status'] == 'merge-new']
assert new[0]['identity'] == {'rule': 'same-face',
                              'dots': [['front', 'A'], ['front', 'B']]}
assert new[0]['present_in'] == {'baseline': False, 'left': False, 'right': False}

# every smallest cause is delivered, including a threshold change and two moves
diagnostic = merged['diagnostics'][0]
assert diagnostic['minimal_edit_count'] == 2
assert len(diagnostic['minimal_combinations']) == 2
shapes = set()
for combination in diagnostic['minimal_combinations']:
    assert combination['edit_count'] == 2
    objects = {_label(item['object']) for item in combination['edits']}
    shapes.add(frozenset(objects))
    replay = combination['replay']
    # The replay selects what the combination actually carried, not what the
    # complete merge happened to select.
    assert replay['selected']['min_same'] in (2, 3)
    assert replay['after']['finding']['rule'] == 'same-face'
    for edit in combination['edits']:
        assert edit['revision_source'] in ('left', 'right')
assert frozenset({'setting:min_same', 'dot:front/A'}) in shapes
assert frozenset({'dot:front/A', 'dot:front/B'}) in shapes

# replay re-registers with the combination's own offset instead of the merge's
replayed = merge('replay-base', 'replay-left', 'replay-right')
assert replayed['merged_document']['back_offset'] == [3, 1]
for diagnostic in replayed['diagnostics']:
    for combination in diagnostic['minimal_combinations']:
        assert combination['replay']['selected']['back_offset'] == [0, 0]
        replay_doc = combination['replay']['document']
        assert replay_doc['back_offset'] == [0, 0]

# offset change and raw back move are a different minimal cause of a new clash
offset = merge('offset-base', 'offset-left', 'offset-right')
assert offset['reports']['left']['accepted'] is True
assert offset['reports']['right']['accepted'] is True
assert offset['comparison']['summary']['merge_new_count'] == 1
combination = offset['diagnostics'][0]['minimal_combinations'][0]
assert combination['edit_count'] == 2
assert {_label(item['object']) for item in combination['edits']} == {
    'setting:back_offset', 'dot:back/B'}
assert combination['replay']['selected']['back_offset'] == [-2, 0]

# same identity with a changed distance is not a new conflict
distance = merge('distance-base', 'distance-left', 'distance-right')
assert distance['mergeable'] is True
assert distance['comparison']['summary']['merge_new_count'] == 0
entry = distance['comparison']['findings'][0]
assert entry['status'] == 'branch-existing'
assert entry['distances']['left'] != entry['distances']['right']
assert entry['distances']['right'] != entry['distances']['merged']
assert entry['distances']['required'] == 6

# delete-versus-modify stops the merge and produces no merged document
stopped = merge('delete-base', 'delete-left', 'delete-right')
assert stopped['mergeable'] is False
assert stopped['merged_document'] is None
assert stopped['structural_conflicts'][0]['reason'] == 'delete-vs-modify'

# identical edits on both revisions collapse to one edit
same = merge('base', 'same-value-left', 'same-value-right')
assert same['object_edit_count'] == 2
assert all(edit['revision_source'] == 'both' for edit in same['edits'])

# no new conflicts still ships the merge graph and both-branch comparison
clean = merge('base', 'clean-left', 'clean-right')
assert clean['comparison']['summary']['merge_new_count'] == 0
assert clean['merged_document'] is not None
assert clean['reports']['left'] and clean['reports']['right']
assert {item['disposition'] for item in clean['merge_graph']} >= {
    'merged-from-left', 'merged-from-right'}

# malformed merge input is rejected with no partial output
with tempfile.TemporaryDirectory() as temp:
    bad = Path(temp) / 'bad.json'
    bad.write_text('{"grid": [0, 0]}', encoding='utf-8')
    cmd = [sys.executable, '-B', '-m', 'reliefsheet', '--merge', str(bad),
           str(MERGE / 'base.json'), str(MERGE / 'base.json')]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
assert result.returncode == 2 and not result.stdout and result.stderr
print('production smoke: PASS (reliefsheet)')
