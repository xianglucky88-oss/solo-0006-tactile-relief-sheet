"""Three-way merge and minimal-cause replay for reliefsheet documents.

A sheet is merged as a set of independent objects:

* a dot is identified by ``(face, id)`` and its **raw drawing coordinate** is
  the value that is compared, so registration never hides an edit;
* a keepout is identified by its ``id`` and its raw rectangle is compared;
* ``back_offset``, ``min_same`` and ``min_opposite`` are three independent
  scalar objects.

Registration and rule evaluation are only performed after a value has been
selected.  A replay is always built from the baseline plus the edits of one
combination, so it re-registers with the offset and re-evaluates with the
thresholds that the combination actually selected instead of borrowing state
from the complete merge.

The search stays bounded: a finding identity depends on at most four objects,
so minimal-cause replay only enumerates subsets of those objects rather than
subsets of every object edit, no matter how many objects were edited.
"""
from copy import deepcopy
from itertools import combinations

from .pipeline import run


_SETTING_FIELDS = ('back_offset', 'min_same', 'min_opposite')
_DOT_FACES = ('front', 'back')
_PAIR_RULES = ('same-face', 'opposite-face')


# ---------------------------------------------------------------------------
# object identity and raw values


def _object_key(kind, *parts):
    return (kind,) + tuple(parts)


def _object_label(key):
    if key[0] == 'setting':
        return {'kind': 'setting', 'name': key[1]}
    if key[0] == 'dot':
        return {'kind': 'dot', 'face': key[1], 'id': key[2]}
    if key[0] == 'keepout':
        return {'kind': 'keepout', 'id': key[1]}
    return {'kind': key[0]}


def _sort_key(key):
    order = {'grid': 0, 'setting': 1, 'dot': 2, 'keepout': 3}
    if key[0] == 'setting':
        return (order[key[0]], _SETTING_FIELDS.index(key[1]))
    if key[0] == 'dot':
        return (order[key[0]], _DOT_FACES.index(key[1]), key[2])
    if key[0] == 'keepout':
        return (order[key[0]], key[1])
    return (order[key[0]],)


def _as_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _same(left, right):
    return _as_list(left) == _as_list(right)


def _document_values(document):
    """Return raw values keyed by object identity (``None`` when absent)."""
    values = {_object_key('grid'): list(document['grid'])}
    for face in _DOT_FACES:
        for row in document[face]:
            values[_object_key('dot', face, row['id'])] = list(row['at'])
    for row in document['keepouts']:
        values[_object_key('keepout', row['id'])] = list(row['rect'])
    for field in _SETTING_FIELDS:
        values[_object_key('setting', field)] = _as_list(document[field])
    return values


def _raw_dot(document, label):
    face, name = label
    for row in document[face]:
        if row['id'] == name:
            return list(row['at'])
    return None


# ---------------------------------------------------------------------------
# structural merge


def _structural_entry(graph_entry):
    return {
        'object': deepcopy(graph_entry['object']),
        'before': deepcopy(graph_entry['before']),
        'left': deepcopy(graph_entry['left']),
        'right': deepcopy(graph_entry['right']),
        'reason': graph_entry['conflict_reason'],
    }


def _edit(key, before, after, source):
    return {'_key': key, 'before': _as_list(before), 'after': _as_list(after),
            'source': source,
            'sources': ['left', 'right'] if source == 'both' else [source]}


def _public_edit(edit):
    return {
        'object': _object_label(edit['_key']),
        'before': deepcopy(edit['before']),
        'after': deepcopy(edit['after']),
        'revision_source': edit['source'],
        'revision_sources': list(edit['sources']),
    }


