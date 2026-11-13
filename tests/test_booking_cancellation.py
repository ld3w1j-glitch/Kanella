import sqlite3
import json
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from urllib.error import URLError

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from domain import now


@pytest.fixture
def booking_app(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'bookings.sqlite'), 'SECRET_KEY': 'cancel-test', 'RATE_LIMIT_ENABLED': False})
    with sqlite3.connect(app.config['DATABASE']) as db:
        db.execute('INSERT INTO users(id,email,password_hash,name,phone,is_admin) VALUES(?,?,?,?,?,1)', ('admin', 'admin@example.test', generate_password_hash('admin-password'), 'Gerente', ''))
    return app


def post(client, path, value):
    token = client.get('/api/bootstrap').json['csrfToken']
    return client.post(path, json=value, headers={'X-CSRF-Token': token})


def create(client):
    day = (now().date() + timedelta(days=1)).isoformat()
    result = post(client, '/api/bookings', {'date': day, 'time': '10:00', 'serviceIds': ['combo'], 'name': 'Cliente teste', 'phone': '11999998888', 'payment': 'local'})
    assert result.status_code == 201
    return result.json['booking']


def test_confirmed_booking_cancelled_by_customer_updates_admin_and_releases_slots(booking_app):
    customer, admin = booking_app.test_client(), booking_app.test_client()
    booking = create(customer)
    assert post(admin, '/api/login', {'email': 'admin@example.test', 'password': 'admin-password'}).status_code == 200
    assert post(admin, '/api/admin', {'action': 'approve', 'id': booking['id']}).status_code == 200
    assert admin.get('/api/admin').json['stats']['confirmed'] == 1
    result = post(customer, '/api/bookings/cancel', {'token': booking['token']})
    assert result.status_code == 200
    assert result.json['booking']['status'] == 'cancelled'
    dashboard = admin.get('/api/admin').json
    assert dashboard['stats']['confirmed'] == 0
    cancelled = next(item for item in dashboard['bookings'] if item['id'] == booking['id'])
    assert cancelled['status'] == 'cancelled'
    assert cancelled['cancellationNotificationStatus'] == 'unconfigured'
    assert dashboard['cancellationWhatsappConfigured'] is False
    slots = {slot['time']: slot['status'] for slot in customer.get('/api/availability', query_string={'date': booking['date']}).json['slots']}
    assert slots['10:00'] == slots['10:30'] == 'available'
    assert post(customer, '/api/bookings/cancel', {'token': booking['token']}).status_code == 200
    assert post(admin, '/api/admin', {'action': 'complete', 'id': booking['id'], 'paymentReceived': True}).status_code == 409


@pytest.mark.parametrize('status,paid', [('confirmed', 1), ('pending', 1), ('completed', 1), ('rejected', 0)])
def test_cannot_cancel_paid_or_finished_booking(booking_app, status, paid):
    client = booking_app.test_client()
    booking = create(client)
    with sqlite3.connect(booking_app.config['DATABASE']) as db:
        db.execute('UPDATE bookings SET status=?, paid=? WHERE id=?', (status, paid, booking['id']))
    assert post(client, '/api/bookings/cancel', {'token': booking['token']}).status_code == 409
    with sqlite3.connect(booking_app.config['DATABASE']) as db:
        assert db.execute('SELECT status,paid FROM bookings WHERE id=?', (booking['id'],)).fetchone() == (status, paid)


