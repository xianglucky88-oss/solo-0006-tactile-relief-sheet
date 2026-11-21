import argparse
import json
from pathlib import Path
import sys

from .pipeline import run


def _replacement(value):
    """Parse ``ID:x0,y0,x1,y1`` for ``--replace-head``."""

    name, sep, rect = value.partition(':')
    if not sep or not name:
        raise argparse.ArgumentTypeError('expected ID:x0,y0,x1,y1')
    try:
        parts = [int(part) for part in rect.split(',')]
    except ValueError:
        raise argparse.ArgumentTypeError('rectangle must be four integers')
    if len(parts) != 4:
        raise argparse.ArgumentTypeError('rectangle must be four integers')
    return name, parts


def main():
    parser = argparse.ArgumentParser(description='registered geometry, keepouts, and paired-clearance evidence')
    parser.add_argument('input', type=Path, help='source JSON document')
    parser.add_argument('--replace-head', type=_replacement, metavar='ID:X0,Y0,X1,Y1',
                        help='swap one head definition and emit affected evidence only')
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding='utf-8'))
        report = run(payload, args.replace_head)
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(f'input rejected: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
