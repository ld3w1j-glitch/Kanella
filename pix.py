"""BR Code estático Pix; não consulta nem confirma pagamentos.

Referência: Manual de Padrões para Iniciação do Pix, Banco Central,
seção 2.6.3 (consultado em 13/11/2026).
"""
import base64
import binascii
import io
import re
import unicodedata
import qrcode
from domain import ValidationError


def validate_settings(key, name, city):
    if not isinstance(key, str) or not isinstance(name, str) or not isinstance(city, str):
        raise ValidationError('Informe chave, recebedor e cidade do Pix.')
    key = key.strip()
    key_patterns = (r'[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', r'\+[1-9][0-9]{9,14}', r'[0-9]{11}|[0-9]{14}', r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
    if not key.isascii() or len(key) > 77 or not any(re.fullmatch(pattern, key) for pattern in key_patterns):
        raise ValidationError('Informe uma chave Pix válida: e-mail, CPF/CNPJ, telefone com +55 ou chave aleatória.')
    def field(value, limit):
        value = unicodedata.normalize('NFKD', value.strip()).encode('ascii','ignore').decode('ascii')
        if not 1 <= len(value) <= limit or not re.fullmatch(r"[A-Za-z0-9 .,'-]+", value):
            raise ValidationError('Informe nome e cidade válidos para o Pix (até 25 e 15 caracteres).')
        return value
    return key, field(name,25), field(city,15)


def payload(key, name, city, cents, txid):
    def tlv(tag, value):
        if len(value.encode('utf-8')) > 99:
            raise ValueError('Campo Pix muito longo')
        return f'{tag}{len(value.encode("utf-8")):02d}{value}'
    account = tlv('00','br.gov.bcb.pix') + tlv('01',key)
    value = tlv('00','01') + tlv('26',account) + tlv('52','0000') + tlv('53','986')
    if cents is not None:
        value += tlv('54',f'{cents // 100}.{cents % 100:02d}')
    value += tlv('58','BR') + tlv('59',name) + tlv('60',city) + tlv('62',tlv('05',txid)) + '6304'
    return value + f'{binascii.crc_hqx(value.encode("utf-8"), 0xffff):04X}'


def generate(key, name, city, cents, reference):
    code = payload(key, name, city, cents, reference)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(code)
    qr.make(fit=True)
    output = io.BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(output, format='PNG')
    return {'copyPaste':code, 'qrPng':base64.b64encode(output.getvalue()).decode('ascii')}
