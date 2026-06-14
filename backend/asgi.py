import os
import json
from datetime import datetime

API_KEY = os.getenv("OPEN_DCMS_API_KEY", "dev-secret")
ADMIN_API_KEY = os.getenv("OPEN_DCMS_ADMIN_API_KEY", "admin-secret")
DATA_DIR = os.getenv("OPEN_DCMS_DATA_DIR", ".data")
os.makedirs(DATA_DIR, exist_ok=True)
try:
    from backend.auth import validate_key, create_key, list_keys
except Exception:
    # relative import fallback
    from auth import validate_key, create_key, list_keys

# try to import DB helpers (optional)
try:
    from backend import db as db_mod
except Exception:
    try:
        import db as db_mod
    except Exception:
        db_mod = None

async def app(scope, receive, send):
    if scope["type"] != "http":
        await send({"type": "http.response.start", "status": 400})
        await send({"type": "http.response.body", "body": b""})
        return

    path = scope.get("path", "")
    method = scope.get("method", "GET")
    headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}

    if method == "GET" and path == "/health":
        body = json.dumps({"status": "ok"}).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})
        return

    # Admin endpoints for API key management
    if path.startswith("/api/v1/admin/"):
        # admin auth
        adm_key = headers.get("x-admin-key")
        if adm_key != ADMIN_API_KEY:
            body = json.dumps({"detail": "invalid admin key"}).encode()
            await send({"type": "http.response.start", "status": 401, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
            return

        if method == "POST" and path == "/api/v1/admin/key":
            # create key for tenant; read body
            more_body = True
            body_bytes = b""
            while more_body:
                event = await receive()
                if event["type"] == "http.request":
                    body_bytes += event.get("body", b"")
                    more_body = event.get("more_body", False)
            try:
                obj = json.loads(body_bytes.decode())
            except Exception:
                await send({"type": "http.response.start", "status": 400})
                await send({"type": "http.response.body", "body": b""})
                return
            tenant = obj.get("tenant") or "default"
            newkey = create_key(tenant)
            body = json.dumps({"tenant": tenant, "key": newkey}).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
            return

        if method == "GET" and path == "/api/v1/admin/keys":
            qs = scope.get("query_string", b"").decode()
            from urllib.parse import parse_qs
            params = parse_qs(qs)
            tenant = params.get("tenant", [None])[0]
            data = list_keys(tenant)
            body = json.dumps(data, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
            return

    # Read-only endpoint: return the last stored record for a tenant
    if method == "GET" and path == "/api/v1/latest":
        # parse query string to get tenant
        from urllib.parse import parse_qs
        qs = scope.get("query_string", b"").decode()
        params = parse_qs(qs)
        tenant = params.get("tenant", ["default"])[0]
        # try DB first
        if db_mod:
            try:
                res = db_mod.get_latest_for_tenant(tenant)
                if res:
                    body = json.dumps(res, ensure_ascii=False).encode()
                    await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json; charset=utf-8"]]})
                    await send({"type": "http.response.body", "body": body})
                    return
            except Exception:
                # fall through to file-based fallback
                pass

        # file-based fallback (legacy)
        fname = os.path.join(DATA_DIR, f"{tenant}.jsonl")
        if not os.path.exists(fname):
            body = json.dumps({"detail": "no data for tenant"}).encode()
            await send({"type": "http.response.start", "status": 404, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
            return
        last = None
        try:
            with open(fname, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
        except Exception:
            last = None
        if not last:
            body = json.dumps({"detail": "no records"}).encode()
            await send({"type": "http.response.start", "status": 404, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
            return
        try:
            obj = json.loads(last)
        except Exception:
            obj = {"raw": last}
        body = json.dumps(obj, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json; charset=utf-8"]]})
        await send({"type": "http.response.body", "body": body})
        return

    # Query endpoint: paginated/time-range telemetry
    if method == "GET" and path == "/api/v1/query":
        from urllib.parse import parse_qs
        qs = scope.get("query_string", b"").decode()
        params = parse_qs(qs)
        tenant = params.get("tenant", [None])[0]
        try:
            limit = int(params.get("limit", ["100"])[0])
        except Exception:
            limit = 100
        try:
            offset = int(params.get("offset", ["0"])[0])
        except Exception:
            offset = 0
        since = params.get("since", [None])[0]
        until = params.get("until", [None])[0]
        source = params.get("source", [None])[0]
        payload_key = params.get("payload_key", [None])[0]
        cursor = params.get("cursor", [None])[0]

        if db_mod:
            try:
                res = db_mod.query_telemetry(tenant=tenant, limit=limit, offset=offset, since=since, until=until, source=source, payload_key=payload_key, cursor=cursor)
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json; charset=utf-8"]]})
                await send({"type": "http.response.body", "body": body})
                return
            except Exception as e:
                body = json.dumps({"detail": "query failed", "error": str(e)}).encode()
                await send({"type": "http.response.start", "status": 500, "headers": [[b"content-type", b"application/json; charset=utf-8"]]})
                await send({"type": "http.response.body", "body": body})
                return

        # if no DB, return 404
        body = json.dumps({"detail": "DB not enabled"}).encode()
        await send({"type": "http.response.start", "status": 404, "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})
        return

    # POST /api/v1/blackhole -> trigger blackhole via adapter (admin-only)
    if method == 'POST' and path == '/api/v1/blackhole':
        more_body = True
        body_bytes = b''
        while more_body:
            event = await receive()
            if event['type'] == 'http.request':
                body_bytes += event.get('body', b'')
                more_body = event.get('more_body', False)
        try:
            obj = json.loads(body_bytes.decode()) if body_bytes else {}
        except Exception:
            obj = {}
        prefix = obj.get('prefix')
        action = obj.get('action', 'add')  # 'add' or 'remove'
        adapter = obj.get('adapter', 'exabgp')
        community = obj.get('community')
        if not prefix:
            body = json.dumps({'detail': 'prefix required'}).encode()
            await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]} )
            await send({'type': 'http.response.body', 'body': body})
            return
        # lazy import of adapters
        try:
            from backend import router_adapters as rad
        except Exception:
            try:
                import router_adapters as rad
            except Exception:
                rad = None
        result = False
        detail = None
        try:
            if not rad:
                raise RuntimeError('router adapters not available')
            # map adapter name to class
            amap = {
                'cisco': rad.CiscoIOSAdapter,
                'juniper': rad.JuniperAdapter,
                'exabgp': rad.ExaBGPAdapter,
            }
            cls = amap.get(adapter.lower(), rad.ExaBGPAdapter)
            inst = cls(adapter, config=obj.get('config'))
            if action == 'remove':
                result = inst.remove_blackhole(prefix)
            else:
                result = inst.send_blackhole(prefix, community=community)
            detail = 'ok' if result else 'failed'
        except Exception as e:
            detail = str(e)
            result = False

        # record action to DATA_DIR
        try:
            log_entry = {
                'time': datetime.utcnow().isoformat() + 'Z',
                'prefix': prefix,
                'action': action,
                'adapter': adapter,
                'community': community,
                'result': result,
                'detail': detail,
            }
            lf = os.path.join(DATA_DIR, 'blackholes.jsonl')
            with open(lf, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception:
            pass

        # also record in DB if available for audit/rollback
        try:
            if db_mod:
                try:
                    # operator: record admin key presence (do not store raw key in prod)
                    operator = 'admin'
                    lid = db_mod.log_blackhole_action(prefix=prefix, action=action, adapter=adapter, community=community, result=result, detail=detail, operator=operator)
                    # include DB id in response detail when possible
                    detail = (detail or '') + f' db_id={lid}'
                except Exception:
                    pass
        except Exception:
            pass

        status = 200 if result else 500
        body = json.dumps({'result': result, 'detail': detail}).encode()
        await send({'type': 'http.response.start', 'status': status, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
        await send({'type': 'http.response.body', 'body': body})
        return

    # GET /api/v1/blackhole/logs -> list recent blackhole actions (admin)
    if method == 'GET' and path == '/api/v1/blackhole/logs':
        qs = scope.get('query_string', b'').decode()
        from urllib.parse import parse_qs
        params = parse_qs(qs)
        try:
            limit = int(params.get('limit', ['100'])[0])
        except Exception:
            limit = 100
        prefix = params.get('prefix', [None])[0]
        try:
            if not db_mod:
                raise RuntimeError('DB not enabled')
            logs = db_mod.list_blackhole_actions(limit=limit, prefix=prefix)
            body = json.dumps({'logs': logs}, ensure_ascii=False).encode()
            await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
            await send({'type': 'http.response.body', 'body': body})
        except Exception as e:
            body = json.dumps({'detail': 'failed', 'error': str(e)}).encode()
            await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
            await send({'type': 'http.response.body', 'body': body})
        return

    # POST /api/v1/blackhole/revert -> revert a prior blackhole action by id (admin)
    if method == 'POST' and path == '/api/v1/blackhole/revert':
        more_body = True
        body_bytes = b''
        while more_body:
            event = await receive()
            if event['type'] == 'http.request':
                body_bytes += event.get('body', b'')
                more_body = event.get('more_body', False)
        try:
            obj = json.loads(body_bytes.decode()) if body_bytes else {}
        except Exception:
            obj = {}
        orig_id = obj.get('id')
        if not orig_id:
            body = json.dumps({'detail': 'id required'}).encode()
            await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]} )
            await send({'type': 'http.response.body', 'body': body})
            return
        try:
            if not db_mod:
                raise RuntimeError('DB not enabled')
            orig = db_mod.get_blackhole_action(int(orig_id))
            if not orig:
                body = json.dumps({'detail': 'not found'}).encode()
                await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json']]} )
                await send({'type': 'http.response.body', 'body': body})
                return
            # inverse action
            inv = 'remove' if orig.get('action') == 'add' else 'add'
            adapter = orig.get('adapter') or 'exabgp'
            community = orig.get('community')
            # lazy import adapters
            try:
                from backend import router_adapters as rad
            except Exception:
                try:
                    import router_adapters as rad
                except Exception:
                    rad = None
            if not rad:
                raise RuntimeError('router adapters not available')
            amap = {
                'cisco': rad.CiscoIOSAdapter,
                'juniper': rad.JuniperAdapter,
                'exabgp': rad.ExaBGPAdapter,
            }
            cls = amap.get((adapter or 'exabgp').lower(), rad.ExaBGPAdapter)
            inst = cls(adapter, config={})
            if inv == 'remove':
                ok = inst.remove_blackhole(orig.get('prefix'))
            else:
                ok = inst.send_blackhole(orig.get('prefix'), community=community)
            detail = 'ok' if ok else 'failed'
            # log revert action
            try:
                operator = 'admin'
                new_id = None
                if db_mod:
                    new_id = db_mod.log_blackhole_action(prefix=orig.get('prefix'), action=inv, adapter=adapter, community=community, result=ok, detail=f'revert_of={orig.get("id")}', operator=operator)
            except Exception:
                new_id = None
            # also append to file log
            try:
                lf = os.path.join(DATA_DIR, 'blackholes.jsonl')
                with open(lf, 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'time': datetime.utcnow().isoformat() + 'Z', 'prefix': orig.get('prefix'), 'action': inv, 'adapter': adapter, 'result': ok, 'detail': f'revert_of={orig.get("id")}', 'db_id': new_id}, ensure_ascii=False) + '\n')
            except Exception:
                pass
            status = 200 if ok else 500
            body = json.dumps({'result': ok, 'detail': detail, 'log_id': new_id}).encode()
            await send({'type': 'http.response.start', 'status': status, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
            await send({'type': 'http.response.body', 'body': body})
            return
        except Exception as e:
            body = json.dumps({'detail': 'failed', 'error': str(e)}).encode()
            await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
            await send({'type': 'http.response.body', 'body': body})
            return

    # ASN topology endpoints
    if path.startswith('/api/v1/asn'):
        # GET /api/v1/asn -> list ASNs
        if method == 'GET' and path == '/api/v1/asn':
            if not db_mod:
                body = json.dumps({'detail': 'DB not enabled'}).encode()
                await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json']]} )
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                res = db_mod.list_asns()
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'list failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        # GET /api/v1/asn/graph -> nodes + links
        if method == 'GET' and path == '/api/v1/asn/graph':
            if not db_mod:
                body = json.dumps({'detail': 'DB not enabled'}).encode()
                await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json']]} )
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                res = db_mod.query_as_graph()
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'graph failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        # GET /api/v1/asn/locations -> list ASNs with optional lat/lon
        if method == 'GET' and path == '/api/v1/asn/locations':
            if not db_mod:
                body = json.dumps({'detail': 'DB not enabled'}).encode()
                await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json']]} )
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                rows = db_mod.list_asns()
                # use built-in country centroid lookup if available
                try:
                    from backend.data.country_centroids import get_country_center
                except Exception:
                    def get_country_center(x):
                        return (None, None)

                out = []
                minutes = None
                try:
                    qs = scope.get('query_string', b'').decode()
                    from urllib.parse import parse_qs
                    params = parse_qs(qs)
                    minutes = int(params.get('minutes', [None])[0]) if params.get('minutes') else None
                except Exception:
                    minutes = None

                for r in rows:
                    lat, lon = None, None
                    # prefer DB-stored values if present
                    if isinstance(r, dict):
                        lat = r.get('lat')
                        lon = r.get('lon')
                    else:
                        try:
                            lat = getattr(r, 'lat', None)
                            lon = getattr(r, 'lon', None)
                        except Exception:
                            lat = lon = None

                    if not lat or not lon:
                        lat, lon = get_country_center(r.get('country') if isinstance(r, dict) else getattr(r, 'country', None))
                        # persist to DB when available
                        try:
                            if db_mod and lat is not None and lon is not None:
                                try:
                                    db_mod.set_asn_location(r.get('asn') if isinstance(r, dict) else getattr(r, 'asn', None), lat, lon)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    weight = 0
                    try:
                        if minutes and db_mod:
                            try:
                                series = db_mod.aggregate_counts_by_asn(r.get('asn') if isinstance(r, dict) else getattr(r, 'asn', None), minutes=minutes)
                                weight = sum(series.get('counts', [])) if series else 0
                            except Exception:
                                weight = 0
                    except Exception:
                        weight = 0

                    item = {**r, 'lat': lat, 'lon': lon, 'weight': weight}
                    out.append(item)
                body = json.dumps({'items': out}, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]} )
                await send({'type': 'http.response.body', 'body': body})
            return

        # GET /api/v1/asn/telemetry?asn=123&minutes=60
        if method == 'GET' and path == '/api/v1/asn/telemetry':
            if not db_mod:
                body = json.dumps({'detail': 'DB not enabled'}).encode()
                await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json']]} )
                await send({'type': 'http.response.body', 'body': body})
                return
            qs = scope.get('query_string', b'').decode()
            from urllib.parse import parse_qs
            params = parse_qs(qs)
            try:
                asn = int(params.get('asn', [None])[0])
            except Exception:
                asn = None
            minutes = int(params.get('minutes', ['60'])[0])
            if not asn:
                body = json.dumps({'detail': 'asn param required'}).encode()
                await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]} )
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                series = db_mod.aggregate_counts_by_asn(asn, minutes=minutes)
                samples = db_mod.get_telemetry_for_asn(asn, limit=200)
                res = {'series': series, 'samples': samples}
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        # POST endpoints require admin auth
        adm_key = headers.get('x-admin-key')
        if adm_key != ADMIN_API_KEY:
            body = json.dumps({'detail': 'invalid admin key'}).encode()
            await send({'type': 'http.response.start', 'status': 401, 'headers': [[b'content-type', b'application/json']]} )
            await send({'type': 'http.response.body', 'body': body})
            return

        # POST /api/v1/asn -> create ASN
        if method == 'POST' and path == '/api/v1/asn':
            more_body = True
            body_bytes = b''
            while more_body:
                event = await receive()
                if event['type'] == 'http.request':
                    body_bytes += event.get('body', b'')
                    more_body = event.get('more_body', False)
            try:
                obj = json.loads(body_bytes.decode())
            except Exception:
                await send({'type': 'http.response.start', 'status': 400})
                await send({'type': 'http.response.body', 'body': b''})
                return
            asn = obj.get('asn')
            name = obj.get('name')
            country = obj.get('country')
            if not asn:
                body = json.dumps({'detail': 'asn required'}).encode()
                await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]})
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                db_mod.create_asn(int(asn), name=name, country=country)
                body = json.dumps({'asn': int(asn), 'name': name, 'country': country}).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'create failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        # POST /api/v1/asn/peer -> add neighbor relation
        if method == 'POST' and path == '/api/v1/asn/peer':
            more_body = True
            body_bytes = b''
            while more_body:
                event = await receive()
                if event['type'] == 'http.request':
                    body_bytes += event.get('body', b'')
                    more_body = event.get('more_body', False)
            try:
                obj = json.loads(body_bytes.decode())
            except Exception:
                await send({'type': 'http.response.start', 'status': 400})
                await send({'type': 'http.response.body', 'body': b''})
                return
            asn = obj.get('asn')
            neighbor = obj.get('neighbor')
            relation = obj.get('relation', 'peer')
            if not asn or not neighbor:
                body = json.dumps({'detail': 'asn and neighbor required'}).encode()
                await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]})
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                db_mod.add_as_link(int(asn), int(neighbor), relation=relation)
                body = json.dumps({'asn': int(asn), 'neighbor': int(neighbor), 'relation': relation}).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'add link failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        

        # IRR / prefix mapping endpoints
        # POST /api/v1/irr/map  (admin)
        if method == 'POST' and path == '/api/v1/irr/map':
            more_body = True
            body_bytes = b''
            while more_body:
                event = await receive()
                if event['type'] == 'http.request':
                    body_bytes += event.get('body', b'')
                    more_body = event.get('more_body', False)
            try:
                obj = json.loads(body_bytes.decode())
            except Exception:
                await send({'type': 'http.response.start', 'status': 400})
                await send({'type': 'http.response.body', 'body': b''})
                return
            prefix = obj.get('prefix')
            asn = obj.get('asn')
            source = obj.get('source')
            if not prefix or not asn:
                body = json.dumps({'detail': 'prefix and asn required'}).encode()
                await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]})
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                db_mod.add_prefix_mapping(prefix, int(asn), source=source)
                body = json.dumps({'prefix': prefix, 'asn': int(asn), 'source': source}).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'map failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        # GET /api/v1/irr/lookup?prefix=1.2.3.0/24
        if method == 'GET' and path == '/api/v1/irr/lookup':
            qs = scope.get('query_string', b'').decode()
            from urllib.parse import parse_qs
            params = parse_qs(qs)
            prefix = params.get('prefix', [None])[0]
            if not prefix:
                body = json.dumps({'detail': 'prefix param required'}).encode()
                await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]})
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                res = db_mod.lookup_prefix(prefix)
                if not res:
                    body = json.dumps({'detail': 'not found'}).encode()
                    await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                    await send({'type': 'http.response.body', 'body': body})
                    return
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'lookup failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return
        # IP lookup: /api/v1/irr/lookup?ip=1.2.3.4
        if method == 'GET' and path == '/api/v1/irr/lookup' and 'ip=' in scope.get('query_string', b'').decode():
            qs = scope.get('query_string', b'').decode()
            from urllib.parse import parse_qs
            params = parse_qs(qs)
            ip = params.get('ip', [None])[0]
            if not ip:
                body = json.dumps({'detail': 'ip param required'}).encode()
                await send({'type': 'http.response.start', 'status': 400, 'headers': [[b'content-type', b'application/json']]})
                await send({'type': 'http.response.body', 'body': body})
                return
            try:
                res = db_mod.lookup_ip(ip)
                if not res:
                    body = json.dumps({'detail': 'not found'}).encode()
                    await send({'type': 'http.response.start', 'status': 404, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                    await send({'type': 'http.response.body', 'body': body})
                    return
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'lookup failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

        # POST /api/v1/irr/import-telemetry (admin) -> bulk scan telemetry and import prefixes
        if method == 'POST' and path == '/api/v1/irr/import-telemetry':
            more_body = True
            body_bytes = b''
            while more_body:
                event = await receive()
                if event['type'] == 'http.request':
                    body_bytes += event.get('body', b'')
                    more_body = event.get('more_body', False)
            try:
                obj = json.loads(body_bytes.decode()) if body_bytes else {}
            except Exception:
                obj = {}
            limit = obj.get('limit')
            try:
                res = db_mod.scan_and_import_prefixes(limit=limit)
                body = json.dumps(res, ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            except Exception as e:
                body = json.dumps({'detail': 'import failed', 'error': str(e)}).encode()
                await send({'type': 'http.response.start', 'status': 500, 'headers': [[b'content-type', b'application/json; charset=utf-8']]})
                await send({'type': 'http.response.body', 'body': body})
            return

    if method == "POST" and path == "/api/v1/ingest":
        key = headers.get("x-api-key")

        # read body
        more_body = True
        body_bytes = b""
        while more_body:
            event = await receive()
            if event["type"] == "http.request":
                body_bytes += event.get("body", b"")
                more_body = event.get("more_body", False)

        try:
            obj = json.loads(body_bytes.decode())
        except Exception:
            await send({"type": "http.response.start", "status": 400})
            await send({"type": "http.response.body", "body": b""})
            return

        tenant = obj.get("tenant_id") or "default"
        # validate key for tenant: either global API_KEY or tenant-specific
        if key != API_KEY and not validate_key(key, tenant):
            body = json.dumps({"detail": "invalid api key for tenant"}).encode()
            await send({"type": "http.response.start", "status": 401, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
            return
        # try writing to DB if available
        record = {
            "received_at": datetime.utcnow().isoformat() + "Z",
            "source": obj.get("source"),
            "timestamp": obj.get("timestamp"),
            "payload": obj.get("payload"),
        }
        wrote_db = False
        # attempt to extract ASN info from payload and persist
        try:
            payload_obj = obj.get('payload')
            if db_mod and isinstance(payload_obj, dict):
                try:
                    # possible keys: 'asn', 'origin_asn', 'asn_name', 'peers', 'neighbor_asn'
                    if 'asn' in payload_obj:
                        db_mod.create_asn(int(payload_obj.get('asn')), name=payload_obj.get('asn_name'))
                    if 'origin_asn' in payload_obj:
                        db_mod.create_asn(int(payload_obj.get('origin_asn')))
                    # peers: list of ASNs
                    peers = payload_obj.get('peers')
                    if peers and isinstance(peers, (list, tuple)):
                        src_asn = payload_obj.get('asn') or payload_obj.get('origin_asn')
                        if src_asn:
                            for p in peers:
                                try:
                                    db_mod.add_as_link(int(src_asn), int(p), relation='peer')
                                except Exception:
                                    pass
                    # neighbor_asn single
                    if 'neighbor_asn' in payload_obj:
                        src = payload_obj.get('asn') or payload_obj.get('origin_asn')
                        if src:
                            try:
                                db_mod.add_as_link(int(src), int(payload_obj.get('neighbor_asn')))
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

        if db_mod:
            try:
                # ensure DB tables exist
                db_mod.init_db()
                db_mod.insert_telemetry(tenant, record.get("source"), record.get("timestamp"), json.dumps(record.get("payload")))
                wrote_db = True
            except Exception:
                wrote_db = False

        if not wrote_db:
            fname = os.path.join(DATA_DIR, f"{tenant}.jsonl")
            with open(fname, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        body = json.dumps({"result": "stored", "tenant": tenant, "db": wrote_db}).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})
        return

    # attempt to serve built frontend from frontend/dist if present
    try:
        dist_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
        if os.path.isdir(dist_dir):
            rel = path.lstrip('/')
            if rel == '':
                rel = 'index.html'
            fpath = os.path.join(dist_dir, rel)
            if os.path.exists(fpath) and os.path.isfile(fpath):
                try:
                    with open(fpath, 'rb') as fh:
                        body_bytes = fh.read()
                    ctype = 'text/html'
                    if fpath.endswith('.js'):
                        ctype = 'application/javascript'
                    elif fpath.endswith('.css'):
                        ctype = 'text/css'
                    elif fpath.endswith('.png'):
                        ctype = 'image/png'
                    elif fpath.endswith('.svg'):
                        ctype = 'image/svg+xml'
                    await send({'type': 'http.response.start', 'status': 200, 'headers': [[b'content-type', ctype.encode()]]})
                    await send({'type': 'http.response.body', 'body': body_bytes})
                    return
                except Exception:
                    pass
    except Exception:
        pass

    await send({"type": "http.response.start", "status": 404})
    await send({"type": "http.response.body", "body": b""})