def _merge_objects(baseline, left, right):
    """Return ``(merge graph, selected edits, structural conflicts)``.

    Revisions that changed an object to the same value produce one edit whose
    source is ``both``.  Delete-versus-modify and two different values stop
    the merge instead of inventing a value.
    """
    base_values = _document_values(baseline)
    left_values = _document_values(left)
    right_values = _document_values(right)
    keys = set(base_values) | set(left_values) | set(right_values)
    graph = []
    edits = []
    structural = []

    for key in sorted(keys, key=_sort_key):
        before = base_values.get(key)
        left_value = left_values.get(key)
        right_value = right_values.get(key)
        entry = {
            'object': _object_label(key),
            'before': deepcopy(before),
            'left': deepcopy(left_value),
            'right': deepcopy(right_value),
            'merged': deepcopy(before),
            'disposition': 'unchanged',
            'conflict_reason': None,
        }

        if key[0] == 'grid':
            if not (_same(left_value, before) and _same(right_value, before)):
                entry['merged'] = None
                entry['disposition'] = 'conflict'
                entry['conflict_reason'] = 'fixed-grid-changed'
                structural.append(_structural_entry(entry))
            graph.append(entry)
            continue

        if _same(left_value, right_value):
            if not _same(left_value, before):
                entry['disposition'] = 'merged-from-both'
                entry['merged'] = deepcopy(left_value)
                edits.append(_edit(key, before, left_value, 'both'))
            graph.append(entry)
            continue

        if _same(left_value, before):
            entry['disposition'] = 'merged-from-right'
            entry['merged'] = deepcopy(right_value)
            edits.append(_edit(key, before, right_value, 'right'))
            graph.append(entry)
            continue

        if _same(right_value, before):
            entry['disposition'] = 'merged-from-left'
            entry['merged'] = deepcopy(left_value)
            edits.append(_edit(key, before, left_value, 'left'))
            graph.append(entry)
            continue

        if before is None:
            reason = 'divergent-additions'
        elif left_value is None or right_value is None:
            reason = 'delete-vs-modify'
        else:
            reason = 'different-values'
        entry['merged'] = None
        entry['disposition'] = 'conflict'
        entry['conflict_reason'] = reason
        structural.append(_structural_entry(entry))
        graph.append(entry)

    return graph, edits, structural


def _find_row(rows, name):
    for index, row in enumerate(rows):
        if row['id'] == name:
            return index
    return None


def apply_edits(document, edits):
    """Apply only ``edits`` to ``document`` (normally the baseline).

    Registration is intentionally left to the caller, which re-runs the
    production pipeline on the result.
    """
    result = deepcopy(document)
    for edit in sorted(edits, key=lambda item: _sort_key(item['_key'])):
        key = edit['_key']
        value = deepcopy(edit['after'])
        if key[0] == 'setting':
            result[key[1]] = value
        elif key[0] == 'dot':
            rows = result[key[1]]
            index = _find_row(rows, key[2])
            if value is None:
                if index is not None:
                    rows.pop(index)
            elif index is None:
                rows.append({'id': key[2], 'at': value})
            else:
                rows[index]['at'] = value
        elif key[0] == 'keepout':
            rows = result['keepouts']
            index = _find_row(rows, key[1])
            if value is None:
                if index is not None:
                    rows.pop(index)
            elif index is None:
                rows.append({'id': key[1], 'rect': value})
            else:
                rows[index]['rect'] = value
        else:
            raise ValueError(f'cannot apply edit to {key[0]}')
    return result


# ---------------------------------------------------------------------------
# conflict identity and comparison


def _finding_key(finding):
    """Identity: rule plus the involved *original* objects.

    Distance and required clearance are excluded, so a finding whose distance
    changes remains the same item.
    """
    rule = finding['rule']
    if rule == 'outside':
        return ('outside', tuple(finding['dot']))
    if rule == 'keepout':
        return ('keepout', tuple(finding['dot']), finding['keepout'])
    dots = sorted(tuple(item) for item in finding['dots'])
    return (rule, dots[0], dots[1])


