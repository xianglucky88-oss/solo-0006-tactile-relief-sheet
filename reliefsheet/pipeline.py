"""Report construction and one-model revision comparison.

``run`` emits the full report.  When the source document carries a revision
request (a replacement head definition) or the CLI passes ``--replace-head``,
the plate maker's model swap is evaluated instead.
"""

from itertools import combinations

from .clearance import (dot_findings, evidence_key, evidence_order, findings,
                        label, pair_finding, paper_rect)
from .plates import parse


def thresholds(document):
    same, opposite = document['min_same'], document['min_opposite']
    if any(type(v) is not int or not 1 <= v <= 2048 for v in (same, opposite)):
        raise ValueError('minimum clearances must be positive grid distances')
    return same, opposite


def registered(dot):
    row = {'dot': label(dot), 'at': [dot.x, dot.y]}
    if dot.rect is not None:
        # Keep the original drawing cell next to the registered paper marker.
        row.update(head=dot.head, drawing=[dot.source_x, dot.source_y],
                   paper=list(paper_rect(dot)))
    return row


def _involving(dots, head):
    return [dot for dot in dots if dot.head == head]


def _evidence(width, height, dots, keepouts, same, opposite, head):
    """Evidence for the selected model's objects and their pair partners.

    Evidence keys are identity based, so evidence that persists with different
    details keeps its key and surfaces as a change rather than an
    add/remove pair.
    """

    collect = {}
    for dot in _involving(dots, head):
        for finding in dot_findings(width, height, dot, keepouts):
            collect[evidence_key(finding)] = finding
    for a, b in combinations(dots, 2):
        if a.head != head and b.head != head:
            continue
        finding = pair_finding(a, b, same, opposite)
        if finding is not None:
            collect[evidence_key(finding)] = finding
    return collect


def revision(document, head, rect):
    """Swap one head definition and report only its affected evidence.

    ``head`` names an existing model and ``rect`` is the replacement relative
    half-open placement.  Returns added, removed and changed evidence plus the
    replacement placement of every affected object.  Objects that do not
    select the model are never re-judged.
    """

    same, opposite = thresholds(document)
    old_width, old_height, old_dots, old_keepouts, old_heads = parse(document)
    new_width, new_height, new_dots, new_keepouts, new_heads = parse(
        document, (head, rect))
    if head not in old_heads:
        raise ValueError(f'unknown head to replace: {head}')

    before = _evidence(old_width, old_height, old_dots, old_keepouts,
                       same, opposite, head)
    after = _evidence(new_width, new_height, new_dots, new_keepouts,
                      same, opposite, head)

    added = [after[key] for key in
             sorted(after, key=lambda k: (evidence_order(after[k]), k))
             if key not in before]
    removed = [before[key] for key in
               sorted(before, key=lambda k: (evidence_order(before[k]), k))
               if key not in after]
    changed = [{'before': before[key], 'after': after[key]}
               for key in sorted(after, key=lambda k: (evidence_order(after[k]), k))
               if key in before and before[key] != after[key]]

    affected = sorted(_involving(new_dots, head),
                      key=lambda dot: (dot.face, dot.name))
    return {'revision': {
        'head': head,
        'before': list(old_heads[head]),
        'after': list(new_heads[head]),
        'affected_dots': [registered(dot) for dot in affected],
        'added': added,
        'removed': removed,
        'changed': changed,
    }}


_REVISION_KEYS = ('revision', 'replace_head', 'replace')
_HEAD_KEYS = ('head', 'model', 'type', 'head_id')
_RECT_KEYS = ('rect', 'placement', 'footprint', 'after')


def _revision_request(document, override):
    """Normalise a revision request from the CLI or the source document."""

    if override is not None:
        return override
    request = None
    for key in _REVISION_KEYS:
        if key in document:
            request = document[key]
            break
    if request is None:
        return None
    if not isinstance(request, dict):
        raise ValueError('revision must be an object')
    head = None
    for key in _HEAD_KEYS:
        if key in request:
            head = request[key]
            break
    if head is None and 'id' in request:
        head = request['id']
    if not isinstance(head, str) or not head:
        raise ValueError('revision must name a head to replace')
    rect = None
    for key in _RECT_KEYS:
        if key in request:
            rect = request[key]
            break
    if rect is None:
        raise ValueError(f'revision for {head} must include a rectangle')
    return head, rect


def run(document, replace_head=None):
    same, opposite = thresholds(document)
    request = _revision_request(document, replace_head)
    if request is not None:
        return revision(document, *request)
    width, height, dots, keepouts, _ = parse(document)
    found = findings(width, height, dots, keepouts, same, opposite)
    return {'registered_dots': [registered(dot) for dot in dots],
            'accepted': not found, 'findings': found}
