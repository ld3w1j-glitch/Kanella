import sqlite3
from werkzeug.security import generate_password_hash
from app import create_app


def test_admin_password_change_and_session_revocation(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret', 'DATABASE': str(tmp_path / 'test.sqlite'), 'RATE_LIMIT_ENABLED': False})
    with sqlite3.connect(app.config['DATABASE']) as db:
        db.execute('INSERT INTO users(id,email,password_hash,name,phone,is_admin) VALUES(?,?,?,?,?,1)', ('admin', 'admin@example.com', generate_password_hash('old-password'), 'Admin', ''))
        db.execute('INSERT INTO users(id,email,password_hash,name,phone,is_admin) VALUES(?,?,?,?,?,0)', ('client', 'client@example.com', generate_password_hash('client-password'), 'Cliente', ''))

    def post(client, path, body):
        token = client.get('/api/bootstrap').json['csrfToken']
        return client.post(path, json=body, headers={'X-CSRF-Token': token})

    def login(client, email, password):
        return post(client, '/api/login', {'email': email, 'password': password})

    anonymous = app.test_client()
    assert post(anonymous, '/api/admin/password', {'currentPassword': 'old-password', 'newPassword': 'new-password'}).status_code == 401
    client = app.test_client()
    assert login(client, 'client@example.com', 'client-password').status_code == 200
    assert post(client, '/api/admin/password', {'currentPassword': 'client-password', 'newPassword': 'new-password'}).status_code == 403
    admin = app.test_client()
    second_session = app.test_client()
    assert login(admin, 'admin@example.com', 'old-password').status_code == 200
    assert login(second_session, 'admin@example.com', 'old-password').status_code == 200
    assert admin.post('/api/admin/password', json={'currentPassword': 'old-password', 'newPassword': 'new-password'}).status_code == 403
    token = admin.get('/api/bootstrap').json['csrfToken']
    assert admin.post('/api/admin/password', json={'currentPassword': 'old-password', 'newPassword': 'new-password'}, headers={'X-CSRF-Token': token, 'Origin': 'https://malicious.example'}).status_code == 403
    assert post(admin, '/api/admin/password', {'currentPassword': 'wrong', 'newPassword': 'new-password'}).status_code == 401
    assert post(admin, '/api/admin/password', {'currentPassword': 'old-password', 'newPassword': 'short'}).status_code == 400
    assert post(admin, '/api/admin/password', {'currentPassword': 'old-password', 'newPassword': 'new-password'}).status_code == 200
    assert admin.get('/api/admin').status_code == 200
    assert second_session.get('/api/admin').status_code == 401
    assert login(app.test_client(), 'admin@example.com', 'old-password').status_code == 401
    assert login(app.test_client(), 'admin@example.com', 'new-password').status_code == 200