def _finding_identity(key):
    if key[0] == 'outside':
        return {'rule': 'outside', 'dot': list(key[1])}
    if key[0] == 'keepout':
        return {'rule': 'keepout', 'dot': list(key[1]), 'keepout': key[2]}
    return {'rule': key[0], 'dots': [list(key[1]), list(key[2])]}


def _finding_key_from_identity(identity):
    rule = identity['rule']
    if rule == 'outside':
        return ('outside', tuple(identity['dot']))
    if rule == 'keepout':
        return ('keepout', tuple(identity['dot']), identity['keepout'])
    dots = sorted(tuple(item) for item in identity['dots'])
    return (rule, dots[0], dots[1])


def _findings_by_key(report):
    return {_finding_key(finding): finding for finding in report['findings']}


def _distance(finding):
    return None if finding is None else finding.get('distance')


def _compare_reports(reports):
    baseline = _findings_by_key(reports['baseline'])
    left = _findings_by_key(reports['left'])
    right = _findings_by_key(reports['right'])
    merged = _findings_by_key(reports['merged'])

    entries = []
    for key, finding in merged.items():
        branches = {'left': left.get(key), 'right': right.get(key)}
        present = {'baseline': key in baseline, 'left': key in left,
                   'right': key in right}
        entries.append({
            'identity': _finding_identity(key),
            'status': 'branch-existing' if present['left'] or present['right']
                      else 'merge-new',
            'present_in': present,
            'merged': deepcopy(finding),
            'branches': {name: deepcopy(value)
                         for name, value in branches.items()},
            'baseline': deepcopy(baseline.get(key)),
            # Same identity may carry a different distance in each revision;
            # record the move without promoting it to a new conflict.
            'distances': {
                'baseline': _distance(baseline.get(key)),
                'left': _distance(branches['left']),
                'right': _distance(branches['right']),
                'merged': _distance(finding),
                'required': finding.get('required'),
            },
        })

    resolved = []
    merged_keys = set(merged)
    for key in sorted(set(baseline) | set(left) | set(right)):
        if key in merged_keys:
            continue
        resolved.append({
            'identity': _finding_identity(key),
            'present_in': {'baseline': key in baseline, 'left': key in left,
                           'right': key in right, 'merged': False},
            'baseline': deepcopy(baseline.get(key)),
            'branches': {'left': deepcopy(left.get(key)),
                         'right': deepcopy(right.get(key))},
            'merged': None,
        })

    summary = {
        'baseline_count': len(baseline),
        'left_count': len(left),
        'right_count': len(right),
        'merged_count': len(merged),
        'merge_new_count': sum(1 for entry in entries
                               if entry['status'] == 'merge-new'),
        'merge_new_already_in_baseline_count': sum(
            1 for entry in entries if entry['status'] == 'merge-new'
            and entry['present_in']['baseline']),
        'branch_existing_count': sum(1 for entry in entries
                                     if entry['status'] == 'branch-existing'),
        'resolved_count': len(resolved),
        'accepted': {name: reports[name]['accepted']
                     for name in ('baseline', 'left', 'right', 'merged')},
    }
    return {'summary': summary, 'findings': entries,
            'resolved_findings': resolved}


# ---------------------------------------------------------------------------
# minimal causes


