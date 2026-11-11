import concurrent.futures
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.models import normalize_phone
from backend.security import password_hash

PASSWORD = 'A-test-only-password-123!'
HASH = password_hash(PASSWORD)


class APITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(str(Path(self.tmp.name) / 'test.sqlite3'), 'admin', HASH,
                                 ('http://localhost:5500',), 'test-secret', 'test-verify', 'test-phone-id')
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.auth = {'Authorization': 'Bearer ' + self.client.post('/api/auth/login', json={
            'username': 'admin', 'password': PASSWORD}).json()['access_token']}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def state(self):
        response = self.client.get('/api/state', headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def payload(self, mid='wamid.test1', sender='5511987654321', kind='text', text='Quero saber mais'):
        message = {'id': mid, 'from': sender, 'timestamp': '1794402000', 'type': kind}
        message[kind] = {'body': text} if kind == 'text' else {}
        return {'object': 'whatsapp_business_account', 'entry': [{'id': 'waba-test', 'changes': [
            {'field': 'messages', 'value': {'metadata': {'phone_number_id': 'test-phone-id'},
             'contacts': [{'wa_id': sender, 'profile': {'name': 'Cliente Teste'}}], 'messages': [message]}}]}]}

    def post_webhook(self, payload):
        raw = json.dumps(payload).encode()
        signature = 'sha256=' + hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/whatsapp', content=raw,
                                headers={'X-Hub-Signature-256': signature, 'Content-Type': 'application/json'})

    def test_new_message_creates_contact_without_invented_fields(self):
        response = self.post_webhook(self.payload())
        self.assertEqual(response.status_code, 200)
        c = self.state()['clients'][0]
        self.assertEqual((c['name'], c['wa'], c['stage'], c['origin']),
                         ('Cliente Teste', '+5511987654321', 'novos', 'WhatsApp'))
        self.assertEqual((c['product'], c['model'], c['budget'], c['value']), ('', '', 0, 0))
        self.assertEqual(c['chat'][0]['m'], 'Quero saber mais')
        self.assertTrue(c['chat'][0]['at'].endswith('+00:00'))
        self.assertEqual(c['hist'][-1]['t'], 'Mensagem recebida no WhatsApp (text)')

    def test_existing_contact_preserves_stage_and_operator_name(self):
        self.post_webhook(self.payload())
        c = self.state()['clients'][0]
        response = self.client.post(f"/api/clients/{c['id']}/actions", headers=self.auth,
                                    json={'version': c['version'], 'kind': 'stage', 'stage': 'vendidos', 'value': 500})
        self.assertEqual(response.status_code, 200)
        self.post_webhook(self.payload(mid='wamid.test2'))
        state = self.state()
        self.assertEqual(len(state['clients']), 1)
        self.assertEqual(state['clients'][0]['stage'], 'vendidos')
        self.assertEqual(state['clients'][0]['closed'], 500)
        self.assertEqual(len(state['clients'][0]['chat']), 2)

    def test_duplicate_message_is_idempotent(self):
        self.post_webhook(self.payload())
        before = self.state()
        result = self.post_webhook(self.payload()).json()
        self.assertEqual(result['duplicate'], 1)
        self.assertEqual(before, self.state())

    def test_parallel_duplicate_delivery(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.post_webhook(self.payload()).status_code, range(4)))
        self.assertEqual(results, [200]*4)
        c = self.state()['clients']
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]['chat']), 1)

    def test_invalid_and_missing_signatures_cannot_write(self):
        for headers in ({}, {'X-Hub-Signature-256': 'sha256=bad'}):
            self.assertEqual(self.client.post('/webhooks/whatsapp', json=self.payload(), headers=headers).status_code, 403)
        self.assertEqual(self.state()['clients'], [])

    def test_status_events_never_create_contacts_or_chat(self):
        p = self.payload()
        value = p['entry'][0]['changes'][0]['value']
        value.pop('messages')
        value['statuses'] = [{'id': 'outgoing.test', 'status': 'read', 'timestamp': '1794402000', 'recipient_id': '5511987654321'}]
        self.assertEqual(self.post_webhook(p).json()['statuses'], 1)
        self.assertEqual(self.post_webhook(p).json()['statuses'], 0)
        self.assertEqual(self.state()['clients'], [])

    def test_wrong_phone_and_echoes_ignored(self):
        p = self.payload()
        p['entry'][0]['changes'][0]['value']['metadata']['phone_number_id'] = 'other-phone'
        self.assertEqual(self.post_webhook(p).json()['ignored'], 1)
        p = self.payload()
        p['entry'][0]['changes'][0]['field'] = 'smb_message_echoes'
        self.assertEqual(self.post_webhook(p).json()['ignored'], 1)
        self.assertEqual(self.state()['clients'], [])

    def test_nontext_media_labeled_without_fake_transcription(self):
        self.post_webhook(self.payload(kind='audio'))
        c = self.state()['clients'][0]
        self.assertEqual(c['chat'][0]['m'], '[Áudio]')
        self.assertEqual(c['chat'][0]['type'], 'audio')

    def test_missing_profile_uses_phone(self):
        p = self.payload()
        p['entry'][0]['changes'][0]['value']['contacts'] = []
        self.post_webhook(p)
        self.assertEqual(self.state()['clients'][0]['name'], '+5511987654321')

    def test_normalization_and_manual_contact_matches_webhook(self):
        self.assertEqual(normalize_phone('(11) 98765-4321'), '5511987654321')
        self.assertEqual(normalize_phone('+1 202 555 0123'), '12025550123')
        response = self.client.post('/api/clients', headers=self.auth, json={'name': 'Nome cadastrado', 'wa': '(11) 98765-4321'})
        self.assertEqual(response.status_code, 201)
        self.post_webhook(self.payload())
        self.assertEqual(len(self.state()['clients']), 1)
        self.assertEqual(self.state()['clients'][0]['name'], 'Nome cadastrado')

    def test_data_routes_require_auth(self):
        for method, path, payload in [('get','/api/state',None), ('post','/api/clients',{'name':'Teste'}),
                                      ('post','/api/import',{'clients':[]}), ('put','/api/config',{'version':1,'fields':{}}),
                                      ('delete','/api/clients/1?version=1',None),
                                      ('patch','/api/clients/1',{'version':1,'fields':{'name':'Teste'}})]:
            kwargs = {'json': payload} if payload is not None else {}
            self.assertEqual(getattr(self.client, method)(path, **kwargs).status_code, 401)

    def test_logout_revokes_session(self):
        self.assertEqual(self.client.post('/api/auth/logout', headers=self.auth).status_code, 204)
        self.assertEqual(self.client.get('/api/state', headers=self.auth).status_code, 401)

    def test_verify_challenge_plain_text_and_invalid_token(self):
        args = {'hub.mode':'subscribe', 'hub.verify_token':'test-verify', 'hub.challenge':'12345'}
        r = self.client.get('/webhooks/whatsapp', params=args)
        self.assertEqual(r.text, '12345')
        self.assertIn('text/plain', r.headers['content-type'])
        args['hub.verify_token'] = 'bad'
        self.assertEqual(self.client.get('/webhooks/whatsapp', params=args).status_code, 403)

    def test_stale_edit_cannot_overwrite_new_message(self):
        self.post_webhook(self.payload())
        c = self.state()['clients'][0]
        self.post_webhook(self.payload(mid='wamid.new'))
        r = self.client.post(f"/api/clients/{c['id']}/actions", headers=self.auth,
                             json={'version':c['version'],'kind':'stage','stage':'perdidos'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(len(self.state()['clients'][0]['chat']), 2)
        self.assertEqual(self.state()['clients'][0]['stage'], 'novos')

    def test_import_is_atomic_and_idempotent(self):
        rows = [{'name':'Legado','wa':'(11) 98765-4321','stage':'negociando','hist':[], 'chat':[{'m':'antigo','me':True}]}]
        r = self.client.post('/api/import', headers=self.auth, json={'clients':rows})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {'added':1,'skipped':0})
        r = self.client.post('/api/import', headers=self.auth, json={'clients':rows})
        self.assertEqual(r.json(), {'added':0,'skipped':1})
        self.post_webhook(self.payload())
        c = self.state()['clients'][0]
        self.assertEqual(c['stage'], 'negociando')
        self.assertEqual(c['chat'][0]['source'], 'legacy')
        bad = [{'name':'Válido','wa':'11911112222'}, {'name':'Inválido','wa':'x'}]
        self.assertEqual(self.client.post('/api/import', headers=self.auth, json={'clients':bad}).status_code, 422)
        self.assertEqual(len(self.state()['clients']), 1)

    def test_crud_config_and_counters(self):
        c = self.client.post('/api/clients', headers=self.auth, json={'name':'Teste','wa':'11911112222'}).json()
        fields = {k:c[k] for k in ('name','wa','phone','ig','origin','product','model','storage','color','budget','value','notes','created')}
        fields['notes'] = 'Observação editada'
        c = self.client.patch(f"/api/clients/{c['id']}", headers=self.auth, json={'version':c['version'],'fields':fields}).json()
        self.assertEqual(c['notes'], 'Observação editada')
        c = self.client.post(f"/api/clients/{c['id']}/actions", headers=self.auth, json={'version':c['version'],'kind':'follow_done'}).json()
        state = self.state()
        self.assertEqual(state['fu'], 1)
        cfg = state['cfg']; cfg['loja'] = 'Loja editada'
        self.assertEqual(self.client.put('/api/config', headers=self.auth, json={'version':state['cfgVersion'],'fields':cfg}).status_code, 200)
        self.assertEqual(self.state()['cfg']['loja'], 'Loja editada')
        self.assertEqual(self.client.delete(f"/api/clients/{c['id']}?version={c['version']}",headers=self.auth).status_code, 204)
        self.assertEqual(self.state()['clients'], [])

    def test_persistence_after_application_restart(self):
        self.post_webhook(self.payload())
        with TestClient(create_app(self.settings)) as second:
            login = second.post('/api/auth/login', json={'username':'admin','password':PASSWORD}).json()
            clients = second.get('/api/state', headers={'Authorization':'Bearer '+login['access_token']}).json()['clients']
            self.assertEqual(len(clients), 1)
            self.assertEqual(len(clients[0]['chat']), 1)

    def test_failed_login_throttle_and_no_input_echo(self):
        for _ in range(10):
            self.assertEqual(self.client.post('/api/auth/login', json={'username':'admin','password':'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', json={'username':'admin','password':PASSWORD}).status_code, 429)
        r=self.client.post('/api/auth/login', json={'username': {'secret':'never echo'}, 'password':'sensitive-password'})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn('sensitive-password',r.text)

    def test_cors_and_response_cache(self):
        headers={'Origin':'http://localhost:5500','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization'}
        self.assertEqual(self.client.options('/api/state', headers=headers).status_code, 200)
        headers['Origin']='https://untrusted.example'
        self.assertEqual(self.client.options('/api/state', headers=headers).status_code, 400)
        self.assertEqual(self.client.get('/api/state',headers=self.auth).headers['cache-control'], 'no-store')

    def test_request_size_limit(self):
        self.assertEqual(self.client.post('/webhooks/whatsapp',content=b'x'*(5*1024*1024+1)).status_code, 413)


if __name__ == '__main__':
    unittest.main()
