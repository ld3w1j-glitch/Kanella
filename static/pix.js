import {escape as e} from './common.js';

export function pixPanel(pix){
 if(!pix)return '';
 return `<section class="pix-panel" aria-label="Pagamento Pix"><h3>Pague com Pix</h3><p>Leia o QR Code no aplicativo do banco ou copie o código. Confira o recebedor e o valor antes de pagar.</p><img class="pix-qr" src="data:image/png;base64,${e(pix.qrPng)}" alt="QR Code para pagamento Pix" width="240" height="240"><label class="field">Pix copia e cola<textarea readonly rows="3">${e(pix.copyPaste)}</textarea></label><button type="button" class="secondary" data-action="pix-copy">Copiar código Pix</button><p class="info-note">A barbearia confere o pagamento manualmente. O QR Code não confirma pagamento nem altera a reserva ou o pedido.</p></section>`;
}
