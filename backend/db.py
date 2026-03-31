import os
import uuid
import json
import ipaddress
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, text, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

# optional radix index for LPM (py-radix / radix package)
_radix = None
_radix_built = False
try:
    import radix as _radix_mod
except Exception:
    try:
        # fallback to pure-python implementation if available in repo
        from backend import simple_radix as _radix_mod
    except Exception:
        _radix_mod = None
DB_URL = os.getenv("OPEN_DCMS_DB_URL", "sqlite:///./.data/open_dcms.db")

connect_args = {}
if DB_URL.startswith("sqlite:"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    tenant = Column(String(256), index=True, nullable=False)
    key = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Telemetry(Base):
    __tablename__ = "telemetry"
    id = Column(Integer, primary_key=True, index=True)
    tenant = Column(String(256), index=True, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    source = Column(String(256), nullable=True)
    ts = Column(String(64), nullable=True)
    ts_dt = Column(DateTime(timezone=True), nullable=True, index=True)
    payload = Column(String, nullable=True)  # store JSON as text for SQLite


class ASN(Base):
    __tablename__ = 'asns'
    id = Column(Integer, primary_key=True, index=True)
    asn = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String(512), nullable=True)
    country = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ASLink(Base):
    __tablename__ = 'as_links'
    id = Column(Integer, primary_key=True, index=True)
    asn = Column(Integer, ForeignKey('asns.asn'), index=True, nullable=False)
    neighbor = Column(Integer, ForeignKey('asns.asn'), index=True, nullable=False)
    relation = Column(String(32), nullable=True)  # peer, provider, customer
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PrefixMapping(Base):
    __tablename__ = 'prefix_mappings'
    id = Column(Integer, primary_key=True, index=True)
    prefix = Column(String(64), index=True, nullable=False)  # e.g. 1.2.3.0/24
    asn = Column(Integer, index=True, nullable=False)
    source = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TenantModel(Base):
    __tablename__ = 'tenants'
    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(256), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserModel(Base):
    __tablename__ = 'users'
    id = Column(String(64), primary_key=True, index=True)
    tenant_id = Column(String(64), ForeignKey('tenants.id'), index=True, nullable=False)
    username = Column(String(128), nullable=False)
    password_hash = Column(String(256), nullable=True)
    password_salt = Column(String(64), nullable=True)
    roles = Column(String(256), nullable=True)  # comma separated
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(128), unique=True, index=True, nullable=False)
    user_id = Column(String(64), ForeignKey('users.id'), index=True, nullable=False)
    revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())


