from dataclasses import dataclass


@dataclass(frozen=True)
class Dot:
    name: str
    face: str
    x: int
    y: int


def parse(document):
    width, height = document['grid']
    if any(type(v) is not int or not 1 <= v <= 2048 for v in (width, height)):
        raise ValueError('grid must have two positive dimensions up to 2048')
    dx, dy = document['back_offset']
    if any(type(v) is not int or abs(v) > 2048 for v in (dx, dy)):
        raise ValueError('invalid back offset')
    dots = []
    names = set()
    for face in ('front', 'back'):
        for row in document[face]:
            name = row['id']
            x, y = row['at']
            if not isinstance(name, str) or not name or (face, name) in names:
                raise ValueError(f'duplicate or empty dot id on {face}')
            if type(x) is not int or type(y) is not int or not (0 <= x < width and 0 <= y < height):
                raise ValueError(f'dot outside its drawing: {face}/{name}')
            names.add((face, name))
            dots.append(Dot(name, face, width - 1 - x + dx if face == 'back' else x,
                            y + dy if face == 'back' else y))
    if len(dots) > 1000:
        raise ValueError('at most 1000 dots per sheet')
    keepouts = []
    keepout_names = set()
    for row in document['keepouts']:
        name = row['id']
        x0, y0, x1, y1 = row['rect']
        if not isinstance(name, str) or not name or name in keepout_names:
            raise ValueError('keepout IDs must be unique nonempty strings')
        if (any(type(v) is not int for v in (x0, y0, x1, y1))
            or not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height)):
            raise ValueError(f'invalid half-open keepout: {name}')
        keepout_names.add(name)
        keepouts.append((name, x0, y0, x1, y1))
    return width, height, sorted(dots, key=lambda d: (d.face, d.name)), sorted(keepouts)