def _candidate_edits(key, edits):
    """Edits that can influence this finding identity, and no others.

    A paired finding depends only on its two dots, the applicable threshold
    and, when a back dot is involved, the back offset.  A keepout or outside
    finding depends only on its dot, the named keepout for the keepout rule,
    and the back offset for a back dot.  The candidate set therefore has at
    most four members, which bounds the replay search.
    """
    by_key = {edit['_key']: edit for edit in edits}
    wanted = []
    rule = key[0]
    if rule in _PAIR_RULES:
        first, second = key[1], key[2]
        wanted.append(_object_key('dot', first[0], first[1]))
        wanted.append(_object_key('dot', second[0], second[1]))
        same_face = first[0] == second[0]
        wanted.append(_object_key(
            'setting', 'min_same' if same_face else 'min_opposite'))
        if 'back' in (first[0], second[0]):
            wanted.append(_object_key('setting', 'back_offset'))
    elif rule == 'keepout':
        dot = key[1]
        wanted.append(_object_key('dot', dot[0], dot[1]))
        wanted.append(_object_key('keepout', key[2]))
        if dot[0] == 'back':
            wanted.append(_object_key('setting', 'back_offset'))
    else:
        dot = key[1]
        wanted.append(_object_key('dot', dot[0], dot[1]))
        if dot[0] == 'back':
            wanted.append(_object_key('setting', 'back_offset'))
    return [by_key[object_key] for object_key in sorted(set(wanted),
                                                        key=_sort_key)
            if object_key in by_key]


def _spans_both_branches(combo):
    """Whether the combination draws on both revisions.

    Rule findings are not monotone in the edits: a branch document can contain
    an edit that reproduces an identity and another edit that suppresses it.
    So this is reported as an interaction marker rather than used to prune
    reproduction, otherwise a genuinely smallest cause would be hidden.
    """
    sources = [set(edit['sources']) for edit in combo]
    return (any(source == {'left'} for source in sources)
            and any(source == {'right'} for source in sources))


def _involved_labels(key):
    if key[0] in ('outside', 'keepout'):
        return [list(key[1])]
    return [list(key[1]), list(key[2])]


def _registered_for(report, labels):
    wanted = {tuple(label) for label in labels}
    return [deepcopy(entry) for entry in report['registered_dots']
            if tuple(entry['dot']) in wanted]


def _combination_evidence(baseline, key, combo, replay_document,
                          replay_report, replay_finding, baseline_finding,
                          baseline_report, revision_sources):
    labels = _involved_labels(key)
    before_objects = [{'object': {'kind': 'dot', 'face': label[0],
                                  'id': label[1]},
                       'value': _raw_dot(baseline, label)}
                      for label in labels]
    after_objects = [{'object': {'kind': 'dot', 'face': label[0],
                                 'id': label[1]},
                      'value': _raw_dot(replay_document, label)}
                     for label in labels]
    edits = []
    for edit in combo:
        public = _public_edit(edit)
        public['revision'] = [revision_sources[name]
                              for name in edit['sources']]
        edits.append(public)
    return {
        'edit_count': len(combo),
        'spans_both_revisions': _spans_both_branches(combo),
        'edits': edits,
        'replay': {
            'basis': 'baseline plus only these edits',
            'selected': {
                'back_offset': list(replay_document['back_offset']),
                'min_same': replay_document['min_same'],
                'min_opposite': replay_document['min_opposite'],
            },
            'before': {
                'settings': {
                    'back_offset': list(baseline['back_offset']),
                    'min_same': baseline['min_same'],
                    'min_opposite': baseline['min_opposite'],
                },
                'finding': deepcopy(baseline_finding),
                'objects': before_objects,
                'registered_dots': _registered_for(baseline_report, labels),
            },
            'after': {
                'finding': deepcopy(replay_finding),
                'objects': after_objects,
                'registered_dots': _registered_for(replay_report, labels),
            },
            # Exact inputs and full rule output of the replay, so the
            # combination can be re-checked without the complete merge.
            'document': replay_document,
            'registered_dots': deepcopy(replay_report['registered_dots']),
            'findings': deepcopy(replay_report['findings']),
        },
    }


