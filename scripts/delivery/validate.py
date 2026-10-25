"""Validate shape and environment invariants, NOT authorization or deployment truth.
Run with a trusted schema/config checkout, not schema files modified by a worker.
"""
import argparse
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
ROOT = Path(__file__).resolve().parents[2]
KINDS = ('task', 'worker-result', 'release', 'deployment')

def validate(kind, record, config):
    schema = json.loads((ROOT / 'docs/contracts' / (kind + '.schema.json')).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    if record['repository'] != config['repository']:
        raise ValueError('Record repository differs from trusted config')
    if kind == 'worker-result' and record['status'] == 'review_ready':
        if record['gates']['status'] != 'passed' or not record['gates']['evidence'] or not record['head_sha']:
            raise ValueError('review_ready requires passing gate evidence and head SHA')
    environment = record.get('environment', record.get('target_environment'))
    if environment:
        expected_prod = 'production-vps' if config['group'] == 'NT' else 'production-macmini'
        if environment not in ('dev-macmini', expected_prod) or environment not in config['environments']:
            raise ValueError('Environment is not permitted for this product')
    if kind == 'release' and record['source_sha'] != record['dev_verified_sha']:
        raise ValueError('Release source must match Dev verified SHA; revalidate changed candidates')
    if kind == 'deployment':
        owner = 'op-pro' if environment == 'production-vps' else 'devops'
        if record['owner'] != owner or config['environments'][environment]['owner'] != owner:
            raise ValueError('Deployment owner does not match environment')
        if environment.startswith('production-') and not record['release_id']:
            raise ValueError('Production receipt requires release_id')
        if record['status'] == 'succeeded' and (record['health'] != 'passed' or record['runtime_sha'] != record['source_sha']):
            raise ValueError('Successful deployment requires healthy matching runtime SHA')
        if record['status'] == 'rolled_back' and not record['runtime_sha']:
            raise ValueError('Rollback receipt must identify observed restored SHA')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=KINDS)
    parser.add_argument('record', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / '.github/delivery.json')
    args = parser.parse_args()
    validate(args.kind, json.loads(args.record.read_text()), json.loads(args.config.read_text()))
    print('Contract valid; trusted authorization and evidence verification remain controller responsibilities.')
if __name__ == '__main__':
    main()
