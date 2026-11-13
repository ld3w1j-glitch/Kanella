"""Regras independentes de HTTP. Valores monetários internos em centavos."""
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
TIMES = [f"{hour:02}:{minute:02}" for hour in range(9, 19) if hour != 12 for minute in (0, 30)]
SERVICES = [
    ("corte", "Corte personalizado", "Do clássico ao degradê, com acabamento na navalha.", 4500, 30),
    ("barba", "Barba & cuidado", "Desenho, alinhamento e finalização para uma barba de respeito.", 3500, 30),
    ("sobrancelha", "Sobrancelha", "Limpeza e alinhamento, preservando seu desenho natural.", 2000, 30),
    ("combo", "Combo corte + barba", "Seu visual completo: corte personalizado e barba alinhada.", 7000, 60),
    ("premium", "Experiência Kanella", "Corte, barba e sobrancelha. Cuidado em cada detalhe.", 8500, 60),
]
PRODUCTS = [
    ("pomada", "Pomada matte", "Fixação firme e acabamento seco. 80 g.", 4500, "Cabelo", 20),
    ("oleo", "Óleo para barba", "Maciez, hidratação e aquele toque de cuidado. 30 ml.", 5500, "Barba", 15),
    ("shampoo", "Shampoo diário", "Limpeza equilibrada para cabelo e barba. 250 ml.", 3500, "Cuidado", 20),
    ("pente", "Pente de madeira", "Seu aliado para alinhar o cabelo e a barba.", 2500, "Acessórios", 15),
]

class ValidationError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
        super().__init__(message)

def now():
    return datetime.now(TZ)

def valid_text(value, label="Nome", maximum=100):
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= maximum or re.search(r"[\x00-\x1f\x7f]", value):
        raise ValidationError(f"{label} inválido.")
    return value.strip()

def valid_phone(value):
    if not isinstance(value, str) or len(value) > 24 or not re.fullmatch(r"[+\d() .-]+", value):
        raise ValidationError("Informe um celular válido com DDD.")
    digits = re.sub(r"\D", "", value)
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if not re.fullmatch(r"[1-9]\d{9,10}", digits):
        raise ValidationError("Informe um celular válido com DDD.")
    return "55" + digits

def valid_email(value):
    if not isinstance(value, str) or len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValidationError("Informe um e-mail válido.")
    return value.strip().lower()

def valid_password(value):
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        raise ValidationError("A senha deve ter entre 10 e 128 caracteres.")
    return value

def valid_date(value, clock=None):
    clock = clock or now()
    try:
        day = date.fromisoformat(value)
        if value != day.isoformat():
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Data inválida.") from None
    if not clock.date() <= day <= clock.date() + timedelta(days=30):
        raise ValidationError("Escolha uma data entre hoje e os próximos 30 dias.")
    return day

def occupied_times(day, time, duration, clock=None):
    clock = clock or now()
    parsed = valid_date(day, clock)
    if time not in TIMES or type(duration) is not int or duration < 30 or duration % 30:
        raise ValidationError("Horário ou duração inválidos.")
    if parsed == clock.date() and time <= clock.strftime("%H:%M"):
        raise ValidationError("Esse horário já passou. Escolha outro.")
    start = int(time[:2]) * 60 + int(time[3:])
    result = [f"{m // 60:02}:{m % 60:02}" for m in range(start, start + duration, 30)]
    if any(slot not in TIMES for slot in result):
        raise ValidationError("O serviço ultrapassa o expediente ou o intervalo das 12h às 13h.")
    return result
