from backend import auth


def test_tenant_rbac_basic():
    auth.clear_stores()
    t1 = auth.create_tenant_obj('tenant-a')
    t2 = auth.create_tenant_obj('tenant-b')

    # create users with roles
    u1 = auth.create_user_obj(t1.id, 'alice', password=None, roles=['admin'])
    u2 = auth.create_user_obj(t2.id, 'bob', password=None, roles=['viewer'])

    tok1 = auth.issue_token(t1.id, 'alice')
    tok2 = auth.issue_token(t2.id, 'bob')

    @auth.require_role('admin')
    def secret_admin_action(token, payload=None):
        return f"ok:{auth.get_user_from_token(token).username}"

    # alice can run admin action
    assert secret_admin_action(tok1) == 'ok:alice'

    # bob cannot
    try:
        secret_admin_action(tok2)
        assert False, 'bob should not be allowed'
    except PermissionError:
        pass

    # token isolation: bob's token should map to bob
    u = auth.get_user_from_token(tok2)
    assert u.username == 'bob' and u.tenant_id == t2.id
