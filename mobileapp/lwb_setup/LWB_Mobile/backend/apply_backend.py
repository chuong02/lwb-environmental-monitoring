#!/usr/bin/env python3
"""Add Mobile V1 files without changing existing models, routes, settings or DB."""
import argparse
import ast
import json
import shutil
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def apply(project: Path, dry_run=False):
    project = project.expanduser().resolve()
    for rel in ['manage.py', 'telemetry/models.py', 'config/settings.py']:
        if not (project / rel).is_file():
            raise SystemExit(f'Missing {project / rel}; use the lwb-backend project root.')
    tree = ast.parse((project / 'telemetry/models.py').read_text(encoding='utf-8-sig'))
    required = {'Gateway': {'gateway_id'}, 'Node': {'gateway', 'node_id', 'last_seen'},
                'SensorReading': {'node', 'gateway', 'event_id', 'seq', 'recv_ts_utc',
                                  'hdc_temp_x10', 'hdc_hum_x10', 'bmp_temp_x10', 'light_raw', 'pressure_pa'}}
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    for name, fields in required.items():
        if name not in classes:
            raise SystemExit(f'Missing model {name}. No files changed.')
        attrs = {t.id for n in classes[name].body
                 if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        if fields - attrs:
            raise SystemExit(f'Unexpected model {name}: missing {sorted(fields - attrs)}. No files changed.')
    files = sorted(p for folder in ['config', 'telemetry'] for p in (HERE / folder).rglob('*.py'))
    for src in files:
        ast.parse(src.read_text(encoding='utf-8'))
        target = project / src.relative_to(HERE)
        if target.is_symlink():
            raise SystemExit(f'Refusing symlink: {target}')
    if dry_run:
        for src in files: print(f'Would copy: {src.relative_to(HERE)}')
        return
    backup = project.parent / (project.name + '_mobile_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir()
    manifest = []
    for src in files:
        rel = src.relative_to(HERE)
        dst = project / rel
        existed = dst.exists()
        if existed:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, saved)
        manifest.append({'path': rel.as_posix(), 'existed': existed})
    (backup / 'manifest.json').write_text(json.dumps({'project': str(project), 'files': manifest}, indent=2))
    try:
        for src in files:
            dst = project / src.relative_to(HERE)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except Exception:
        rollback(backup)
        raise
    print(f'Installed {len(files)} files. No migration or database write was performed.')
    print(f'Backup: {backup}')
    print('Existing Web APIs, settings.py, models.py and MQTT Consumer were not modified.')
    print('Next: python manage.py runserver 127.0.0.1:8001 --settings=config.lwb_mobile_local')


def rollback(backup):
    backup = Path(backup).expanduser().resolve()
    info = json.loads((backup / 'manifest.json').read_text())
    project = Path(info['project']).resolve()
    for row in info['files']:
        rel = Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise SystemExit('Unsafe backup manifest.')
        dst = project / rel
        if row['existed']:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / rel, dst)
        elif dst.exists():
            dst.unlink()
    print('Mobile V1 files rolled back; database unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if args.rollback:
        rollback(args.rollback)
    elif args.project:
        apply(args.project, args.dry_run)
    else:
        parser.error('--project or --rollback is required')
