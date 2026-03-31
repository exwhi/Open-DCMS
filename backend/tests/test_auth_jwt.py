import time
from backend import auth_jwt


def test_create_and_verify_token():
    secret = 's3cr3t'
    payload = {'sub': 'alice', 'tenant': 't-1', 'roles': ['admin']}
    token = auth_jwt.create_token(payload, secret, expires_in=2)
    data = auth_jwt.verify_token(token, secret)
    assert data['sub'] == 'alice'
    assert data['tenant'] == 't-1'


def test_expired_token_raises():
    secret = 's3cr3t'
    payload = {'sub': 'bob'}
    # use negative expires_in to ensure token is already expired
    token = auth_jwt.create_token(payload, secret, expires_in=-1)
    try:
        auth_jwt.verify_token(token, secret)
        assert False, 'expected InvalidToken'
    except auth_jwt.InvalidToken:
        pass
