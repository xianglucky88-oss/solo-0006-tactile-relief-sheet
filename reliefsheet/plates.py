"""Source-document parsing and paper registration.

A dot's ``at`` stays in the original drawing coordinates.  Dots that select a
head model also carry a half-open placement rectangle *relative to their
marker*, where the marker cell is the origin cell: a placement must contain
``(0, 0)`` and may extend asymmetrically in any direction.

Registration reuses the existing front/back rules.  The back plate is
horizontally mirrored about the sheet and shifted by the back offset; a back
dot's placement rides along with its marker, which in anchored offsets means a
drawing offset ``rx`` becomes ``-rx``.
"""

from dataclasses import dataclass


MAX_EXTENT = 2048
HEAD_KEYS = ('head', 'model', 'type', 'stamp', 'head_id')
RECT_KEYS = ('rect', 'placement', 'footprint', 'offset', 'box', 'span')
HEAD_SECTIONS = ('heads', 'models', 'types', 'stamps')


@dataclass(frozen=True)
class Dot:
    """A marker in its drawing cell plus its registered paper cell.

    ``x``/``y`` are the registered paper coordinates, preserving the original
    field order.  ``draw_x``/``draw_y`` are the untouched drawing coordinates
    (defaulting to the paper cell when not supplied).  ``rect`` is the head
    placement relative to the marker, or ``None`` for an ordinary dot.
    """

    name: str
    face: str
    x: int
    y: int
    draw_x: int = None
    draw_y: int = None
    head: str = None
    rect: tuple = None

    @property
    def source_x(self):
        return self.x if self.draw_x is None else self.draw_x

    @property
    def source_y(self):
        return self.y if self.draw_y is None else self.draw_y


def _first(mapping, keys, what):
    for key in keys:
        if key in mapping:
            return mapping[key]
    raise KeyError(what)


def placement(value, where):
    """Validate one relative half-open placement rectangle.

    The rectangle must be integral, non-empty and must contain the marker cell
    so that ``id``/``at`` remain the identity anchor of the head.
    """

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f'{where} must be four integers')
    x0, y0, x1, y1 = value
    if any(type(v) is not int for v in (x0, y0, x1, y1)):
        raise ValueError(f'{where} must be four integers')
    if any(abs(v) > MAX_EXTENT for v in (x0, y0, x1, y1)):
        raise ValueError(f'{where} is too large')
    if not (x0 < x1 and y0 < y1 and x0 <= 0 < x1 and y0 <= 0 < y1):
        raise ValueError(f'{where} must be a positive half-open rectangle '
                         'containing the marker cell')
    return (x0, y0, x1, y1)


def head_definitions(document):
    """All declared head models, keyed by id, in declaration order."""

    raw = {}
    for section in HEAD_SECTIONS:
        if section in document:
            raw = document[section]
            break
    heads = {}
    if isinstance(raw, dict):
        rows = []
        for name, value in raw.items():
            if isinstance(value, dict):
                value = _first(value, RECT_KEYS, f'head {name}')
            rows.append({'id': name, 'rect': value})
    elif isinstance(raw, list):
        rows = raw
    else:
        raise ValueError('heads must be a list or mapping of model definitions')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('head definitions must be objects')
        name = row['id']
        if not isinstance(name, str) or not name or name in heads:
            raise ValueError('head IDs must be unique nonempty strings')
        heads[name] = placement(_first(row, RECT_KEYS, f'head {name}'),
                                f'head {name}')
    return heads


def _head_selection(row, face, name):
    """The head id selected by a dot row, or ``None``.

    ``head`` may also be an inline ``{"id": ..., "rect": ...}`` object; such an
    object defines (or re-affirms) the model and yields ``(id, rect)``.
    """

    for key in HEAD_KEYS:
        if key in row:
            head = row[key]
            if head is None:
                return None
            if isinstance(head, dict):
                inline = head['id']
                if not isinstance(inline, str) or not inline:
                    raise ValueError(f'invalid head id on {face}/{name}')
                return inline, _first(head, RECT_KEYS, f'head {inline}')
            if not isinstance(head, str) or not head:
                raise ValueError(f'invalid head id on {face}/{name}')
            return head
    return None


def parse(document, replace_head=None):
    """Validate a source document and register every dot onto paper.

    ``replace_head`` is an optional ``(id, rect)`` pair used by revision mode;
    it swaps exactly one head definition without touching the drawing.
    Returns ``(width, height, dots, keepouts, heads)`` with dots and keepouts
    in canonical order.
    """

    width, height = document['grid']
    if any(type(v) is not int or not 1 <= v <= MAX_EXTENT for v in (width, height)):
        raise ValueError('grid must have two positive dimensions up to 2048')
    dx, dy = document['back_offset']
    if any(type(v) is not int or abs(v) > MAX_EXTENT for v in (dx, dy)):
        raise ValueError('invalid back offset')

    heads = head_definitions(document)
    # Inline definitions may introduce a model before it is selected, so they
    # are registered first; an explicit ``heads`` entry stays authoritative.
    for face in ('front', 'back'):
        rows = document[face]
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get('id', '')
            selection = _head_selection(row, face, name)
            if isinstance(selection, tuple):
                head, inline_rect = selection
                heads.setdefault(head, placement(inline_rect, f'head {head}'))
    if replace_head is not None:
        if not isinstance(replace_head, (list, tuple)) or len(replace_head) != 2:
            raise ValueError('a head replacement is an id and a rectangle')
        name, rect = replace_head
        if not isinstance(name, str) or not name or name not in heads:
            raise ValueError(f'unknown head to replace: {name}')
        heads[name] = placement(rect, f'head {name}')

    dots = []
    seen = set()
    for face in ('front', 'back'):
        rows = document[face]
        if not isinstance(rows, list):
            raise ValueError(f'{face} must be a list of dots')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f'dots on {face} must be objects')
            name = row['id']
            x, y = row['at']
            if not isinstance(name, str) or not name or (face, name) in seen:
                raise ValueError(f'duplicate or empty dot id on {face}')
            if type(x) is not int or type(y) is not int or not (0 <= x < width and 0 <= y < height):
                raise ValueError(f'dot outside its drawing: {face}/{name}')
            head = _head_selection(row, face, name)
            if isinstance(head, tuple):
                # Inline definition; it was already registered above.
                head = head[0]
            if head is not None and head not in heads:
                raise ValueError(f'unknown head on {face}/{name}: {head}')
            seen.add((face, name))
            dots.append(Dot(name, face,
                            width - 1 - x + dx if face == 'back' else x,
                            y + dy if face == 'back' else y,
                            x, y, head,
                            heads[head] if head is not None else None))
    if len(dots) > 1000:
        raise ValueError('at most 1000 dots per sheet')

    keepouts = []
    keepout_names = set()
    rows = document['keepouts']
    if not isinstance(rows, list):
        raise ValueError('keepouts must be a list')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('keepouts must be objects')
        name = row['id']
        x0, y0, x1, y1 = row['rect']
        if not isinstance(name, str) or not name or name in keepout_names:
            raise ValueError('keepout IDs must be unique nonempty strings')
        if (any(type(v) is not int for v in (x0, y0, x1, y1))
            or not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height)):
            raise ValueError(f'invalid half-open keepout: {name}')
        keepout_names.add(name)
        keepouts.append((name, x0, y0, x1, y1))
    return (width, height,
            sorted(dots, key=lambda d: (d.face, d.name)),
            sorted(keepouts), heads)