def test_approval_and_cancellation_remain_consistent_when_simultaneous(booking_app):
    customer, admin = booking_app.test_client(), booking_app.test_client()
    booking = create(customer)
    assert post(admin, '/api/login', {'email': 'admin@example.test', 'password': 'admin-password'}).status_code == 200
    barrier = Barrier(2)

    def execute(client, path, body):
        token = client.get('/api/bootstrap').json['csrfToken']
        barrier.wait(timeout=5)
        return client.post(path, json=body, headers={'X-CSRF-Token': token}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        cancel = executor.submit(execute, customer, '/api/bookings/cancel', {'token': booking['token']})
        approve = executor.submit(execute, admin, '/api/admin', {'action': 'approve', 'id': booking['id']})
        assert cancel.result() == 200
        assert approve.result() in (200, 409)
    dashboard = admin.get('/api/admin').json
    assert dashboard['stats']['confirmed'] == 0
    assert next(item for item in dashboard['bookings'] if item['id'] == booking['id'])['status'] == 'cancelled'
    with sqlite3.connect(booking_app.config['DATABASE']) as db:
        assert db.execute('SELECT COUNT(*) FROM booking_slots WHERE booking_id=?', (booking['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('accepted', [True, False])
def test_cancellation_whatsapp_is_sent_once_after_commit_and_result_is_recorded(booking_app, monkeypatch, accepted):
    booking_app.config.update(WHATSAPP_ACCESS_TOKEN='example-token', WHATSAPP_PHONE_NUMBER_ID='example-id', WHATSAPP_CANCELLATION_TEMPLATE_NAME='cancel_template')
    with sqlite3.connect(booking_app.config['DATABASE']) as db:
        db.execute("UPDATE settings SET whatsapp='5511988887777' WHERE id=1")
    customer, admin = booking_app.test_client(), booking_app.test_client()
    booking = create(customer)
    assert post(admin, '/api/login', {'email': 'admin@example.test', 'password': 'admin-password'}).status_code == 200
    assert post(admin, '/api/admin', {'action': 'approve', 'id': booking['id']}).status_code == 200
    calls = []

    def fake_provider(request, timeout):
        with sqlite3.connect(booking_app.config['DATABASE']) as db:
            assert db.execute('SELECT status FROM bookings WHERE id=?', (booking['id'],)).fetchone()[0] == 'cancelled'
            assert db.execute('SELECT COUNT(*) FROM booking_slots WHERE booking_id=?', (booking['id'],)).fetchone()[0] == 0
        payload = json.loads(request.data)
        calls.append(payload)
        if not accepted:
            raise URLError('offline test')
        return BytesIO(b'{"messages":[{"id":"provider-test-id"}]}')

    monkeypatch.setattr('app.urlopen', fake_provider)
    assert post(customer, '/api/bookings/cancel', {'token': booking['token']}).status_code == 200
    assert post(customer, '/api/bookings/cancel', {'token': booking['token']}).status_code == 200
    assert len(calls) == 1
    assert calls[0]['to'] == '5511988887777'
    assert calls[0]['template']['name'] == 'cancel_template'
    dashboard = admin.get('/api/admin').json
    assert dashboard['cancellationWhatsappConfigured'] is True
    record = next(item for item in dashboard['bookings'] if item['id'] == booking['id'])
    assert record['cancellationNotificationStatus'] == ('accepted' if accepted else 'failed')


def test_pending_cancellation_does_not_send_whatsapp(booking_app, monkeypatch):
    booking_app.config.update(WHATSAPP_ACCESS_TOKEN='test', WHATSAPP_PHONE_NUMBER_ID='test', WHATSAPP_CANCELLATION_TEMPLATE_NAME='cancel_template')
    with sqlite3.connect(booking_app.config['DATABASE']) as db:
        db.execute("UPDATE settings SET whatsapp='5511988887777' WHERE id=1")
    customer = booking_app.test_client()
    booking = create(customer)
    monkeypatch.setattr('app.urlopen', lambda *args, **kwargs: pytest.fail('unexpected external request'))
    assert post(customer, '/api/bookings/cancel', {'token': booking['token']}).status_code == 200
    with sqlite3.connect(booking_app.config['DATABASE']) as db:
        assert db.execute('SELECT COUNT(*) FROM booking_cancellation_notifications WHERE booking_id=?', (booking['id'],)).fetchone()[0] == 0
