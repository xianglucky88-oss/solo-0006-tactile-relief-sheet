from .clearance import clashes, label
from .plates import parse


def run(document):
    same, opposite = document['min_same'], document['min_opposite']
    if any(type(v) is not int or not 1 <= v <= 2048 for v in (same, opposite)):
        raise ValueError('minimum clearances must be positive grid distances')
    width, height, dots, keepouts = parse(document)
    findings = clashes(width, height, dots, keepouts, same, opposite)
    return {'registered_dots': [{'dot': label(dot), 'at': [dot.x, dot.y]} for dot in dots],
            'accepted': not findings, 'findings': findings}
