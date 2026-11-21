import argparse
import json
from pathlib import Path
import sys

from .merge import merge_documents
from .pipeline import run


def _load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='registered geometry, keepouts, and paired-clearance evidence')
    parser.add_argument('input', nargs='?', type=Path,
                        help='source JSON document')
    parser.add_argument('--merge', nargs=3, metavar=('BASELINE', 'LEFT', 'RIGHT'),
                        type=Path, help='three-way merge of two revisions')
    args = parser.parse_args(argv)
    if args.merge is None and args.input is None:
        parser.error('a source document or --merge BASELINE LEFT RIGHT is required')

    try:
        if args.merge is not None:
            baseline, left, right = args.merge
            sources = {'baseline': str(baseline), 'left': str(left),
                       'right': str(right)}
            output = merge_documents(_load(baseline), _load(left), _load(right),
                                     sources)
        else:
            output = run(_load(args.input))
        # A business finding (or an unmergeable revision pair) is still a
        # complete analysis, so it keeps exit code 0; only bad input exits 2.
        code = 0
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(f'input rejected: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
