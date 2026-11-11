// DOM integration (not a real browser). Uses the real local FastAPI fixture.
const {JSDOM}=require('jsdom');
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=require('node:path').resolve(__dirname,'..');
const base='http://127.0.0.1:8765';
const wait=async fn=>{let last;for(let i=0;i<100;i++){try{if(await fn())return;}catch(e){last=e;}await new Promise(r=>setTimeout(r,100));}throw last||Error('timeout');};
const message=async(id,text)=>{
 const payload={object:'whatsapp_business_account',entry:[{changes:[{field:'messages',value:{metadata:{phone_number_id:'test-phone-id'},contacts:[{wa_id:'5511987654321',profile:{name:'Contato Automático'}}],messages:[{id,from:'5511987654321',timestamp:String(Math.floor(Date.now()/1000)),type:'text',text:{body:text}}]}}]}]};
 const body=JSON.stringify(payload);const r=await fetch(base+'/webhooks/whatsapp',{method:'POST',body,headers:{'X-Hub-Signature-256':'sha256='+crypto.createHmac('sha256','test-secret').update(body).digest('hex')}});assert.equal(r.status,200);
};
(async()=>{
 const dom=new JSDOM(fs.readFileSync(root+'/index.html','utf8'),{url:'http://127.0.0.1:5500',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window;w.eval=code=>require('node:vm').runInContext(code,dom.getInternalVMContext());w.fetch=fetch;w.AbortSignal=AbortSignal;w.scrollTo=()=>{};w.confirm=()=>true;
 try{
 for(const f of ['config','app','integration'])w.eval(fs.readFileSync(root+'/assets/'+f+'.js','utf8'));
 const $=id=>w.document.getElementById(id);
 $('api-url').value=base;$('login-user').value='admin';$('login-password').value='Only-local-test-123!';
 w.loginCRM({preventDefault(){}});await wait(()=>{if($('login-error').textContent)throw Error($('login-error').textContent);return $('workspace').hidden===false;});
 assert.equal($('login').hidden,true);
 // Polling is exercised by waiting for the actual interval (no full-page reload).
 w.eval("go('clientes')");await message('wamid.dom1','Mensagem DOM automática');
 await wait(()=>$('pg').textContent.includes('Contato Automático'));
 w.eval("go('whatsapp')");assert.match($('pg').textContent,/Mensagem DOM automática/);
 w.eval("moveTo(S.clients[0].id,'negociando')");await wait(()=>w.eval("S.clients[0].stage==='negociando'"));
 await message('wamid.dom2','Segunda mensagem DOM');await wait(()=>$('pg').textContent.includes('Segunda mensagem DOM'));
 assert.equal(w.eval('S.clients.length'),1);assert.equal(w.eval('S.clients[0].stage'),'negociando');
 w.eval('frm(S.clients[0].id)');w.document.querySelector('[name=notes]').value='Texto digitado';
 await message('wamid.dom3','Mensagem concorrente');
 const form=w.document.querySelector('#mb form');w.eval('sv')({preventDefault(){},target:form},w.eval('S.clients[0].id'));
 await wait(()=>$('sync-state').textContent.includes('mudou'));
 assert.equal(w.document.querySelector('[name=notes]').value,'Texto digitado');
 w.eval('cl()');await w.syncState(true);assert.equal(w.eval('S.clients[0].chat.length'),3);
 // Confirm edit succeeds after refreshing versions.
 w.eval('frm(S.clients[0].id)');w.document.querySelector('[name=notes]').value='Texto salvo';
 w.eval('sv')({preventDefault(){},target:w.document.querySelector('#mb form')},w.eval('S.clients[0].id'));
 await wait(()=>w.eval("S.clients[0].notes==='Texto salvo'"));
 w.eval("go('config')");$('c_loja').value='Loja DOM';w.svc();await wait(()=>w.eval("S.cfg.loja==='Loja DOM'"));
 for(const key of ['dashboard','clientes','novos','negociando','followup','aguardando','vendidos','perdidos','whatsapp','relatorios','config']){
 w.eval(`go('${key}')`);assert.doesNotMatch($('pg').innerHTML,/NaN|undefined/);
 }
 await w.logoutCRM();assert.equal($('login').hidden,false);assert.equal($('pg').innerHTML,'');
 console.log('PASS DOM integration: login, actual API, polling webhook → UI, stage preservation, stale edit rejection, CRUD, config, all views and logout.');
 }finally{w.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
