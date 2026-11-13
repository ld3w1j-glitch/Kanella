let csrf = '';
export const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export const icon = name => `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${name}"/></svg>`;
export const money = n => new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(n);
export const dateLabel = d => new Date(`${d}T12:00:00`).toLocaleDateString('pt-BR',{day:'2-digit',month:'short'}).replace(' de ',' ');
export const addDays = (day,n) => {const d=new Date(`${day}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
export const statuses = {pending:'Aguardando aprovação',confirmed:'Confirmado',rejected:'Recusado',completed:'Concluído',pickedup:'Retirado',cancelled:'Cancelado'};
export const badge = status => `<span class="badge ${escape(status)}">${escape(statuses[status]||status)}</span>`;
export async function api(url,body){
 const multipart=body instanceof FormData;
 const response=await fetch(url,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:multipart?{'X-CSRF-Token':csrf}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:multipart?body:JSON.stringify(body),cache:'no-store'});
 csrf=response.headers.get('X-CSRF-Token')||csrf;
 let result;try{result=await response.json();}catch{throw new Error('Conexão indisponível. Tente novamente em instantes.');}
 if(!response.ok)throw new Error(result.error||'Não foi possível concluir a operação.');
 if(result.csrfToken)csrf=result.csrfToken;return result;
}
let toastTimer;
export function notify(message){const element=document.getElementById('toast');element.textContent=message;element.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{element.hidden=true;},6000);}
export const errorBox = message => message?`<div class="alert" role="alert">${escape(message)}</div>`:'';