class UserAudit(Base):
    __tablename__ = 'user_audit'
    id = Column(Integer, primary_key=True, index=True)
    operator_user_id = Column(String(64), nullable=True, index=True)
    action = Column(String(64), nullable=False)  # create_user, reset_password
    target_user_id = Column(String(64), nullable=True, index=True)
    target_username = Column(String(128), nullable=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    details = Column(String(1024), nullable=True)
    operator_ip = Column(String(64), nullable=True)
    request_id = Column(String(128), nullable=True, index=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


def init_db():
    os.makedirs(os.path.dirname(DB_URL.replace('file:', '').replace('sqlite:///', './').split('?')[0]), exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # perform simple migration: add ts_dt column if missing (SQLite supports ADD COLUMN)
    if DB_URL.startswith('sqlite'):
        with engine.connect() as conn:
            try:
                res = conn.execute(text("PRAGMA table_info('telemetry')")).all()
                cols = [r[1] for r in res]
                if 'ts_dt' not in cols:
                    conn.execute(text("ALTER TABLE telemetry ADD COLUMN ts_dt DATETIME"))
            except Exception:
                pass
            # ensure user_audit has operator_ip and request_id columns (simple migration)
            try:
                res = conn.execute(text("PRAGMA table_info('user_audit')")).all()
                cols = [r[1] for r in res]
                if 'operator_ip' not in cols:
                    conn.execute(text("ALTER TABLE user_audit ADD COLUMN operator_ip TEXT"))
                if 'request_id' not in cols:
                    conn.execute(text("ALTER TABLE user_audit ADD COLUMN request_id TEXT"))
            except Exception:
                pass


def create_api_key(tenant: str):
    key = str(uuid.uuid4())
    db = SessionLocal()
    try:
        obj = APIKey(tenant=tenant, key=key)
        db.add(obj)
        db.commit()
        return key
    finally:
        db.close()


def list_api_keys(tenant: str = None):
    db = SessionLocal()
    try:
        q = db.query(APIKey)
        if tenant:
            rows = q.filter(APIKey.tenant == tenant).all()
            return [r.key for r in rows]
        rows = q.all()
        result = {}
        for r in rows:
            result.setdefault(r.tenant, []).append(r.key)
        return result
    finally:
        db.close()


def validate_api_key(api_key: str, tenant: str):
    if not api_key:
        return False
    db = SessionLocal()
    try:
        row = db.query(APIKey).filter(APIKey.key == api_key, APIKey.tenant == tenant).first()
        return row is not None
    finally:
        db.close()


def insert_telemetry(tenant: str, source: str, ts: str, payload_text: str):
    db = SessionLocal()
    try:
        # attempt to parse ts into a proper datetime for ts_dt
        ts_dt_val = None
        try:
            if ts:
                # handle trailing Z
                if ts.endswith('Z'):
                    ts_norm = ts.replace('Z', '+00:00')
                else:
                    ts_norm = ts
                from datetime import datetime
                ts_dt_val = datetime.fromisoformat(ts_norm)
        except Exception:
            ts_dt_val = None

        obj = Telemetry(tenant=tenant, source=source, ts=ts, ts_dt=ts_dt_val, payload=payload_text)
        db.add(obj)
        db.commit()
        return obj.id
    finally:
        db.close()


def get_latest_for_tenant(tenant: str):
    db = SessionLocal()
    try:
        # prefer ordering by ts_dt if available
        try:
            row = db.query(Telemetry).filter(Telemetry.tenant == tenant).order_by(Telemetry.ts_dt.desc().nullslast(), Telemetry.id.desc()).first()
        except Exception:
            row = db.query(Telemetry).filter(Telemetry.tenant == tenant).order_by(Telemetry.id.desc()).first()
        if not row:
            return None
        return {
            "received_at": row.received_at.isoformat() if row.received_at else None,
            "source": row.source,
            "timestamp": row.ts,
            "payload": json.loads(row.payload) if row.payload else None,
        }
    finally:
        db.close()


def query_telemetry(tenant: str = None, limit: int = 100, offset: int = 0, since: str = None, until: str = None, source: str = None, payload_key: str = None, cursor: int = None):
    db = SessionLocal()
    try:
        q = db.query(Telemetry)
        if tenant:
            q = q.filter(Telemetry.tenant == tenant)
        if source:
            q = q.filter(Telemetry.source == source)
        # cursor pagination: accept numeric id or opaque token
        if cursor:
            try:
                # try numeric first
                q = q.filter(Telemetry.id < int(cursor))
            except Exception:
                # try opaque token (base64 JSON: {"last_id":N})
                try:
                    import base64, json as _json
                    dec = base64.b64decode(cursor)
                    obj = _json.loads(dec.decode())
                    last = int(obj.get('last_id'))
                    q = q.filter(Telemetry.id < last)
                except Exception:
                    pass
        # use parsed datetime column if possible
        if since:
            try:
                if since.endswith('Z'):
                    since_norm = since.replace('Z', '+00:00')
                else:
                    since_norm = since
                from datetime import datetime
                since_dt = datetime.fromisoformat(since_norm)
                q = q.filter(Telemetry.ts_dt >= since_dt)
            except Exception:
                q = q.filter(Telemetry.ts >= since)
        if until:
            try:
                if until.endswith('Z'):
                    until_norm = until.replace('Z', '+00:00')
                else:
                    until_norm = until
                from datetime import datetime
                until_dt = datetime.fromisoformat(until_norm)
                q = q.filter(Telemetry.ts_dt <= until_dt)
            except Exception:
                q = q.filter(Telemetry.ts <= until)

        total = q.count()
        try:
            rows = q.order_by(Telemetry.ts_dt.desc().nullslast(), Telemetry.id.desc()).offset(offset).limit(limit * 5).all()
        except Exception:
            rows = q.order_by(Telemetry.id.desc()).offset(offset).limit(limit * 5).all()

        items = []
        for r in rows:
            try:
                payload = json.loads(r.payload) if r.payload else None
            except Exception:
                payload = r.payload
            # payload_key filtering in Python (SQLite JSON functions may not be available)
            if payload_key and isinstance(payload, dict):
                if payload_key not in payload:
                    continue
            items.append({
                "id": r.id,
                "tenant": r.tenant,
                "received_at": r.received_at.isoformat() if r.received_at else None,
                "source": r.source,
                "timestamp": r.ts,
                "payload": payload,
            })
            if len(items) >= limit:
                break

        next_cursor = None
        if items:
            last_id = items[-1]["id"]
            # produce opaque cursor token
            try:
                import base64, json as _json
                token = _json.dumps({"last_id": last_id}).encode()
                next_cursor = base64.b64encode(token).decode()
            except Exception:
                next_cursor = str(last_id)

        return {"total": total, "limit": limit, "offset": offset, "items": items, "next_cursor": next_cursor}
    finally:
        db.close()


### ASN topology helpers

def create_asn(asn: int, name: str = None, country: str = None):
    db = SessionLocal()
    try:
        existing = db.query(ASN).filter(ASN.asn == int(asn)).first()
        if existing:
            return existing.asn
        obj = ASN(asn=int(asn), name=name, country=country)
        db.add(obj)
        db.commit()
        return obj.asn
    finally:
        db.close()


def list_asns():
    db = SessionLocal()
    try:
        rows = db.query(ASN).order_by(ASN.asn).all()
        return [{"asn": r.asn, "name": r.name, "country": r.country} for r in rows]
    finally:
        db.close()


def add_as_link(asn: int, neighbor: int, relation: str = 'peer'):
    db = SessionLocal()
    try:
        # ensure both ASNs exist
        create_asn(asn)
        create_asn(neighbor)
        # avoid duplicates
        existing = db.query(ASLink).filter(ASLink.asn == int(asn), ASLink.neighbor == int(neighbor)).first()
        if existing:
            return existing.id
        obj = ASLink(asn=int(asn), neighbor=int(neighbor), relation=relation)
        db.add(obj)
        db.commit()
        return obj.id
    finally:
        db.close()


def get_as_neighbors(asn: int):
    db = SessionLocal()
    try:
        rows = db.query(ASLink).filter((ASLink.asn == int(asn)) | (ASLink.neighbor == int(asn))).all()
        neighbors = []
        for r in rows:
            if r.asn == int(asn):
                neighbors.append({"asn": r.neighbor, "relation": r.relation})
            else:
                neighbors.append({"asn": r.asn, "relation": r.relation})
        return neighbors
    finally:
        db.close()


def query_as_graph():
    db = SessionLocal()
    try:
        nodes = db.query(ASN).all()
        links = db.query(ASLink).all()
        nlist = [{"asn": n.asn, "name": n.name, "country": n.country} for n in nodes]
        llist = [{"from": l.asn, "to": l.neighbor, "relation": l.relation} for l in links]
        return {"nodes": nlist, "links": llist}
    finally:
        db.close()


### Prefix -> ASN mapping helpers (simple IRR/Whois cache)

def add_prefix_mapping(prefix: str, asn: int, source: str = None):
    db = SessionLocal()
    try:
        # normalize prefix string
        p = str(prefix).strip()
        existing = db.query(PrefixMapping).filter(PrefixMapping.prefix == p, PrefixMapping.asn == int(asn)).first()
        if existing:
            return existing.id
        obj = PrefixMapping(prefix=p, asn=int(asn), source=source)
        db.add(obj)
        db.commit()
        # invalidate radix cache
        global _radix_built, _radix
        _radix_built = False
        _radix = None
        return obj.id
    finally:
        db.close()


def lookup_prefix(prefix: str):
    db = SessionLocal()
    try:
        p = str(prefix).strip()
        row = db.query(PrefixMapping).filter(PrefixMapping.prefix == p).first()
        if row:
            return {"prefix": row.prefix, "asn": row.asn, "source": row.source}
        return None
    finally:
        db.close()


def scan_and_import_prefixes(limit: int = None):
    db = SessionLocal()
    try:
        q = db.query(Telemetry).order_by(Telemetry.ts_dt.desc().nullslast(), Telemetry.id.desc())
        if limit:
            rows = q.limit(limit).all()
        else:
            rows = q.all()
        imported = 0
        for r in rows:
            try:
                payload = json.loads(r.payload) if r.payload else None
            except Exception:
                payload = None
            if not payload or not isinstance(payload, dict):
                continue
            prefixes = []
            if 'prefix' in payload:
                prefixes.append(payload.get('prefix'))
            if 'prefixes' in payload and isinstance(payload.get('prefixes'), (list, tuple)):
                prefixes.extend(payload.get('prefixes'))
            for k in ('ip','src_ip','dst_ip','client_ip'):
                if k in payload:
                    try:
                        ip = ipaddress.ip_address(payload.get(k))
                        if ip.version == 4:
                            prefixes.append(str(ipaddress.ip_network(str(ip) + '/24', strict=False)))
                        else:
                            prefixes.append(str(ipaddress.ip_network(str(ip) + '/64', strict=False)))
                    except Exception:
                        pass
            seen = set()
            for p in prefixes:
                if not p:
                    continue
                if p in seen:
                    continue
                seen.add(p)
                asn = None
                if 'asn' in payload:
                    try: asn = int(payload.get('asn'))
                    except Exception: asn = None
                if not asn and 'origin_asn' in payload:
                    try: asn = int(payload.get('origin_asn'))
                    except Exception: asn = None
                if asn:
                    try:
                        add_prefix_mapping(p, asn, source='telemetry')
                        create_asn(asn)
                        imported += 1
                    except Exception:
                        pass
        return {'imported': imported}
    finally:
        db.close()


def _build_radix_index():
    """Build an in-memory radix tree from `prefix_mappings` table.
    Falls back gracefully if `radix` package is unavailable.
    """
    global _radix_built, _radix, _radix_mod
    if _radix_built:
        return
    _radix = None
    if not _radix_mod:
        _radix_built = True
        return
    r = _radix_mod.Radix()
    db = SessionLocal()
    try:
        rows = db.query(PrefixMapping).all()
        for row in rows:
            try:
                node = r.add(row.prefix)
                node.data['asn'] = row.asn
                node.data['source'] = row.source
            except Exception:
                continue
    finally:
        db.close()
    _radix = r
    _radix_built = True



def lookup_ip(ip_str: str):
    try:
        ip = ipaddress.ip_address(ip_str)
    except Exception:
        return None
    db = SessionLocal()
    try:
        # prefer radix LPM if available
        try:
            _build_radix_index()
            if _radix:
                # radix.Radix supports search_best
                node = _radix.search_best(str(ip))
                if node and hasattr(node, 'prefix'):
                    return {'prefix': node.prefix, 'asn': node.data.get('asn'), 'source': node.data.get('source')}
        except Exception:
            pass

        # fallback: full table scan LPM
        rows = db.query(PrefixMapping).all()
        best = None
        best_pref = -1
        for r in rows:
            try:
                net = ipaddress.ip_network(r.prefix, strict=False)
                if ip in net:
                    if net.prefixlen > best_pref:
                        best_pref = net.prefixlen
                        best = {'prefix': r.prefix, 'asn': r.asn, 'source': r.source}
            except Exception:
                continue
        return best
    finally:
        db.close()

def create_tenant_db(name: str):
    db = SessionLocal()
    try:
        tid = str(uuid.uuid4())
        t = TenantModel(id=tid, name=name)
        db.add(t)
        db.commit()
        return tid
    finally:
        db.close()


def create_user_db(tenant_id: str, username: str, password_hash: str = None, password_salt: str = None, roles: str = None):
    db = SessionLocal()
    try:
        uid = str(uuid.uuid4())
        u = UserModel(id=uid, tenant_id=tenant_id, username=username, password_hash=password_hash, password_salt=password_salt, roles=roles)
        db.add(u)
        db.commit()
        return uid
    finally:
        db.close()


def get_user_db(tenant_id: str, username: str):
    db = SessionLocal()
    try:
        row = db.query(UserModel).filter(UserModel.tenant_id == tenant_id, UserModel.username == username).first()
        return row
    finally:
        db.close()


def store_refresh_token(token: str, user_id: str, expires_at=None):
    db = SessionLocal()
    try:
        rt = RefreshToken(token=token, user_id=user_id, expires_at=expires_at)
        db.add(rt)
        db.commit()
        return rt.token
    finally:
        db.close()


def validate_refresh_token_db(token: str):
    from datetime import datetime
    db = SessionLocal()
    try:
        row = db.query(RefreshToken).filter(RefreshToken.token == token, RefreshToken.revoked == False).first()
        if not row:
            return None
        if row.expires_at and datetime.utcnow() > row.expires_at:
            return None
        return row
    finally:
        db.close()


def revoke_refresh_token_db(token: str):
    db = SessionLocal()
    try:
        row = db.query(RefreshToken).filter(RefreshToken.token == token).first()
        if not row:
            return False
        row.revoked = True
        db.add(row)
        db.commit()
        return True
    finally:
        db.close()


def log_user_audit(operator_user_id: str, action: str, target_user_id: str = None, target_username: str = None, tenant_id: str = None, details: str = None):
    dbs = SessionLocal()
    try:
        obj = UserAudit(operator_user_id=operator_user_id, action=action, target_user_id=target_user_id, target_username=target_username, tenant_id=tenant_id, details=details)
        dbs.add(obj)
        dbs.commit()
        return obj.id
    finally:
        dbs.close()


def list_user_audit(tenant_id: str = None, limit: int = 100):
    dbs = SessionLocal()
    try:
        q = dbs.query(UserAudit).order_by(UserAudit.performed_at.desc())
        if tenant_id:
            q = q.filter(UserAudit.tenant_id == tenant_id)
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'operator_user_id': r.operator_user_id,
                'action': r.action,
                'target_user_id': r.target_user_id,
                'target_username': r.target_username,
                'tenant_id': r.tenant_id,
                'details': r.details,
                'performed_at': r.performed_at.isoformat() if r.performed_at else None,
            })
        return out
    finally:
        dbs.close()



def get_telemetry_for_asn(asn: int, limit: int = 200):
    db = SessionLocal()
    try:
        rows = db.query(Telemetry).order_by(Telemetry.ts_dt.desc().nullslast(), Telemetry.id.desc()).limit(2000).all()
        items = []
        for r in rows:
            try:
                payload = json.loads(r.payload) if r.payload else None
            except Exception:
                payload = None
            match = False
            if isinstance(payload, dict):
                if payload.get('asn') == asn or payload.get('origin_asn') == asn:
                    match = True
                for k in ('prefix','prefixes'):
                    if k in payload:
                        vals = payload.get(k)
                        if isinstance(vals, str): vals = [vals]
                        if isinstance(vals, (list,tuple)):
                            for v in vals:
                                mp = lookup_prefix(v)
                                if mp and mp.get('asn') == asn:
                                    match = True
                                    break
            if match:
                items.append({
                    'id': r.id,
                    'tenant': r.tenant,
                    'received_at': r.received_at.isoformat() if r.received_at else None,
                    'ts': r.ts,
                    'payload': payload
                })
            if len(items) >= limit:
                break
        return items
    finally:
        db.close()


def aggregate_counts_by_asn(asn: int, minutes: int = 60, bucket_seconds: int = 60):
    from datetime import datetime, timedelta
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        start = now - timedelta(minutes=minutes)
        rows = db.query(Telemetry).filter(Telemetry.ts_dt != None).filter(Telemetry.ts_dt >= start).order_by(Telemetry.ts_dt.asc()).all()
        nb = int(minutes * 60 / bucket_seconds)
        buckets = [0] * nb
        times = []
        for i in range(nb):
            times.append((start + timedelta(seconds=i*bucket_seconds)).isoformat() + 'Z')
        for r in rows:
            try:
                payload = json.loads(r.payload) if r.payload else None
            except Exception:
                payload = None
            matched = False
            if isinstance(payload, dict):
                if payload.get('asn') == asn or payload.get('origin_asn') == asn:
                    matched = True
                for k in ('prefix','prefixes'):
                    if k in payload:
                        vals = payload.get(k)
                        if isinstance(vals, str): vals = [vals]
                        if isinstance(vals, (list,tuple)):
                            for v in vals:
                                mp = lookup_prefix(v)
                                if mp and mp.get('asn') == asn:
                                    matched = True
                                    break
            if matched and r.ts_dt:
                delta = (r.ts_dt - start).total_seconds()
                idx = int(delta // bucket_seconds)
                if 0 <= idx < nb:
                    buckets[idx] += 1
        return {'times': times, 'counts': buckets}
    finally:
        db.close()


class BlackholeAction(Base):
    __tablename__ = 'blackhole_actions'
    id = Column(Integer, primary_key=True, index=True)
    prefix = Column(String(64), index=True, nullable=False)
    action = Column(String(16), nullable=False)  # add/remove
    adapter = Column(String(64), nullable=True)
    community = Column(String(64), nullable=True)
    result = Column(Boolean, nullable=True)
    detail = Column(String(1024), nullable=True)
    operator = Column(String(128), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())


def log_blackhole_action(prefix: str, action: str, adapter: str = None, community: str = None, result: bool = None, detail: str = None, operator: str = None):
    db = SessionLocal()
    try:
        obj = BlackholeAction(prefix=str(prefix), action=str(action), adapter=adapter, community=community, result=bool(result) if result is not None else None, detail=detail, operator=operator)
        db.add(obj)
        db.commit()
        return obj.id
    finally:
        db.close()


def list_blackhole_actions(limit: int = 100, prefix: str = None):
    db = SessionLocal()
    try:
        q = db.query(BlackholeAction).order_by(BlackholeAction.performed_at.desc())
        if prefix:
            q = q.filter(BlackholeAction.prefix == prefix)
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'prefix': r.prefix,
                'action': r.action,
                'adapter': r.adapter,
                'community': r.community,
                'result': bool(r.result) if r.result is not None else None,
                'detail': r.detail,
                'operator': r.operator,
                'performed_at': r.performed_at.isoformat() if r.performed_at else None,
            })
        return out
    finally:
        db.close()


def get_blackhole_action(action_id: int):
    db = SessionLocal()
    try:
        row = db.query(BlackholeAction).filter(BlackholeAction.id == int(action_id)).first()
        if not row:
            return None
        return {
            'id': row.id,
            'prefix': row.prefix,
            'action': row.action,
            'adapter': row.adapter,
            'community': row.community,
            'result': bool(row.result) if row.result is not None else None,
            'detail': row.detail,
            'operator': row.operator,
            'performed_at': row.performed_at.isoformat() if row.performed_at else None,
        }
    finally:
        db.close()
