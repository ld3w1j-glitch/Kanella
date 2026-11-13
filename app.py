"""Kanella: Flask + SQLite, contas locais e reservas com exclusão atômica."""
import functools
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from datetime import timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError
import uuid
from io import BytesIO
from decimal import Decimal, InvalidOperation
from PIL import Image, ImageOps, UnidentifiedImageError

import click
from flask import Flask, current_app, g, jsonify, render_template, request, session, Response
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from domain import SERVICES, PRODUCTS, TIMES, ValidationError, now, occupied_times, valid_date, valid_email, valid_password, valid_phone, valid_text
from migrations import allow_booking_cancellation
from pix import generate as generate_pix, validate_settings as validate_pix_settings


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=15, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=15000")
    return g.db


def transaction(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            result = function(*args, **kwargs)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
    return wrapped


def user_required(admin=False):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            if not g.user:
                raise ValidationError("Entre na sua conta para continuar.", 401)
            if admin and not g.user["is_admin"]:
                raise ValidationError("Área restrita ao administrador.", 403)
            return function(*args, **kwargs)
        return wrapped
    return decorate


def data():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValidationError("Dados inválidos. Envie um objeto JSON.")
    return value


def limit(action, maximum, seconds):
    if not current_app.config["RATE_LIMIT_ENABLED"]:
        return
    remote = request.remote_addr or 'unknown'
    if current_app.config.get('RAILWAY_PROXY'):
        try:
            remote = str(ipaddress.ip_address(request.headers.get('X-Real-IP','')))
        except ValueError:
            pass
    key = hashlib.sha256(f"{action}:{remote}".encode()).hexdigest()
    clock = time.time()
    db = get_db()
    db.execute("INSERT INTO rate_limits(key,count,reset_at) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN reset_at<? THEN 1 ELSE count+1 END,reset_at=CASE WHEN reset_at<? THEN excluded.reset_at ELSE reset_at END", (key, clock+seconds, clock, clock))
    if db.execute("SELECT count FROM rate_limits WHERE key=?", (key,)).fetchone()[0] > maximum:
        raise ValidationError("Muitas tentativas. Aguarde alguns minutos e tente novamente.", 429)


def public_user(row):
    return {"id": row["id"], "email": row["email"], "name": row["name"], "phone": row["phone"], "points": row["points"]} if row else None


def catalog(table):
    result = []
    kind = 'service' if table == 'services' else 'product'
    for row in get_db().execute(f"SELECT * FROM {table} WHERE NOT EXISTS (SELECT 1 FROM archived_catalog a WHERE a.kind=? AND a.item_id={table}.id) ORDER BY rowid", (kind,)):  # table is a code constant
        item = dict(row)
        item["price"] /= 100
        if table == 'products':
            image = get_db().execute('SELECT digest FROM product_images WHERE product_id=?', (item['id'],)).fetchone()
            item['imageUrl'] = f"/media/products/{item['id']}?v={image['digest']}" if image else None
        result.append(item)
    return result

def loyalty_rules():
    row = get_db().execute('SELECT * FROM loyalty_settings WHERE id=1').fetchone()
    return {'earnAmount': row['earn_amount']/100, 'pointsRequired': row['points_required'], 'discountPercent': row['discount_percent']}


def booking_json(row):
    result = dict(row)
    result["services"] = json.loads(row["services"])
    result["total"] = row["total"] / 100
    result["notificationStatus"] = result.pop("notification_status")
    result.pop("user_id", None)
    labels = {"pending": "Solicitação recebida; aguardando aprovação.", "confirmed": "Seu agendamento está confirmado!", "rejected": "A equipe não conseguiu aprovar este horário. Escolha outro horário.", "completed": "Atendimento concluído. Obrigado pela visita!", "cancelled": "Solicitação cancelada pelo cliente. O horário foi liberado."}
    date_text = "/".join(reversed(row["date"].split("-")))
    services = ", ".join(s["name"] for s in result["services"])
    pix_enabled = bool(get_db().execute('SELECT enabled FROM pix_settings WHERE id=1').fetchone()[0])
    payment = "Pagamento confirmado pela equipe." if row["paid"] else "Pagamento via Pix ou na barbearia, conforme combinado." if pix_enabled else "Pagamento na barbearia, no dia do atendimento."
    result["message"] = f"Olá, {row['name']}! Kanella Barber Shop: {labels[row['status']]}\nData: {date_text} às {row['time']}.\nServiço: {services}.\nTotal: R$ {result['total']:.2f}.\n{payment}"
    return result


def order_json(row):
    result = dict(row)
    result["items"] = json.loads(row["items"])
    for key in ("subtotal", "discount", "total"):
        result[key] /= 100
    return result


def whatsapp_ready():
    return all(current_app.config.get(key) for key in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_TEMPLATE_NAME"))


def cancellation_whatsapp_ready():
    return bool(get_db().execute("SELECT whatsapp FROM settings WHERE id=1").fetchone()[0]) and all(current_app.config.get(key) for key in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_CANCELLATION_TEMPLATE_NAME"))


def send_cancellation_notice(booking):
    """A provider acceptance is not evidence of delivery."""
    if not cancellation_whatsapp_ready():
        return "unconfigured"
    cfg = current_app.config
    phone = get_db().execute("SELECT whatsapp FROM settings WHERE id=1").fetchone()[0]
    services = ', '.join(item['name'] for item in booking['services'])
    day = '/'.join(reversed(booking['date'].split('-')))
    details = f"Agendamento confirmado cancelado: {booking['name']}, {booking['phone']}, {day} às {booking['time']}, {services}."
    text = ' '.join(details.split())
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "template", "template": {"name": cfg["WHATSAPP_CANCELLATION_TEMPLATE_NAME"], "language": {"code": "pt_BR"}, "components": [{"type": "body", "parameters": [{"type": "text", "text": text}]}]}}
    endpoint = f"https://graph.facebook.com/{cfg['WHATSAPP_API_VERSION']}/{cfg['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    req = Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['WHATSAPP_ACCESS_TOKEN']}"}, method="POST")
    try:
        with urlopen(req, timeout=8) as response:
            result = json.load(response)
        return "accepted" if result.get("messages", [{}])[0].get("id") else "failed"
    except (URLError, TimeoutError, ValueError, KeyError, IndexError):
        current_app.logger.warning("WhatsApp não aceitou o aviso de cancelamento.")
        return "failed"


