import copy
import importlib.util
import json
from pathlib import Path
import unittest
from jsonschema import ValidationError
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('contract_validator', ROOT / 'scripts/delivery/validate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CONFIG = json.loads((ROOT / '.github/delivery.json').read_text())
def example(kind):
    return json.loads((ROOT / 'docs/contracts/examples' / (kind + '.json')).read_text())
class ContractTests(unittest.TestCase):
    def assert_invalid(self, kind, record, config=None):
        with self.assertRaises((ValidationError, ValueError)):
            module.validate(kind, record, config or CONFIG)
    def test_examples(self):
        for kind in module.KINDS:
            with self.subTest(kind=kind): module.validate(kind, example(kind), CONFIG)
    def test_missing_approval_reference(self):
        x = example('task'); del x['approval']['reference']; self.assert_invalid('task', x)
    def test_unknown_secret_field_rejected(self):
        x = example('task'); x['token'] = 'dummy'; self.assert_invalid('task', x)
    def test_protected_branches_rejected(self):
        for branch in ['main', 'prod', 'release/test']:
            x = example('task'); x['branch'] = branch; self.assert_invalid('task', x)
    def test_wrong_repository(self):
        x = example('task'); x['repository'] = 'other/repository'; self.assert_invalid('task', x)
    def test_unbounded_execution_rejected(self):
        for key, value in [('max_minutes',121),('max_fix_rounds',3),('max_cost_usd',0)]:
            x = example('task'); x['limits'][key] = value; self.assert_invalid('task', x)
    def test_failed_gate_cannot_be_ready(self):
        x = example('worker-result'); x['gates']['status']='failed'; self.assert_invalid('worker-result', x)
    def test_missing_evidence_cannot_be_ready(self):
        x = example('worker-result'); x['gates']['evidence']=[]; self.assert_invalid('worker-result', x)
    def test_timeout_can_checkpoint_without_head(self):
        x = example('worker-result'); x.update(status='timeout',head_sha=None);x['gates']={'status':'not_run','evidence':[]};module.validate('worker-result',x,CONFIG)
    def test_release_requires_exact_dev_sha(self):
        x = example('release'); x['dev_verified_sha']='d'*40; self.assert_invalid('release', x)
    def test_production_requires_release(self):
        x = example('deployment'); x['release_id']=None; self.assert_invalid('deployment', x)
    def test_runtime_mismatch_cannot_succeed(self):
        x = example('deployment'); x['runtime_sha']='d'*40; self.assert_invalid('deployment', x)
    def test_failed_health_cannot_succeed(self):
        x = example('deployment'); x['health']='failed'; self.assert_invalid('deployment', x)
    def test_nt_production_owner(self):
        x = example('deployment'); x['owner']='devops'; self.assert_invalid('deployment', x)
    def test_personal_production_cannot_target_vps(self):
        c = copy.deepcopy(CONFIG);c['group']='personal';self.assert_invalid('deployment',example('deployment'),c)
    def test_personal_mac_production(self):
        c = copy.deepcopy(CONFIG);c['group']='personal';c['environments']={'production-macmini':{'owner':'devops'}}
        x = example('deployment');x.update(environment='production-macmini',owner='devops');module.validate('deployment',x,c)
    def test_dev_receipt_does_not_require_release(self):
        x = example('deployment');x.update(environment='dev-macmini',owner='devops',release_id=None);module.validate('deployment',x,CONFIG)
    def test_rollback_requires_observed_version(self):
        x = example('deployment');x.update(status='rolled_back',runtime_sha=None);self.assert_invalid('deployment',x)
if __name__ == '__main__': unittest.main()
