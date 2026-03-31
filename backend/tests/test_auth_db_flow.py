from backend import auth, db


def test_db_user_token_flow():
    # ensure DB tables present
    db.init_db()
    auth.clear_stores()

    tid = auth.create_tenant('acme')
    uid = auth.create_user(tid, 'alice', password='s3cr3t', roles=['admin'])
    assert uid is not None

    # authenticate
    authed = auth.authenticate_user(tid, 'alice', 's3cr3t')
    assert authed == uid

    toks = auth.issue_tokens_for_user(uid)
    assert 'access_token' in toks and 'refresh_token' in toks

    new = auth.refresh_access_token(toks['refresh_token'])
    assert new and 'access_token' in new

    # revoke and ensure refresh fails
    assert auth.revoke_refresh_token(toks['refresh_token']) is True
    assert auth.refresh_access_token(toks['refresh_token']) is None
