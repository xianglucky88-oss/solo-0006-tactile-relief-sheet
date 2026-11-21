"""Paper-space clearance geometry for ordinary dots and head placements.

A placement is a half-open rectangle of integer cells.  Rectangles are never
expanded cell by cell: intersections, out-of-bounds cells, Chebyshev distances
and nearest cell pairs are all derived analytically, so a wide head costs the
same as a single dot.

Every finding keeps the original object identity (``dot`` / ``dots`` and the
keepout id).  Findings that involve a head also carry the occupied paper cells
and the matching source drawing cells, so each piece of evidence can be traced
back to the drawing it came from.
"""

from itertools import combinations


def label(dot):
    return [dot.face, dot.name]


def paper_rect(dot):
    """Registered paper footprint of a dot (half-open, integer cells)."""

    if dot.rect is None:
        return (dot.x, dot.y, dot.x + 1, dot.y + 1)
    rx0, ry0, rx1, ry1 = dot.rect
    if dot.face == 'back':
        # The head rides along with its marker's horizontal mirroring.  In
        # anchored offsets a drawing offset ``rx`` becomes ``-rx``, so the
        # interval ``[rx0, rx1)`` becomes ``[1 - rx1, 1 - rx0)``.  This is the
        # only reflection applied to a back dot: ``dot.x``/``dot.y`` are
        # already registered paper coordinates and are never mirrored again.
        return (dot.x + 1 - rx1, dot.y + ry0, dot.x + 1 - rx0, dot.y + ry1)
    return (dot.x + rx0, dot.y + ry0, dot.x + rx1, dot.y + ry1)


def source_cell(dot, cell):
    """Map one occupied paper cell back to its source drawing cell.

    The paper offset is undone once against the original drawing anchor.  For
    a back dot the paper offset is the negated drawing offset, so negating the
    paper offset recovers the drawing cell without reflecting the absolute
    paper coordinate a second time.
    """

    px, py = cell
    rel_x, rel_y = px - dot.x, py - dot.y
    if dot.face == 'back':
        rel_x = -rel_x
    return [dot.source_x + rel_x, dot.source_y + rel_y]


def source_rect(dot, paper):
    """Map an occupied paper rectangle back to its source drawing rectangle."""

    x0, y0, x1, y1 = paper
    if dot.face == 'back':
        return [dot.source_x + dot.x - x1 + 1, dot.source_y + y0 - dot.y,
                dot.source_x + dot.x - x0 + 1, dot.source_y + y1 - dot.y]
    return [dot.source_x + x0 - dot.x, dot.source_y + y0 - dot.y,
            dot.source_x + x1 - dot.x, dot.source_y + y1 - dot.y]


def intersection(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return (x0, y0, x1, y1) if x0 < x1 and y0 < y1 else None


def first_outside(rect, width, height):
    """Lexicographically first occupied cell outside the paper, if any.

    Cells compare as ``(x, y)``.  If the marker cell itself already starts
    outside, it is the answer.  Otherwise only the bottom and right edges can
    still leave the sheet, and a row overflowing the bottom sorts before a
    column overflowing the right edge.
    """

    x0, y0, x1, y1 = rect
    if not (0 <= x0 < width and 0 <= y0 < height):
        return (x0, y0)
    if y1 > height:
        return (x0, max(y0, height))
    if x1 > width:
        return (max(x0, width), y0)
    return None


def chebyshev(a, b):
    """Minimum Chebyshev distance between two half-open cell rectangles."""

    return max(0, b[0] - a[2] + 1, a[0] - b[2] + 1,
               b[1] - a[3] + 1, a[1] - b[3] + 1)


def nearest_cells(a, b):
    """Lexicographically smallest cell pair at the minimum distance.

    The first cell lies in *a* and the second in *b*, matching report order.
    """

    distance = chebyshev(a, b)
    ax = max(a[0], b[0] - distance)
    ay = max(a[1], b[1] - distance)
    bx = max(b[0], ax - distance)
    by = max(b[1], ay - distance)
    return (ax, ay), (bx, by)


def dot_findings(width, height, dot, keepouts):
    """Boundary and keepout evidence for one dot's registered placement."""

    findings = []
    rect = paper_rect(dot)
    outside = first_outside(rect, width, height)
    if outside is not None:
        finding = {'rule': 'outside', 'dot': label(dot)}
        if dot.rect is not None:
            finding.update(head=dot.head, paper=list(outside),
                           drawing=source_cell(dot, outside))
        findings.append(finding)
    for name, x0, y0, x1, y1 in keepouts:
        overlap = intersection(rect, (x0, y0, x1, y1))
        if overlap is not None:
            finding = {'rule': 'keepout', 'dot': label(dot), 'keepout': name}
            if dot.rect is not None:
                finding.update(head=dot.head, paper=list(overlap),
                               drawing=source_rect(dot, overlap))
            findings.append(finding)
    return findings


def pair_finding(a, b, same, opposite):
    """Paired-clearance evidence for two dots, or ``None`` when clear."""

    same_face = a.face == b.face
    limit = same if same_face else opposite
    distance = chebyshev(paper_rect(a), paper_rect(b))
    if distance >= limit:
        return None
    finding = {'rule': 'same-face' if same_face else 'opposite-face',
               'dots': [label(a), label(b)], 'distance': distance,
               'required': limit}
    if a.rect is not None or b.rect is not None:
        first, second = nearest_cells(paper_rect(a), paper_rect(b))
        finding.update(heads=[a.head, b.head],
                       paper=[list(first), list(second)],
                       drawing=[source_cell(a, first), source_cell(b, second)])
    return finding


def evidence_key(finding):
    """Stable identity of one piece of evidence, independent of its content."""

    if 'keepout' in finding:
        return ('keepout', tuple(finding['dot']), finding['keepout'])
    if 'dots' in finding:
        return (finding['rule'], tuple(finding['dots'][0]),
                tuple(finding['dots'][1]))
    return (finding['rule'], tuple(finding['dot']))


def evidence_order(finding):
    """Deterministic, human-readable ordering for evidence."""

    key = evidence_key(finding)
    return (key[0],) + tuple(' '.join(part) if isinstance(part, tuple) else part
                            for part in key[1:])


def findings(width, height, dots, keepouts, same, opposite):
    """Full ordered finding list for a parsed sheet."""

    out = []
    for dot in dots:
        out.extend(dot_findings(width, height, dot, keepouts))
    for a, b in combinations(dots, 2):
        finding = pair_finding(a, b, same, opposite)
        if finding is not None:
            out.append(finding)
    return out