def send_confirmation(booking):
    """Provider acceptance is not a delivery receipt. Manual fallback never claims sent."""
    if not whatsapp_ready():
        return "manual"
    cfg = current_app.config
    text = " ".join(booking["message"].split())
    payload = {"messaging_product": "whatsapp", "to": booking["phone"], "type": "template", "template": {"name": cfg["WHATSAPP_TEMPLATE_NAME"], "language": {"code": "pt_BR"}, "components": [{"type": "body", "parameters": [{"type": "text", "text": text}]}]}}
    endpoint = f"https://graph.facebook.com/{cfg['WHATSAPP_API_VERSION']}/{cfg['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    req = Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['WHATSAPP_ACCESS_TOKEN']}"}, method="POST")
    try:
        with urlopen(req, timeout=8) as response:
            result = json.load(response)
        return "accepted" if result.get("messages", [{}])[0].get("id") else "failed"
    except (URLError, TimeoutError, ValueError, KeyError, IndexError):
        current_app.logger.warning("WhatsApp não aceitou a confirmação; usar envio manual.")
        return "failed"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    instance = Path(app.instance_path)
    production = os.getenv('APP_ENV') == 'production'
    if production:
        volume = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '')
        secret = os.getenv('SECRET_KEY', '')
        if not volume or not os.getenv('RAILWAY_VOLUME_NAME') or not Path(volume).is_dir():
            raise RuntimeError('Produção requer um volume persistente montado no Railway.')
        if len(secret) < 32:
            raise RuntimeError('Produção requer SECRET_KEY própria com pelo menos 32 caracteres.')
        database = Path(volume) / 'kanella.sqlite3'
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    else:
        instance.mkdir(exist_ok=True)
        database = instance / 'kanella.sqlite3'
    app.config.from_mapping(DATABASE=str(database), SECRET_KEY=os.getenv('SECRET_KEY') or None, RAILWAY_PROXY=production, ADMIN_EMAIL=os.getenv("ADMIN_EMAIL", "ld3w1j@gmail.com").lower(), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=production or os.getenv("COOKIE_SECURE") == "1", PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=16384, RATE_LIMIT_ENABLED=True)
    for key in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_TEMPLATE_NAME", "WHATSAPP_CANCELLATION_TEMPLATE_NAME"):
        app.config[key] = os.getenv(key, "")
    app.config["WHATSAPP_API_VERSION"] = os.getenv("WHATSAPP_API_VERSION", "v23.0")
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        secret_path = instance / ".secret-key"
        if not secret_path.exists():
            try:
                with secret_path.open("x", encoding="utf-8") as handle:
                    handle.write(secrets.token_hex(32))
                secret_path.chmod(0o600)
            except FileExistsError:
                pass
        app.config["SECRET_KEY"] = secret_path.read_text(encoding="utf-8")

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript((Path(app.root_path) / "schema.sql").read_text(encoding="utf-8"))
        allow_booking_cancellation(db)
        db.executemany("INSERT OR IGNORE INTO services VALUES(?,?,?,?,?)", SERVICES)
        db.executemany("INSERT OR IGNORE INTO products VALUES(?,?,?,?,?,?)", PRODUCTS)

    @app.before_request
    def security():
        if request.endpoint == 'health':
            return None
        if request.endpoint == 'admin_product_update':
            request.max_content_length = 3 * 1024 * 1024
        session.setdefault("csrf", secrets.token_urlsafe(32))
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session.get("user_id"),)).fetchone() if session.get("user_id") else None
        if g.user and g.user["is_admin"]:
            password_version = hashlib.sha256(g.user["password_hash"].encode()).hexdigest()
            if not secrets.compare_digest(session.get("admin_password_version", ""), password_version):
                session.clear()
                session["csrf"] = secrets.token_urlsafe(32)
                g.user = None
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                raise ValidationError("Origem não autorizada.", 403)
            token = request.headers.get("X-CSRF-Token", "")
            if not secrets.compare_digest(token, session["csrf"]):
                raise ValidationError("Sessão expirada. Atualize a página e tente novamente.", 403)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-CSRF-Token"] = session.get("csrf", "")
        return response

    @app.errorhandler(ValidationError)
    def validation(error):
        return jsonify(error=error.message), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        if error.code == 413:
            return jsonify(error="Imagem ou solicitação muito grande. Escolha uma imagem menor que 3 MB."), 413
        return jsonify(error="Solicitação não encontrada ou inválida."), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception("Falha interna na operação")
        return jsonify(error="Não foi possível concluir a operação. Tente novamente."), 500

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get('/health')
    def health():
        get_db().execute('SELECT 1').fetchone()
        return jsonify(status='ok')

    @app.get("/api/bootstrap")
    def bootstrap():
        settings = dict(get_db().execute("SELECT * FROM settings WHERE id=1").fetchone())
        pix_enabled = bool(get_db().execute('SELECT enabled FROM pix_settings WHERE id=1').fetchone()[0])
        return jsonify(user=public_user(g.user), isAdmin=bool(g.user and g.user["is_admin"]), services=catalog("services"), products=catalog("products") if g.user else [], settings=settings, loyalty=loyalty_rules(), pixEnabled=pix_enabled, csrfToken=session["csrf"], today=now().date().isoformat())

    @app.post("/api/register")
    def register():
        limit("register", 8, 3600)
        value = data()
        email, password = valid_email(value.get("email")), valid_password(value.get("password"))
        name, phone = valid_text(value.get("name")), valid_phone(value.get("phone"))
        if email == app.config["ADMIN_EMAIL"]:
            raise ValidationError("Esse e-mail é reservado à administração. Use a conta criada pelo comando local.", 403)
        uid = str(uuid.uuid4())
        try:
            get_db().execute("INSERT INTO users(id,email,password_hash,name,phone) VALUES(?,?,?,?,?)", (uid,email,generate_password_hash(password),name,phone))
        except sqlite3.IntegrityError:
            raise ValidationError("Não foi possível cadastrar esse e-mail. Se já possui conta, entre com sua senha.", 409) from None
        session.clear()
        session.update(user_id=uid, csrf=secrets.token_urlsafe(32))
        session.permanent = True
        return jsonify(ok=True), 201

    @app.post("/api/login")
    def login():
        limit("login", 12, 900)
        value = data()
        email = valid_email(value.get("email"))
        password = value.get("password", "")
        if not isinstance(password, str) or len(password) > 128:
            raise ValidationError("E-mail ou senha incorretos.", 401)
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            raise ValidationError("E-mail ou senha incorretos.", 401)
        session.clear()
        session.update(user_id=user["id"], csrf=secrets.token_urlsafe(32))
        if user["is_admin"]:
            session["admin_password_version"] = hashlib.sha256(user["password_hash"].encode()).hexdigest()
        session.permanent = True
        return jsonify(ok=True)

    @app.post("/api/admin/password")
    @user_required(admin=True)
    def admin_password():
        limit("admin_password", 12, 900)
        value = data()
        current = value.get("currentPassword")
        if not isinstance(current, str) or len(current) > 128 or not check_password_hash(g.user["password_hash"], current):
            raise ValidationError("Senha atual incorreta.", 401)
        new_password = valid_password(value.get("newPassword"))
        password_hash = generate_password_hash(new_password)
        updated = get_db().execute("UPDATE users SET password_hash=? WHERE id=? AND password_hash=?", (password_hash, g.user["id"], g.user["password_hash"]))
        if updated.rowcount != 1:
            raise ValidationError("A senha foi alterada em outra sessão. Entre novamente.", 409)
        session["admin_password_version"] = hashlib.sha256(password_hash.encode()).hexdigest()
        session["csrf"] = secrets.token_urlsafe(32)
        return jsonify(ok=True)

    @app.post("/api/logout")
    def logout():
        session.clear()
        session["csrf"] = secrets.token_urlsafe(32)
        return jsonify(ok=True)

    @app.get("/api/availability")
    def availability():
        day = request.args.get("date")
        valid_date(day)
        taken = {r[0] for r in get_db().execute("SELECT time FROM booking_slots WHERE date=?", (day,))}
        clock = now()
        return jsonify(slots=[{"time": slot, "status": "reserved" if slot in taken else "past" if day == clock.date().isoformat() and slot <= clock.strftime("%H:%M") else "available"} for slot in TIMES])

    @app.get("/api/bookings")
    def bookings_get():
        token = request.args.get("token")
        if token is not None:
            row = get_db().execute("SELECT * FROM bookings WHERE token=?", (token[:100],)).fetchone()
            if not row:
                raise ValidationError("Reserva não encontrada.", 404)
            return jsonify(booking=booking_json(row))
        if not g.user:
            raise ValidationError("Entre para ver seus agendamentos.", 401)
        rows = get_db().execute("SELECT * FROM bookings WHERE user_id=? ORDER BY date DESC,time DESC", (g.user["id"],))
        return jsonify(bookings=[booking_json(row) for row in rows])

    @app.post("/api/bookings")
    def bookings_post():
        limit("booking", 12, 3600)
        return create_booking(data())

    @app.post("/api/bookings/cancel")
    def bookings_cancel():
        booking, notify = cancel_booking(data())
        if notify:
            try:
                status = send_cancellation_notice(booking)
            except Exception:
                app.logger.warning("Falha ao enviar aviso de cancelamento; reserva permanece cancelada.")
                status = "failed"
            try:
                get_db().execute("UPDATE booking_cancellation_notifications SET status=? WHERE booking_id=?", (status, booking['id']))
            except sqlite3.Error:
                app.logger.warning("Não foi possível registrar o resultado do aviso de cancelamento.")
        return jsonify(booking=booking)

    @transaction
    def cancel_booking(value):
        token = value.get("token")
        if not isinstance(token, str) or not 1 <= len(token) <= 100:
            raise ValidationError("Link de reserva inválido.", 400)
        db = get_db()
        row = db.execute("SELECT * FROM bookings WHERE token=?", (token,)).fetchone()
        if not row:
            raise ValidationError("Reserva não encontrada.", 404)
        if row["status"] == "cancelled":
            return booking_json(row), False
        if row["paid"]:
            raise ValidationError("Para cancelar um agendamento com pagamento registrado, entre em contato com a barbearia.", 409)
        if row["status"] not in ("pending", "confirmed"):
            raise ValidationError("Este agendamento não pode mais ser cancelado. Atualize o status da reserva.", 409)
        notify = row["status"] == "confirmed"
        db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (row["id"],))
        db.execute("DELETE FROM booking_slots WHERE booking_id=?", (row["id"],))
        if notify:
            db.execute("INSERT INTO booking_cancellation_notifications(booking_id,status) VALUES(?,'pending')", (row["id"],))
        return booking_json(db.execute("SELECT * FROM bookings WHERE id=?", (row["id"],)).fetchone()), notify

    @transaction
    def create_booking(value):
        name, phone = valid_text(value.get("name")), valid_phone(value.get("phone"))
        if value.get("payment") != "local":
            raise ValidationError("O pagamento é feito na barbearia.")
        ids = value.get("serviceIds")
        if not isinstance(ids, list) or not ids or len(ids) > 5 or any(not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids):
            raise ValidationError("Selecione serviços válidos.")
        # Combos include the other services; do not charge the same care twice.
        if ("premium" in ids and len(ids)>1) or ("combo" in ids and any(i in ids for i in ("corte","barba"))):
            raise ValidationError("O combo já inclui esses serviços. Selecione apenas o combo desejado.")
        selected = []
        for sid in ids:
            item = get_db().execute("SELECT * FROM services WHERE id=? AND NOT EXISTS (SELECT 1 FROM archived_catalog WHERE kind='service' AND item_id=services.id)", (sid,)).fetchone()
            if not item:
                raise ValidationError("Serviço inválido.")
            selected.append(dict(item))
        duration, total = sum(s["duration"] for s in selected), sum(s["price"] for s in selected)
        day, start = value.get("date"), value.get("time")
        times = occupied_times(day, start, duration)
        for item in selected:
            item["price"] /= 100
        bid, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        db = get_db()
        try:
            db.execute("INSERT INTO bookings(id,token,user_id,date,time,name,phone,services,total,duration) VALUES(?,?,?,?,?,?,?,?,?,?)", (bid,token,g.user["id"] if g.user else None,day,start,name,phone,json.dumps(selected,ensure_ascii=False),total,duration))
            db.executemany("INSERT INTO booking_slots VALUES(?,?,?)", [(day,t,bid) for t in times])
        except sqlite3.IntegrityError:
            raise ValidationError("Esse horário acabou de ser reservado. Escolha outro horário.", 409) from None
        return jsonify(booking=booking_json(db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())), 201

    @app.get("/api/store")
    @user_required()
    def store():
        return jsonify(products=catalog("products"), orders=[order_json(r) for r in get_db().execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (g.user["id"],))])

    def pix_for(row, prefix):
        settings = get_db().execute('SELECT * FROM pix_settings WHERE id=1').fetchone()
        if not settings['enabled']:
            raise ValidationError('Pix não configurado.',404)
        reference = prefix + row['id'].replace('-', '')[:24]
        return jsonify(generate_pix(settings['pix_key'],settings['name'],settings['city'],row['total'],reference))

    @app.get('/api/pix/booking')
    def pix_booking():
        token = request.args.get('token','')
        if not 1 <= len(token) <= 100:
            raise ValidationError('Reserva não encontrada.',404)
        row = get_db().execute("SELECT * FROM bookings WHERE token=? AND status IN ('pending','confirmed') AND paid=0",(token,)).fetchone()
        if not row:
            raise ValidationError('Reserva não encontrada.',404)
        return pix_for(row,'A')

    @app.get('/api/pix/order/<order_id>')
    @user_required()
    def pix_order(order_id):
        row = get_db().execute("SELECT * FROM orders WHERE id=? AND user_id=? AND status='pending'",(order_id,g.user['id'])).fetchone()
        if not row or row['total'] <= 0:
            raise ValidationError('Pedido não encontrado ou sem valor a pagar.',404)
        return pix_for(row,'P')

    @app.get('/media/products/<product_id>')
    def product_image(product_id):
        row = get_db().execute('SELECT image FROM product_images WHERE product_id=?', (product_id,)).fetchone()
        if not row:
            raise ValidationError('Imagem não encontrada.', 404)
        response = Response(row['image'], mimetype='image/png')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.post('/api/admin/products/<product_id>')
    @user_required(admin=True)
    def admin_product_update(product_id):
        name = valid_text(request.form.get('name'), maximum=100)
        try:
            price = Decimal(request.form.get('price', ''))
            stock_text = request.form.get('stock', '')
            if not price.is_finite() or price <= 0 or price > 10000 or price.as_tuple().exponent < -2 or not stock_text.isascii() or not stock_text.isdecimal() or not 0 <= int(stock_text) <= 10000:
                raise ValueError()
            cents, stock = int(price * 100), int(stock_text)
        except (InvalidOperation, ValueError, OverflowError):
            raise ValidationError('Preço ou estoque inválido.') from None
        upload = request.files.get('image')
        remove = request.form.get('removeImage') == '1'
        if upload and upload.filename and remove:
            raise ValidationError('Escolha uma nova imagem ou remova a atual.')
        raw = None
        if upload and upload.filename:
            try:
                with Image.open(upload.stream) as im:
                    if im.format not in ('JPEG','PNG','WEBP') or im.width * im.height > 16000000 or getattr(im, 'n_frames', 1) != 1:
                        raise ValueError()
                    im = ImageOps.exif_transpose(im)
                    im.thumbnail((1200,1200))
                    im = im.convert('RGBA' if 'A' in im.getbands() else 'RGB')
                    im.info.clear()
                    output = BytesIO()
                    im.save(output, format='PNG', optimize=True)
                    raw = output.getvalue()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                raise ValidationError('Imagem inválida. Use JPG, PNG ou WebP de até 16 megapixels.') from None
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        try:
            if not db.execute('UPDATE products SET name=?,price=?,stock=? WHERE id=?', (name,cents,stock,product_id)).rowcount:
                raise ValidationError('Produto não encontrado.',404)
            if raw is not None:
                db.execute('INSERT INTO product_images(product_id,image,digest) VALUES(?,?,?) ON CONFLICT(product_id) DO UPDATE SET image=excluded.image,digest=excluded.digest', (product_id,raw,hashlib.sha256(raw).hexdigest()))
            elif remove:
                db.execute('DELETE FROM product_images WHERE product_id=?', (product_id,))
            db.commit()
        except Exception:
            db.rollback()
            raise
        return jsonify(ok=True)

    @app.post("/api/orders")
    @user_required()
    @transaction
    def order_create():
        value, db = data(), get_db()
        items, redeem = value.get("items"), value.get("redeem", False)
        if not isinstance(items,list) or not 1 <= len(items) <= 20 or type(redeem) is not bool:
            raise ValidationError("Carrinho inválido.")
        selected, seen, subtotal = [], set(), 0
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get("productId"),str) or type(item.get("quantity")) is not int or not 1 <= item["quantity"] <= 20:
                raise ValidationError("Quantidade ou produto inválido.")
            product = db.execute("SELECT * FROM products WHERE id=? AND NOT EXISTS (SELECT 1 FROM archived_catalog WHERE kind='product' AND item_id=products.id)", (item["productId"],)).fetchone()
            if not product or product["id"] in seen or product["stock"] < item["quantity"]:
                raise ValidationError("Produto sem estoque suficiente ou repetido no carrinho.", 409)
            seen.add(product["id"])
            selected.append({"productId":product["id"], "name":product["name"], "price":product["price"]/100, "quantity":item["quantity"]})
            subtotal += product["price"] * item["quantity"]
            db.execute("UPDATE products SET stock=stock-? WHERE id=?", (item["quantity"],product["id"]))
        rules = loyalty_rules()
        discount = (subtotal * rules['discountPercent'] + 50) // 100 if redeem else 0
        points = rules['pointsRequired'] if redeem else 0
        if not db.execute("UPDATE users SET points=points-? WHERE id=? AND points>=?", (points,g.user["id"],points)).rowcount:
            raise ValidationError(f"Você precisa de {points} pontos para esse desconto.", 409)
        oid = str(uuid.uuid4())
        db.execute("INSERT INTO orders(id,user_id,items,subtotal,discount,total,points_spent) VALUES(?,?,?,?,?,?,?)", (oid,g.user["id"],json.dumps(selected,ensure_ascii=False),subtotal,discount,subtotal-discount,points))
        return jsonify(order=order_json(db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())), 201

    @app.get("/api/admin")
    @user_required(admin=True)
    def admin_get():
        db = get_db()
        bookings = [booking_json(r) for r in db.execute("SELECT * FROM bookings ORDER BY date DESC,time DESC")]
        cancellation_notifications = dict(db.execute("SELECT booking_id,status FROM booking_cancellation_notifications"))
        for booking in bookings:
            booking['cancellationNotificationStatus'] = cancellation_notifications.get(booking['id'])
        orders = [order_json(r) for r in db.execute("SELECT o.*,u.name,u.phone FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.created_at DESC")]
        archived = [dict(row) for row in db.execute("SELECT 'service' AS kind,s.id,s.name FROM services s JOIN archived_catalog a ON a.kind='service' AND a.item_id=s.id UNION ALL SELECT 'product' AS kind,p.id,p.name FROM products p JOIN archived_catalog a ON a.kind='product' AND a.item_id=p.id")]
        pix = dict(db.execute('SELECT enabled,pix_key,name,city FROM pix_settings WHERE id=1').fetchone())
        return jsonify(bookings=bookings,orders=orders,settings=dict(db.execute("SELECT * FROM settings WHERE id=1").fetchone()),pixSettings=pix,services=catalog("services"),products=catalog("products"),archived=archived,whatsappConfigured=whatsapp_ready(),cancellationWhatsappConfigured=cancellation_whatsapp_ready(),stats={"pending":sum(b["status"]=="pending" for b in bookings),"confirmed":sum(b["status"]=="confirmed" for b in bookings),"revenue":sum(b["total"] for b in bookings if b["paid"])+sum(o["total"] for o in orders if o["status"]=="pickedup"),"customers":db.execute("SELECT COUNT(DISTINCT phone) FROM bookings WHERE status NOT IN ('rejected','cancelled')").fetchone()[0]})

    @app.post("/api/admin")
    @user_required(admin=True)
    def admin_post():
        value = data()
        result = admin_action(value)
        if value.get("action") in ("approve", "retryNotification"):
            booking = result["booking"]
            try:
                status = send_confirmation(booking)
            except Exception:
                app.logger.warning("Falha no provedor de notificações; aprovação preservada.")
                status = "failed"
            try:
                get_db().execute("UPDATE bookings SET notification_status=? WHERE id=?", (status, booking["id"]))
            except sqlite3.Error:
                app.logger.warning("Não foi possível persistir o status da notificação.")
                status = "failed"
            booking["notificationStatus"] = status
        return jsonify(result)

    @transaction
    def admin_action(value):
        db, action = get_db(), value.get("action")
        if action == 'pixSettings':
            enabled = value.get('enabled')
            if type(enabled) is not bool:
                raise ValidationError('Configuração Pix inválida.')
            key, name, city = value.get('key',''), value.get('name',''), value.get('city','')
            if not all(isinstance(item,str) for item in (key,name,city)):
                raise ValidationError('Configuração Pix inválida.')
            if enabled or key or name or city:
                key, name, city = validate_pix_settings(key,name,city)
            db.execute('UPDATE pix_settings SET enabled=?,pix_key=?,name=?,city=? WHERE id=1', (int(enabled),key,name,city))
            return {'ok':True}
        if action in ('catalogCreate','catalogArchive','catalogRestore'):
            kind = value.get('kind')
            table = 'services' if kind == 'service' else 'products' if kind == 'product' else None
            if table is None:
                raise ValidationError('Catálogo inválido.')
            if action == 'catalogCreate':
                name = valid_text(value.get('name'), maximum=100)
                description = valid_text(value.get('description'), label='Descrição', maximum=220)
                price = value.get('price')
                try:
                    amount = Decimal(str(price)) if type(price) in (int,float) else Decimal('NaN')
                    valid_price = amount.is_finite() and Decimal('0.01') <= amount <= Decimal('10000') and amount * 100 == (amount * 100).to_integral_value()
                except InvalidOperation:
                    valid_price = False
                if not valid_price:
                    raise ValidationError('Preço inválido.')
                item_id = uuid.uuid4().hex
                if kind == 'service':
                    duration = value.get('duration')
                    if type(duration) is not int or duration not in range(30, 181, 30):
                        raise ValidationError('Duração deve ser de 30 a 180 minutos, em blocos de 30 minutos.')
                    db.execute('INSERT INTO services(id,name,description,price,duration) VALUES(?,?,?,?,?)', (item_id,name,description,int(amount*100),duration))
                else:
                    category = valid_text(value.get('category'), label='Categoria', maximum=60)
                    stock = value.get('stock')
                    if type(stock) is not int or not 0 <= stock <= 10000:
                        raise ValidationError('Estoque inválido.')
                    db.execute('INSERT INTO products(id,name,description,price,category,stock) VALUES(?,?,?,?,?,?)', (item_id,name,description,int(amount*100),category,stock))
                return {'ok':True,'id':item_id}
            item_id = value.get('id')
            if not isinstance(item_id,str) or not db.execute(f'SELECT 1 FROM {table} WHERE id=?', (item_id,)).fetchone():
                raise ValidationError('Item não encontrado.', 404)
            if action == 'catalogArchive':
                db.execute('INSERT OR IGNORE INTO archived_catalog(kind,item_id) VALUES(?,?)', (kind,item_id))
            else:
                db.execute('DELETE FROM archived_catalog WHERE kind=? AND item_id=?', (kind,item_id))
            return {'ok':True}
        if action == "settings":
            settings = value.get("settings")
            if not isinstance(settings,dict):
                raise ValidationError("Configuração inválida.")
            phone = valid_phone(settings.get("whatsapp")) if settings.get("whatsapp") else ""
            db.execute("UPDATE settings SET whatsapp=? WHERE id=1", (phone,))
            return {"ok": True}
        if action == 'loyalty':
            amount, points, discount = value.get('earnAmount'), value.get('pointsRequired'), value.get('discountPercent')
            try:
                money_amount = Decimal(str(amount)) if type(amount) in (int,float) else Decimal('NaN')
                valid_amount = money_amount.is_finite() and Decimal('0.01') <= money_amount <= Decimal('10000') and money_amount * 100 == (money_amount * 100).to_integral_value()
            except InvalidOperation:
                valid_amount = False
            if not valid_amount or type(points) is not int or not 1 <= points <= 100000 or type(discount) is not int or not 1 <= discount <= 100:
                raise ValidationError('Regras de fidelidade inválidas.')
            db.execute('UPDATE loyalty_settings SET earn_amount=?,points_required=?,discount_percent=? WHERE id=1', (int(money_amount*100),points,discount))
            return {'ok':True}
        if action == "catalog":
            kind = value.get("kind")
            table = "services" if kind == "service" else "products" if kind == "product" else None
            if table is None:
                raise ValidationError("Catálogo inválido.")
            price = value.get("price")
            if type(price) not in (int,float) or not 0 < price <= 10000:
                raise ValidationError("Preço inválido.")
            if not db.execute(f"UPDATE {table} SET price=? WHERE id=?", (round(price*100),value.get("id"))).rowcount:
                raise ValidationError("Item não encontrado.",404)
            if kind == "product":
                stock = value.get("stock")
                if type(stock) is not int or not 0 <= stock <= 10000:
                    raise ValidationError("Estoque inválido.")
                db.execute("UPDATE products SET stock=? WHERE id=?", (stock,value["id"]))
            return {"ok": True}
        if action in ("completeOrder","cancelOrder"):
            row = db.execute("SELECT * FROM orders WHERE id=?", (value.get("id"),)).fetchone()
            if not row or row["status"] != "pending":
                raise ValidationError("Pedido inexistente ou já finalizado.",409)
            status = "pickedup" if action == "completeOrder" else "cancelled"
            db.execute("UPDATE orders SET status=? WHERE id=?", (status,row["id"]))
            if status == "cancelled":
                for item in json.loads(row["items"]):
                    db.execute("UPDATE products SET stock=stock+? WHERE id=?", (item["quantity"],item["productId"]))
                db.execute("UPDATE users SET points=points+? WHERE id=?", (row["points_spent"],row["user_id"]))
            return {"ok": True}
        row = db.execute("SELECT * FROM bookings WHERE id=?", (value.get("id"),)).fetchone()
        if not row:
            raise ValidationError("Agendamento não encontrado.",404)
        transitions = {"approve":("pending","confirmed"),"reject":("pending","rejected"),"complete":("confirmed","completed")}
        if action == "retryNotification" and row["status"] == "confirmed":
            return {"booking":booking_json(row)}
        if action not in transitions or row["status"] != transitions[action][0]:
            raise ValidationError("Essa alteração não é permitida para o status atual.",409)
        status = transitions[action][1]
        if action == "complete":
            start = f"{row['date']} {row['time']}"
            if start > now().strftime("%Y-%m-%d %H:%M"):
                raise ValidationError("Conclua o atendimento somente a partir do horário agendado.")
            if value.get("paymentReceived") is not True:
                raise ValidationError("Confirme o recebimento do pagamento antes de concluir.")
            earn_amount = db.execute('SELECT earn_amount FROM loyalty_settings WHERE id=1').fetchone()[0]
            db.execute("UPDATE users SET points=points+? WHERE id=?", (row["total"]//earn_amount,row["user_id"]))
        db.execute("UPDATE bookings SET status=?,paid=? WHERE id=?", (status,1 if action=="complete" else 0,row["id"]))
        if action == "reject":
            db.execute("DELETE FROM booking_slots WHERE booking_id=?", (row["id"],))
        return {"booking":booking_json(db.execute("SELECT * FROM bookings WHERE id=?",(row["id"],)).fetchone())}

    @app.cli.command("create-admin")
    @click.option("--email", default=None, help="Deve coincidir com ADMIN_EMAIL.")
    @click.password_option(confirmation_prompt=True)
    def create_admin(email, password):
        """Cria ou redefine a senha administrativa, sem senha padrão."""
        try:
            email = valid_email(email or app.config["ADMIN_EMAIL"])
            valid_password(password)
            if email != app.config["ADMIN_EMAIL"]:
                raise ValidationError("O e-mail deve coincidir com ADMIN_EMAIL.")
        except ValidationError as error:
            raise click.ClickException(error.message) from None
        get_db().execute("INSERT INTO users(id,email,password_hash,name,phone,is_admin) VALUES(?,?,?,?,?,1) ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash,is_admin=1", (str(uuid.uuid4()),email,generate_password_hash(password),"Administrador Kanella",""))
        click.echo(f"Administrador {email} configurado. Entre pela área administrativa.")

    return app
