import {escape as e,icon,money} from './common.js';

export function bookingNotification(booking,phone,pixEnabled=false) {
  if (booking.status !== 'pending') return '';
  const destination = String(phone || '').replace(/\D/g,'');
  if (!/^55\d{10,11}$/.test(destination)) {
    return `<div class="booking-notification"><button class="primary" disabled>${icon('message')} Avisar barbearia pelo WhatsApp</button><p class="info-note">O WhatsApp da barbearia ainda não está disponível. Sua solicitação já está registrada para análise da equipe.</p></div>`;
  }
  const message = [
    'Olá, Kanella! Fiz uma solicitação de agendamento pelo aplicativo.',
    `Nome: ${booking.name}`,
    `Celular: ${booking.phone}`,
    `Data: ${booking.date.split('-').reverse().join('/')}`,
    `Horário: ${booking.time} (Brasília)`,
    `Serviço: ${booking.services.map(service=>service.name).join(' + ')}`,
    `Total: ${money(booking.total)}`,
    pixEnabled?'Pagamento por Pix ou na barbearia.':'Pagamento na barbearia.',
    `Protocolo: ${booking.id.slice(0,8).toUpperCase()}`,
    'Aguardo a aprovação da minha reserva. Obrigado!'
  ].join('\n');
  const url = `https://wa.me/${destination}?text=${encodeURIComponent(message)}`;
  return `<div class="booking-notification"><a class="primary" href="${e(url)}" target="_blank" rel="noopener noreferrer" aria-describedby="booking-whatsapp-help">${icon('message')} Avisar barbearia pelo WhatsApp ${icon('arrow')}</a><p class="info-note" id="booking-whatsapp-help">O WhatsApp abrirá com a mensagem pronta. Toque em enviar para avisar a barbearia. Sua reserva continua aguardando aprovação.</p></div>`;
}
