/* Server owns all business data. Only the public server URL is stored locally.
   The opaque login token lives in memory and expires server-side after 8 hours. */
let apiURL = '', apiToken = '', polling = null, syncing = false, mutating = false;
const editableFields = ['name','phone','wa','ig','origin','product','model','storage','color','budget','value','notes','created'];
const configFields = ['loja','admin','telefone','dias','n1','n2','n3'];
let serverRevision = -1;
try { $('api-url').value = window.AXION_CONFIG.apiBaseUrl || localStorage.getItem('axion_api_url') || ''; } catch (_) {}

function connection(text) { $('sync-state').textContent = text; }
function endpoint(value) {
  const u = new URL(value);
  if (u.username || u.password || u.search || u.hash || u.pathname !== '/') throw Error('Use apenas a origem do servidor, sem caminho, senha ou parâmetros.');
  const local = ['localhost','127.0.0.1','[::1]'].includes(u.hostname);
  if (u.protocol !== 'https:' && !(local && u.protocol === 'http:')) throw Error('O servidor precisa de HTTPS (HTTP é permitido apenas no computador local).');
  return u.origin;
}
async function api(path, options = {}) {
  const response = await fetch(apiURL + path, {
    ...options, cache:'no-store', signal:AbortSignal.timeout(20000),
    headers: {'Content-Type':'application/json', ...(apiToken ? {Authorization:'Bearer '+apiToken} : {}), ...options.headers}
  });
  if (!response.ok) {
    let message = 'Falha ao acessar o servidor ('+response.status+').';
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch (_) {}
    if (response.status === 401 && apiToken) showLogin('Sessão expirada. Entre novamente.');
    const error = new Error(message); error.status = response.status; throw error;
  }
  return response.status === 204 ? null : response.json();
}
function showLogin(message = '') {
  clearInterval(polling); polling = null; apiToken = '';
  S.clients = []; S.cfg = {}; S.fu = 0; serverRevision = -1;
  $('pg').innerHTML = ''; $('mb').innerHTML = ''; cl();
  $('workspace').hidden = true; $('side').hidden = true; $('login').hidden = false;
  $('login-error').textContent = message;
}
function loginCRM(event) {
  event.preventDefault();
  (async () => {
    $('login-button').disabled = true; $('login-error').textContent = '';
    try {
      apiURL = endpoint($('api-url').value.trim());
      const login = await api('/api/auth/login', {method:'POST', body:JSON.stringify({username:$('login-user').value, password:$('login-password').value})});
      apiToken = login.access_token; $('login-password').value = '';
      try { localStorage.setItem('axion_api_url', apiURL); } catch (_) {}
      S.view = 'dashboard'; await syncState(true);
      $('login').hidden = true; $('workspace').hidden = false; $('side').hidden = false;
      polling = setInterval(() => syncState().catch(syncError), 5000);
    } catch (error) { showLogin(error.message); }
    finally { $('login-button').disabled = false; }
  })();
  return false;
}
async function logoutCRM() {
  try { await api('/api/auth/logout', {method:'POST'}); } catch (_) {}
  showLogin();
}
function modalOpen() { return $('md').classList.contains('on'); }
function editingPage() { return S.view === 'config' || ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName); }
async function syncState(force = false) {
  if (!apiToken || syncing || (!force && (mutating || modalOpen() || editingPage() || document.hidden))) return;
  syncing = true;
  try {
    const state = await api('/api/state');
    const changed = state.revision !== serverRevision;
    S.clients = state.clients; S.cfg = state.cfg; S.cfgVersion = state.cfgVersion; S.fu = state.fu; S.integration = state.integration;
    serverRevision = state.revision;
    if (force || changed) render();
    const status = state.integration.configured ? 'Servidor conectado · webhook configurado' : 'Servidor conectado · falta configurar a Meta';
    connection(status + ' · atualizado às ' + new Date().toLocaleTimeString('pt-BR'));
  } finally { syncing = false; }
}
function syncError(error) {
  if (!apiToken) return;
  connection('Sem sincronização: '+error.message+' Os dados existentes continuam no servidor.');
}
async function mutation(task, message) {
  if (mutating) return;
  mutating = true;
  try { await task(); cl(); await syncState(true); toast(message); }
  catch (error) {
    toast(error.message); connection(error.message);
    // Keep the form and its typed values open; a conflict must never overwrite incoming data.
    if (error.status === 409) connection(error.message+' Feche e reabra o formulário para carregar os dados atuais.');
  } finally { mutating = false; }
}
const fieldsOf = value => Object.fromEntries(editableFields.map(k=>[k,value[k] ?? (['budget','value'].includes(k)?0:'')]));
sv = function(event, id) {
  event.preventDefault();
  const fields = Object.fromEntries(new FormData(event.target));
  fields.budget = +fields.budget || 0; fields.value = +fields.value || 0;
  const version = id ? cli(id).version : null;
  mutation(() => api('/api/clients'+(id?'/'+id:''), {method:id?'PATCH':'POST', body:JSON.stringify(id?{version,fields}:fields)}), 'Cliente salvo no servidor');
  return false;
};
function clientAction(id, body) {
  const c = cli(id);
  if (!c) return Promise.reject(Error('Cliente não encontrado.'));
  return api('/api/clients/'+id+'/actions', {method:'POST', body:JSON.stringify({version:c.version, ...body})});
}
moveTo = function(id, stage, extra) {
  const c = cli(id); if (!c || c.stage === stage) return;
  if (stage === 'vendidos' && !extra) return modal(`<h3>Venda concluída</h3><label>Valor fechado (R$)<input id="vf" type="number" min="0" value="${c.value}"></label><div class="ra"><button class="btn" onclick="cl()">Cancelar</button><button class="btn p" onclick="moveTo(${id},'vendidos',{v:+$('vf').value})">Confirmar</button></div>`);
  if (stage === 'perdidos' && !extra) return modal(`<h3>Motivo da perda</h3><select id="mo">${MOT.map(m=>`<option>${E(m)}</option>`).join('')}</select><div class="ra"><button class="btn" onclick="cl()">Cancelar</button><button class="btn p" onclick="moveTo(${id},'perdidos',{m:$('mo').value})">Confirmar</button></div>`);
  mutation(()=>clientAction(id,{kind:'stage',stage,value:extra?.v||0,reason:extra?.m||''}), 'Etapa atualizada');
};
fuDone = id => mutation(()=>clientAction(id,{kind:'follow_done'}), 'Follow-up registrado');
fuReply = id => mutation(()=>clientAction(id,{kind:'follow_reply'}), 'Resposta registrada');
c2 = id => { const follow=$('nd').value; if(follow)mutation(()=>clientAction(id,{kind:'follow_date',follow}), 'Follow-up reagendado'); };
function updateReason(id, reason) { mutation(()=>clientAction(id,{kind:'reason',reason}), 'Motivo atualizado'); }
del = id => modal(`<h3>Excluir cliente?</h3><p>${E(cli(id).name)} será removido. Exporte um backup antes se precisar guardar uma cópia.</p><div class="ra"><button class="btn" onclick="cl()">Cancelar</button><button class="btn d" onclick="deleteClient(${id})">Excluir</button></div>`);
function deleteClient(id) { mutation(()=>api('/api/clients/'+id+'?version='+cli(id).version,{method:'DELETE'}), 'Cliente excluído'); }
openWA = (id, text) => {
  let phone = (cli(id).wa || cli(id).phone || '').replace(/\D/g,'');
  if ([10,11].includes(phone.length)) phone='55'+phone;
  if (!phone) return toast('Cadastre o WhatsApp deste cliente.');
  window.open('https://wa.me/'+phone+(text?'?text='+encodeURIComponent(text):''),'_blank','noopener,noreferrer');
};
V.config = () => {
  const g = S.cfg;
  const input=(key,label,type='text')=>`<label>${label}<input id="c_${key}" type="${type}" value="${E(g[key])}"></label>`;
  const check=(key,label)=>`<label><input id="c_${key}" type="checkbox" ${g[key]?'checked':''}> ${label}</label>`;
  const i=S.integration||{};
  return hd('Configurações','Dados centralizados no servidor','<button class="btn p" onclick="svc()">Salvar configurações</button>')+`<div class="grid g2"><div class="cd f" style="display:grid;gap:10px"><b>Dados da loja</b>${input('loja','Nome da loja')}${input('admin','Responsável')}${input('telefone','WhatsApp da loja','tel')}</div><div class="cd f" style="display:grid;gap:10px"><b>Follow-up</b>${input('dias','Prazo padrão (dias)','number')}${check('n1','Follow-ups vencidos')}${check('n2','Follow-ups do dia')}${check('n3','Novos contatos')}</div><div class="cd"><b>Recebimento do WhatsApp</b><p class="mu">${i.configured?'Webhook configurado no servidor.':'Aguardando configuração das credenciais da Meta no servidor.'}</p><p class="mu">${i.lastReceivedAt?'Última mensagem registrada: '+E(new Date(i.lastReceivedAt).toLocaleString('pt-BR')):'Ainda não há mensagens recebidas registradas.'}</p><p class="mu">Os contatos entram automaticamente quando a Meta entrega os eventos. As respostas continuam manuais. Tokens e segredos não são cadastrados nesta tela.</p></div><div class="cd"><b>Backup e importação</b><p class="mu">Importe o JSON da versão antiga. Contatos com telefone já existente serão ignorados; nenhum cadastro atual será substituído. Configurações e contadores antigos não são importados.</p><button class="btn" onclick="backup()">Exportar backup</button> <label class="btn">Importar JSON<input type="file" hidden accept=".json,application/json" onchange="restoreBackup(this.files[0])"></label><p class="mu">Reimportar um backup serve para recuperar contatos ausentes; não substitui o banco completo. Históricos antigos são identificados como importados.</p></div></div>`;
};
function svc() {
  const fields = Object.fromEntries(configFields.map(k=>[k,['n1','n2','n3'].includes(k)?$('c_'+k).checked:k==='dias'?+$('c_'+k).value:$('c_'+k).value]));
  mutation(()=>api('/api/config',{method:'PUT',body:JSON.stringify({version:S.cfgVersion,fields})}), 'Configurações salvas');
}
async function backup() {
  try {
    const state = await api('/api/state');
    const url = URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='AXION-backup-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  } catch(error) { toast(error.message); }
}
async function restoreBackup(file) {
  if(!file)return;
  if(file.size>5*1024*1024)return toast('O backup deve ter até 5 MB.');
  try {
    const data=JSON.parse(await file.text());
    if(!Array.isArray(data.clients))throw Error('Backup inválido: falta a lista de clientes.');
    if(!confirm('Importar os contatos ausentes? Cadastros existentes serão preservados.'))return;
    await mutation(async()=>{const r=await api('/api/import',{method:'POST',body:JSON.stringify({clients:data.clients})});toast(`${r.added} importados; ${r.skipped} já existentes`);}, 'Importação concluída (contatos existentes preservados)');
  } catch(error) { toast(error.message); }
}
