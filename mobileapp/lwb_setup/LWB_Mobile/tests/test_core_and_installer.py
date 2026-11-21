import ast
import hashlib
import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
core = load('mobile_core', ROOT / 'backend/telemetry/mobile_v1/core.py')
installer = load('mobile_installer', ROOT / 'backend/apply_backend.py')

class CoreTests(unittest.TestCase):
    def setUp(self): self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def test_never(self): self.assertEqual(core.node_status(None, self.now), 'never')
    def test_live_boundary(self): self.assertEqual(core.node_status(self.now - timedelta(seconds=15), self.now), 'live')
    def test_stale_boundary(self): self.assertEqual(core.node_status(self.now - timedelta(seconds=30), self.now), 'stale')
    def test_offline_boundary(self): self.assertEqual(core.node_status(self.now - timedelta(seconds=30.001), self.now), 'offline')
    def test_future_error(self): self.assertEqual(core.node_status(self.now + timedelta(seconds=11), self.now), 'clock_error')
    def test_small_skew(self): self.assertEqual(core.node_status(self.now + timedelta(seconds=5), self.now), 'live')
    def test_clamp(self): self.assertEqual(core.bounded_int('99999', 25, 100, 'page_size'), 100)
    def test_invalid_parameters(self):
        for value in ['x', '0', '-2']:
            with self.assertRaises(ValueError): core.bounded_int(value, 25, 100, 'page_size')
    def test_invalid_policy(self):
        with self.assertRaises(ValueError): core.policy(30, 15)
    def test_scale_and_zero(self):
        self.assertEqual(core.number(254, 10), 25.4); self.assertEqual(core.number(0), 0)
    def test_null_sentinel(self):
        self.assertIsNone(core.number(None)); self.assertIsNone(core.number(65535, sentinel=65535))
    def test_reading_units(self):
        row = SimpleNamespace(event_id=5, gateway=SimpleNamespace(gateway_id='a'),
            node=SimpleNamespace(node_id=500), seq=2, recv_ts_utc=self.now,
            hdc_temp_x10=254, hdc_hum_x10=972, light_raw=638, bmp_temp_x10=248, pressure_pa=100790)
        data = core.reading_data(row)
        self.assertEqual(data['temperature_c'], 25.4)
        self.assertEqual(data['pressure_pa'], 100790)
        self.assertEqual(data['node_id'], 500)

class InstallerTests(unittest.TestCase):
    def test_apply_and_rollback_does_not_touch_existing_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'lwb-backend'
            (project / 'telemetry').mkdir(parents=True); (project / 'config').mkdir()
            for file in ['manage.py', 'config/settings.py', 'telemetry/views.py', 'telemetry/urls.py']:
                (project / file).write_text('# Existing file\n')
            model = ('class Gateway:\n gateway_id = 1\n'
                     'class Node:\n gateway=1\n node_id=1\n last_seen=1\n'
                     'class SensorReading:\n node=1\n gateway=1\n event_id=1\n seq=1\n recv_ts_utc=1\n'
                     ' hdc_temp_x10=1\n hdc_hum_x10=1\n bmp_temp_x10=1\n light_raw=1\n pressure_pa=1\n')
            (project / 'telemetry/models.py').write_text(model)
            original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*.py')}
            installer.apply(project)
            self.assertTrue((project / 'telemetry/mobile_v1/views.py').exists())
            for p, h in original.items(): self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), h)
            backup = next(Path(tmp).glob('lwb-backend_mobile_backup_*'))
            installer.rollback(backup)
            self.assertFalse((project / 'telemetry/mobile_v1/views.py').exists())
            for p, h in original.items(): self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), h)
    def test_refuse_wrong_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit): installer.apply(Path(tmp))
    def test_python_syntax(self):
        for file in (ROOT / 'backend').rglob('*.py'): ast.parse(file.read_text(), filename=str(file))

if __name__ == '__main__': unittest.main(verbosity=2)
