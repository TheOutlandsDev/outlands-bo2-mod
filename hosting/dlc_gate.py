"""Fail-closed DLC rotation gate backed by isolated native test receipts.

The private acceptance file contains only package paths/hashes and map/mode IDs.
It never contains game assets, player records, logs or account information.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

try:
    from tools.content_inventory import MAPS
except ImportError:  # Flat /opt/t6 layout in the private game image.
    from content_inventory import MAPS

DLC_MAPS = frozenset(name for name, (_, pack) in MAPS.items()
                     if pack not in ('base', 'nuketown_bonus'))
HASH = re.compile(r'[0-9a-f]{64}\Z')
ASSET = re.compile(r'(?:zone/(?:all|[a-z]{2,12})/[a-z0-9_]+\.(?:ff|ipak)'
                   r'|sound/[a-z0-9_]+\.[a-z]{2,12}\.(?:sabs|sabl))\Z')
MAX_JSON = 256 * 1024


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError('Invalid DLC gate input')
    return json.loads(path.read_text(encoding='utf-8'))


def digest_asset(game, relative):
    if not isinstance(relative, str) or not ASSET.fullmatch(relative):
        raise ValueError('Invalid DLC package path')
    path = Path(game)
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError('Linked DLC package refused')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
        raise ValueError('Missing or empty DLC package')
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def accepted_maps(path, game, modes):
    """Return DLC IDs accepted for *every* enabled mode; invalid state denies all."""
    try:
        data = read_json(path)
        if set(data) != {'schema_version', 'maps'} or data['schema_version'] != 1 or not isinstance(data['maps'], dict):
            return set()
        accepted = set()
        for name, row in data['maps'].items():
            if name not in DLC_MAPS or not isinstance(row, dict) or set(row) != {'modes', 'files'}:
                continue
            files = row['files']
            if (not isinstance(row['modes'], list) or len(row['modes']) != len(set(row['modes']))
                    or not set(modes).issubset(row['modes']) or not isinstance(files, dict)
                    or not 2 <= len(files) <= 32 or f'zone/all/{name}.ff' not in files
                    or not any(p.endswith(('.ipak', '.sabs', '.sabl')) for p in files)):
                continue
            if all(isinstance(want, str) and HASH.fullmatch(want)
                   and digest_asset(game, relative) == want for relative, want in files.items()):
                accepted.add(name)
        return accepted
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return set()


def native_pass(report, map_name, mode):
    """Accept only completed, isolated, all-bot observations for this map/mode."""
    plan = report.get('plan', {})
    if (plan.get('network_mode') != 'none' or plan.get('published_ports') is not False
            or plan.get('human_clients') is not False or plan.get('live_state') is not False):
        return False
    wanted_case = {'map_name': map_name, 'mode': mode}
    if wanted_case not in plan.get('cases', []):
        return False
    for result in report.get('results', []):
        case = result.get('case', {})
        if case != wanted_case or result.get('passed') is not True:
            continue
        if result.get('native_crash') or result.get('script_error'):
            continue
        samples = result.get('samples', [])
        matching = [s for s in samples if s.get('stage') == 0
                    and s.get('map') == map_name and s.get('mode') == mode]
        completed = [s for s in matching if s.get('kind') == 'complete']
        if (completed and completed[-1].get('bots') == 16
                and max((s.get('moved', 0) for s in matching), default=0) >= 8
                and completed[-1].get('kills', 0) > 0 and completed[-1].get('score', 0) > 0):
            return True
    return False


def build_acceptance(game, candidate, reports, modes):
    if not isinstance(candidate, dict) or not candidate or set(candidate) - DLC_MAPS:
        raise ValueError('Candidate must contain catalogued DLC maps')
    if not modes:
        raise ValueError('At least one active mode is required')
    evidence = [read_json(path) for path in reports]
    output = {}
    for name, files in candidate.items():
        if (not isinstance(files, list) or len(files) != len(set(files))
                or not 2 <= len(files) <= 32 or f'zone/all/{name}.ff' not in files
                or not any(isinstance(p, str) and p.endswith(('.ipak', '.sabs', '.sabl')) for p in files)):
            raise ValueError('Candidate package list is incomplete')
        if any(not any(native_pass(report, name, mode) for report in evidence) for mode in modes):
            raise ValueError('Missing passing isolated native map/mode receipt')
        output[name] = {'modes': sorted(modes),
                        'files': {relative: digest_asset(game, relative) for relative in sorted(files)}}
    return {'schema_version': 1, 'maps': output}


def save_private(path, data):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('Refusing to overwrite DLC acceptance')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.dlc-acceptance-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True,
                        help='Private JSON mapping DLC map IDs to required compiled package paths')
    parser.add_argument('--report', type=Path, action='append', required=True,
                        help='Isolated backend_verify report.json; repeat for all map/mode cases')
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from hosting.rotation import load_catalog
        catalog = load_catalog(args.catalog)
        modes = {name for name, weight in catalog['modes'].items() if weight}
        data = build_acceptance(args.game_dir, read_json(args.candidate), args.report, modes)
        save_private(args.output, data)
        print('DLC acceptance written: ' + str(len(data['maps'])) + ' map(s), ' + str(len(modes)) + ' mode(s)')
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        print('DLC acceptance refused; check candidate packages and native receipts')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
