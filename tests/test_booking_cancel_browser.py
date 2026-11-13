"""Fluxo real de cancelamento em navegadores e banco isolados."""

import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from app import create_app, get_db


def test_confirmed_booking_cancelled_by_customer_updates_manager(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'booking.sqlite'), 'SECRET_KEY': 'browser-test', 'RATE_LIMIT_ENABLED': False})
    with app.app_context():
        get_db().execute('INSERT INTO users(id,email,password_hash,name,phone,is_admin) VALUES(?,?,?,?,?,1)', ('admin', 'admin@example.test', generate_password_hash('admin-test-password'), 'Admin', ''))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
            browser = p.chromium.launch(headless=True, executable_path=str(chrome) if chrome.exists() else None)
            customer = browser.new_context(viewport={'width': 1440, 'height': 1000}).new_page()
            manager = browser.new_context(viewport={'width': 1440, 'height': 1000}).new_page()
            customer.on('dialog', lambda dialog: dialog.accept())
            url = f'http://127.0.0.1:{server.server_port}'
            customer.goto(url)
            customer.locator('.date-option').nth(1).click()
            customer.get_by_role('button', name='09:00, disponível', exact=True).click()
            customer.get_by_role('button', name='Escolher serviço').click()
            customer.locator('[data-action="service"][data-id="corte"]').click()
            customer.get_by_role('button', name='Continuar', exact=True).click()
            customer.get_by_label('Seu nome').fill('Cliente cancelamento')
            customer.get_by_label('Celular com WhatsApp').fill('11977776666')
            customer.get_by_role('checkbox').check()
            customer.get_by_role('button', name='Solicitar agendamento').click()
            expect(customer.get_by_role('heading', name='Solicitação recebida!')).to_be_visible()

            manager.goto(url + '/#admin')
            manager.locator('input[name="email"]').fill('admin@example.test')
            manager.locator('input[name="password"]').fill('admin-test-password')
            manager.locator('form[data-form="login"] button[type="submit"]').click()
            manager.get_by_role('button', name='Aprovar reserva').click()
            manager.locator('[data-action="filter"][data-filter="confirmed"]').click()
            expect(manager.locator('.admin-bookings')).to_contain_text('Cliente cancelamento')

            customer.locator('[data-action="refresh-booking"]').click()
            expect(customer.locator('.receipt .badge')).to_have_text('Confirmado')
            customer.locator('[data-action="cancel-booking"]').click()
            expect(customer.locator('.receipt .badge')).to_have_text('Cancelado')
            expect(manager.locator('.admin-bookings')).to_have_count(0, timeout=45000)
            manager.locator('[data-action="filter"][data-filter="cancelled"]').click()
            expect(manager.locator('.admin-bookings')).to_contain_text('Cliente cancelamento')
            expect(manager.locator('.admin-bookings .badge')).to_have_text('Cancelado')
            browser.close()
    finally:
        server.shutdown()
        thread.join()
