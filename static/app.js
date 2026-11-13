import {api,escape,notify,errorBox} from './common.js';
import {renderBooking,bookingClick,bookingSubmit,loadSlots} from './booking.js';
import {renderClub,clubClick,clubSubmit,loadClub} from './club.js';
import {renderAdmin,adminClick,adminSubmit,loadAdmin} from './admin.js';

const state={boot:null,view:'booking',error:'',busy:false,step:0,date:'',time:'',offset:0,slots:[],slotsLoading:true,selected:[],booking:null,authMode:'login',cart:{},redeem:false,orders:[],bookings:[],admin:null,filter:'pending',adminSection:'dashboard',pix:null,lastOrderId:null};
const ctx={state,render,notify,reload,go};
async function reload(){state.boot=await api('/api/bootstrap');document.getElementById('account-label').textContent=state.boot.user?.name.split(' ')[0]||'Minha conta';return state.boot;}
function render(){
 const active=document.activeElement;const focus=active?.dataset?.action?Object.fromEntries(Object.entries(active.dataset).filter(([key])=>['action','id','time','date','filter','step','command'].includes(key))):null;
 const main=document.getElementById('main');
 if(!state.boot){main.innerHTML=errorBox(state.error)+`<div class="empty"><p>Não foi possível carregar o sistema.</p><button class="primary" data-action="reload">Tentar novamente</button></div>`;return;}
 main.innerHTML=errorBox(state.error)+(state.view==='booking'?renderBooking(ctx):state.view==='admin'?renderAdmin(ctx):renderClub(ctx));
 document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===state.view);el.setAttribute('aria-current',el.dataset.nav===state.view?'page':'false');});
 if(focus){const selector=Object.entries(focus).map(([key,value])=>`[data-${key}="${CSS.escape(value)}"]`).join('');main.querySelector(selector)?.focus({preventScroll:true});}
}
async function go(view){state.view=['booking','club','store','admin'].includes(view)?view:'booking';state.error='';document.getElementById('navigation').classList.remove('open');document.getElementById('menu-button').setAttribute('aria-expanded','false');render();try{if(state.view==='admin'&&state.boot.isAdmin)await loadAdmin(ctx);else if(['club','store'].includes(state.view)&&state.boot.user)await loadClub(ctx);else if(state.view==='booking')await loadSlots(ctx);}catch(e){state.error=e.message;}render();}
window.addEventListener('hashchange',()=>go(location.hash.slice(1)));
document.getElementById('menu-button').addEventListener('click',e=>{const open=document.getElementById('navigation').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',String(open));});
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-action]');if(!button||button.disabled||(state.busy&&button.dataset.action!=='filter'))return;
 const action=button.dataset.action;state.error='';
 try{if(action==='pix-copy'){const input=button.closest('.pix-panel').querySelector('textarea');try{await navigator.clipboard.writeText(input.value);notify('Código Pix copiado.');}catch{input.focus();input.select();notify('Selecione e copie o código Pix.');}return;}if(action==='reload'){await reload();await go(state.view);return;}if(action==='logout'){await api('/api/logout',{});state.cart={};state.admin=null;state.bookings=[];state.orders=[];state.pix=null;state.lastOrderId=null;await reload();await go('club');return;}
 await bookingClick(ctx,action,button);await clubClick(ctx,action,button);await adminClick(ctx,action,button);
 }catch(e){state.error=e.message;render();}
});
document.addEventListener('submit',async event=>{
 const form=event.target;if(!form.dataset.form)return;event.preventDefault();if(state.busy)return;
 const fields=new FormData(form);const value=form.dataset.form==='product'?fields:Object.fromEntries(fields);state.busy=true;state.error='';const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
 try{await bookingSubmit(ctx,form.dataset.form,value);await clubSubmit(ctx,form.dataset.form,value);await adminSubmit(ctx,form.dataset.form,value);}
 catch(e){state.error=e.message;const old=form.querySelector('.form-error');if(old)old.remove();const node=document.createElement('div');node.className='alert form-error';node.setAttribute('role','alert');node.textContent=e.message;form.prepend(node);state.error='';}
 finally{state.busy=false;if(submit)submit.disabled=false;}
});
async function init(){try{await reload();state.date=state.boot.today;const token=new URLSearchParams(location.search).get('reserva');if(token){state.booking=(await api(`/api/bookings?token=${encodeURIComponent(token)}`)).booking;state.step=3;}await go(location.hash.slice(1)||'booking');}catch(e){state.error=e.message;render();}}
void init();
setInterval(async()=>{if(state.boot&&state.view==='booking'&&state.step===0&&!state.busy){try{await loadSlots(ctx);render();}catch{/* Preserve the current selection; the server validates at checkout. */}}},30000);
let adminPollPending=false;
setInterval(async()=>{
 if(adminPollPending||document.hidden||!state.boot?.isAdmin||state.view!=='admin'||state.adminSection!=='dashboard'||!state.admin||state.busy)return;
 const snapshot=state.admin,filter=state.filter;
 adminPollPending=true;
 try{
  const response=await fetch('/api/admin',{cache:'no-store'});
  if(!response.ok)return;
  const updated=await response.json();
  // Ignore responses superseded by navigation, another refresh, or a user action.
  if(document.hidden||state.view!=='admin'||state.adminSection!=='dashboard'||state.busy||state.admin!==snapshot||state.filter!==filter)return;
  if(JSON.stringify(updated)!==JSON.stringify(snapshot)){state.admin=updated;render();}
 }catch{/* Keep the last dashboard until the next successful refresh. */}
 finally{adminPollPending=false;}
},15000);
