import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from app import create_app, get_db


def test_password_change_in_browser(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'browser.sqlite'), 'SECRET_KEY': 'browser-test', 'RATE_LIMIT_ENABLED': False})
    with app.app_context():
        get_db().execute('INSERT INTO users(id,email,password_hash,name,phone,is_admin) VALUES(?,?,?,?,?,1)', ('admin', 'admin@example.test', generate_password_hash('original-password'), 'Admin', ''))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
            browser = p.chromium.launch(headless=True, executable_path=str(chrome) if chrome.exists() else None)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            url = f'http://127.0.0.1:{server.server_port}'
            page.goto(url)
            assert page.locator('#navigation a[href="#admin"]').count() == 0
            page.goto(url + '/#admin')
            page.locator('input[name="email"]').fill('admin@example.test')
            page.locator('input[name="password"]').fill('original-password')
            page.locator('form[data-form="login"] button[type="submit"]').click()
            page.locator('[data-action="admin-section"][data-section="settings"]').click()
            form = page.locator('[data-form="admin-password"]')
            form.locator('[name="currentPassword"]').fill('original-password')
            form.locator('[name="newPassword"]').fill('new-browser-password')
            form.locator('[name="confirmPassword"]').fill('new-browser-password')
            with page.expect_response(lambda response: '/api/admin/password' in response.url and response.request.method == 'POST') as response:
                form.locator('button[type="submit"]').click()
            assert response.value.status == 200
            expect(page.locator('#toast')).to_be_visible()
            with page.expect_response(lambda response: '/api/logout' in response.url):
                page.locator('[data-action="logout"]').click()
            expect(page.locator('[data-action="logout"]')).to_have_count(0)
            page.goto(url)
            page.goto(url + '/#admin')
            page.locator('input[name="email"]').fill('admin@example.test')
            page.locator('input[name="password"]').fill('new-browser-password')
            page.locator('form[data-form="login"] button[type="submit"]').click()
            expect(page.locator('[data-action="admin-section"][data-section="settings"]')).to_be_visible()
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        thread.join()
