from itertools import combinations


def label(dot):
    return [dot.face, dot.name]


def clashes(width, height, dots, keepouts, same, opposite):
    findings = []
    for dot in dots:
        if not (0 <= dot.x < width and 0 <= dot.y < height):
            findings.append({'rule': 'outside', 'dot': label(dot)})
        for name, x0, y0, x1, y1 in keepouts:
            if x0 <= dot.x < x1 and y0 <= dot.y < y1:
                findings.append({'rule': 'keepout', 'dot': label(dot), 'keepout': name})
    for a, b in combinations(dots, 2):
        same_face = a.face == b.face
        limit = same if same_face else opposite
        distance = max(abs(a.x-b.x), abs(a.y-b.y))
        if distance < limit:
            findings.append({'rule': 'same-face' if same_face else 'opposite-face',
                             'dots': [label(a), label(b)], 'distance': distance, 'required': limit})
    return findings
