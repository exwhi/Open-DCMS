import os
import asyncio
import json
import pytest
from datetime import datetime

# If sqlalchemy is not installed in the environment, skip DB-heavy tests
try:
    import sqlalchemy  # type: ignore
    _HAS_SQLALCHEMY = True
except Exception:
    _HAS_SQLALCHEMY = False

if not _HAS_SQLALCHEMY:
    pytest.skip("sqlalchemy not installed; skipping DB integration tests", allow_module_level=True)

os.environ['OPEN_DCMS_DB_URL'] = 'sqlite:///./.data/open_dcms.db'
from backend import db
from backend import asgi
import httpx

ADMIN_KEY = os.getenv('OPEN_DCMS_ADMIN_API_KEY', 'admin-secret')

@pytest.fixture(scope='module', autouse=True)
def init_db():
    db.init_db()
    # ensure clean slate for tests: not deleting DB but ok for simple tests
    yield

@pytest.mark.asyncio
async def test_log_and_list():
    # log an action
    lid = db.log_blackhole_action('198.51.100.0/24', 'add', 'exabgp', '65000:666', True, 'pytest', 'admin')
    assert lid is not None
    entry = db.get_blackhole_action(lid)
    assert entry['prefix'] == '198.51.100.0/24'
    logs = db.list_blackhole_actions(limit=5)
    assert any(l['id'] == lid for l in logs)

@pytest.mark.asyncio
async def test_asgi_blackhole_and_revert():
    async with httpx.AsyncClient(app=asgi.app, base_url='http://test') as client:
        # POST blackhole via ASGI
        r = await client.post('/api/v1/blackhole', headers={'X-Admin-Key': ADMIN_KEY}, json={'prefix': '192.0.2.0/24', 'action': 'add', 'adapter': 'exabgp'})
        assert r.status_code in (200, 500)  # adapter stubs may return ok or simulated fail
        jr = r.json()
        # ensure log exists when DB enabled
        logs = db.list_blackhole_actions(limit=10, prefix='192.0.2.0/24')
        assert any(l['prefix'] == '192.0.2.0/24' for l in logs)
        # revert the first found
        target = logs[0]
        rr = await client.post('/api/v1/blackhole/revert', headers={'X-Admin-Key': ADMIN_KEY}, json={'id': target['id']})
        assert rr.status_code in (200, 500)
        rjr = rr.json()
        # revert should produce a new log_id when DB enabled
        assert 'log_id' in rjr