def _minimal_combinations(baseline, key, candidates, baseline_finding,
                          baseline_report, revision_sources):
    """All smallest combinations that reproduce ``key`` from the baseline."""
    if baseline_finding is not None:
        # The identity already holds on the baseline, so the empty combination
        # is the zero-edit minimal cause; adding edits can only be larger.
        return [_combination_evidence(
            baseline, key, [], baseline, baseline_report, baseline_finding,
            baseline_finding, baseline_report, revision_sources)]
    if not candidates:
        return []
    for size in range(1, len(candidates) + 1):
        found = []
        for combo in combinations(candidates, size):
            replay_document = apply_edits(baseline, list(combo))
            try:
                replay_report = run(replay_document)
            except ValueError:
                # The combination is not a valid sheet, so it cannot stand in
                # for the merged revision.
                continue
            replay_finding = _findings_by_key(replay_report).get(key)
            if replay_finding is None:
                continue
            found.append(_combination_evidence(
                baseline, key, list(combo), replay_document, replay_report,
                replay_finding, baseline_finding, baseline_report,
                revision_sources))
        if found:
            return found
    return []


def _diagnostics(comparison, edits, baseline, baseline_report,
                 revision_sources):
    baseline_map = _findings_by_key(baseline_report)
    result = []
    for entry in comparison['findings']:
        if entry['status'] != 'merge-new':
            continue
        key = _finding_key_from_identity(entry['identity'])
        candidates = _candidate_edits(key, edits)
        combos = _minimal_combinations(
            baseline, key, candidates, baseline_map.get(key),
            baseline_report, revision_sources)
        interacting = [combo for combo in combos
                       if combo['spans_both_revisions']]
        by_branch = {'left': [], 'right': []}
        for edit in candidates:
            for name in edit['sources']:
                by_branch[name].append(_public_edit(edit))
        result.append({
            'identity': deepcopy(entry['identity']),
            'merged': deepcopy(entry['merged']),
            'branch_edits': by_branch,
            'candidate_edits': [_public_edit(edit) for edit in candidates],
            'candidate_edit_count': len(candidates),
            'minimal_edit_count': combos[0]['edit_count'] if combos else None,
            'minimal_combinations': combos,
            'interaction_minimal_edit_count': (
                interacting[0]['edit_count'] if interacting else None),
            'interaction_combination_count': len(interacting),
            'reproduced': bool(combos),
        })
        if not combos:
            result[-1]['reproduction_note'] = (
                'no subset of the dependency edits reproduced this identity '
                'from the baseline')
    return result


# ---------------------------------------------------------------------------
# public entry point


def merge_documents(baseline, left, right, revision_sources=None):
    """Return a deterministic, auditable three-way merge report.

    A structural disagreement stops the merge: ``mergeable`` is false and no
    merged document is produced.  Otherwise the complete merged document, the
    two branch reports, the merged report, an object-level merge graph and a
    branch/merge comparison are returned even when the merged finding set is
    unchanged.  Every merge-new finding carries every smallest baseline replay
    that reproduces its identity.
    """
    if revision_sources is None:
        revision_sources = {'baseline': 'baseline', 'left': 'left',
                            'right': 'right'}

    baseline_report = run(baseline)
    left_report = run(left)
    right_report = run(right)

    graph, edits, structural = _merge_objects(baseline, left, right)
    report = {
        'mode': 'merge',
        'revision_sources': deepcopy(revision_sources),
        'mergeable': False,
        'structural_conflicts': structural,
        'object_edit_count': len(edits),
        'search': {
            'candidate_scope': 'per-finding dependency objects',
            'maximum_candidates_per_finding': 4,
            'enumerates_all_object_edit_subsets': False,
        },
        'edits': [_public_edit(edit) for edit in edits],
        'merge_graph': graph,
        'reports': {'baseline': baseline_report, 'left': left_report,
                    'right': right_report},
        'merged_document': None,
        'comparison': None,
        'diagnostics': [],
    }
    if structural:
        return report

    merged_document = apply_edits(baseline, edits)
    merged_report = run(merged_document)
    report['mergeable'] = True
    report['merged_document'] = merged_document
    report['reports']['merged'] = merged_report
    comparison = _compare_reports(report['reports'])
    report['comparison'] = comparison
    report['diagnostics'] = _diagnostics(
        comparison, edits, baseline, baseline_report, revision_sources)
    return report
