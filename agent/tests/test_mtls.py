from agent.agent import try_send


def test_try_send_with_bad_cert():
    # Using an invalid server and non-existent client cert should be handled
    url = 'http://127.0.0.1:1/api/v1/ingest'  # port 1 likely closed
    headers = {'X-API-Key': 'dev'}
    payload = {'id': 'mtls-test'}
    ok = try_send(url, headers, payload, ca_cert=None, client_cert='nonexist.crt', client_key='nonexist.key', max_attempts=1)
    assert not ok
