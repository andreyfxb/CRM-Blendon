// Run with the local fixture server described in docs/TESTES.md.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
async function webhook(id, text){
 const body=JSON.stringify({object:'whatsapp_business_account',entry:[{changes:[{field:'messages',value:{metadata:{phone_number_id:'test-phone-id'},contacts:[{wa_id:'5511987654321',profile:{name:'Contato Automático'}}],messages:[{id,from:'5511987654321',timestamp:String(Math.floor(Date.now()/1000)),type:'text',text:{body:text}}]}}]}]});
 const r=await fetch('http://127.0.0.1:8765/webhooks/whatsapp',{method:'POST',body,headers:{'content-type':'application/json','x-hub-signature-256':'sha256='+crypto.createHmac('sha256','test-secret').update(body).digest('hex')}});assert.equal(r.status,200);
}
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5500');
 await page.locator('#api-url').fill('http://127.0.0.1:8765');
 await page.locator('#login-user').fill('admin');await page.locator('#login-password').fill('Only-local-test-123!');
 await page.locator('#login-button').click();await page.locator('#workspace').waitFor({state:'visible'});
 await page.evaluate(()=>go('clientes'));
 await webhook('wamid.browser1','Mensagem recebida sem atualizar a página');
 await page.getByText('Contato Automático',{exact:true}).first().waitFor({timeout:12000});
 await page.evaluate(()=>go('whatsapp'));
 await page.getByText('Mensagem recebida sem atualizar a página',{exact:true}).waitFor();
 await page.evaluate(()=>moveTo(S.clients[0].id,'negociando'));
 await page.waitForFunction(()=>S.clients[0].stage==='negociando');
 await webhook('wamid.browser2','Segunda mensagem');
 await page.getByText('Segunda mensagem',{exact:true}).waitFor({timeout:12000});
 assert.equal(await page.evaluate(()=>S.clients.length),1);assert.equal(await page.evaluate(()=>S.clients[0].stage),'negociando');
 // A backend update during an open form must cause a conflict, never erase the message.
 await page.evaluate(()=>frm(S.clients[0].id));
 await page.locator('[name=notes]').fill('Edição durante mensagem');
 await webhook('wamid.browser3','Mensagem durante edição');
 await page.getByRole('button',{name:'Salvar cliente',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('sync-state').textContent.includes('mudou'));
 assert.equal(await page.locator('[name=notes]').inputValue(),'Edição durante mensagem');
 await page.evaluate(()=>cl());await page.evaluate(()=>syncState(true));
 assert.equal(await page.evaluate(()=>S.clients[0].chat.length),3);
 await page.evaluate(()=>go('config'));assert.equal(await page.locator('#c_telefone').inputValue(),'11977321570');
 await page.locator('#c_loja').fill('Loja do teste');await page.getByRole('button',{name:'Salvar configurações'}).click();
 await page.waitForFunction(()=>S.cfg.loja==='Loja do teste');
 // Every page renders with server-owned data.
 for(const key of ['dashboard','clientes','novos','negociando','followup','aguardando','vendidos','perdidos','whatsapp','relatorios','config']){
 await page.evaluate(k=>go(k),key);assert.doesNotMatch(await page.locator('#pg').innerHTML(),/NaN|undefined/);
 }
 await page.evaluate(()=>go('dashboard'));await page.screenshot({path:'/tmp/axion-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.evaluate(()=>go('whatsapp'));await page.screenshot({path:'/tmp/axion-mobile.png',fullPage:true});
 await page.evaluate(()=>logoutCRM());await page.locator('#login').waitFor({state:'visible'});
 assert.equal(await page.locator('#pg').innerHTML(),'');assert.equal(await page.evaluate(()=>apiToken),'');
 assert.deepEqual(errors,[]);console.log('PASS: real browser login, signed synthetic webhook → automatic contact/message, pipeline, edit conflict, config, all views, mobile, logout.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
