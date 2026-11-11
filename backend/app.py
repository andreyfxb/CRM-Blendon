"""AXION authenticated API. SQLite is intended for one persistent server instance."""
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from .config import Settings
from .db import Database, bump, encode, get_client, meta, new_client, persist, serialize_client, utcnow
from .models import Action, ClientFields, ConfigFields, EditClient, EditConfig, Login, normalize_phone
from .security import check_password, digest_token
from .webhook import process_payload

bearer = HTTPBearer(auto_error=False)
STAGES = {'novos': 'Novos contatos', 'negociando': 'Negociando', 'followup': 'Follow-up',
          'aguardando': 'Aguardando resposta', 'vendidos': 'Vendidos', 'perdidos': 'Perdidos'}


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    db = Database(settings.db_path)

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        yield

    app = FastAPI(title='AXION CRM API', version='1.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'],
                       allow_headers=['Authorization', 'Content-Type'])

    @app.middleware('http')
    async def limits_and_headers(request, call_next):
        total = 0
        chunks = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > settings.max_request_bytes:
                return JSONResponse({'detail': 'Arquivo/requisição excede 5 MB.'}, status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default response can echo the invalid input, including credentials.
        return JSONResponse({'detail': 'Dados inválidos. Confira os campos e os limites.'}, status_code=422)

    @app.exception_handler(sqlite3.IntegrityError)
    async def duplicate_error(request, exc):
        return JSONResponse({'detail': 'Já existe um cliente com este WhatsApp/telefone.'}, status_code=409)

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None:
            raise HTTPException(401, 'Entre com seu usuário e senha.')
        token_hash = digest_token(credentials.credentials)
        with db.connect() as con:
            row = con.execute('SELECT * FROM sessions WHERE token_hash=?', (token_hash,)).fetchone()
        if not row or row['expires'] <= time.time() or row['password_fingerprint'] != digest_token(settings.admin_password_hash):
            raise HTTPException(401, 'Sessão expirada. Entre novamente.')
        return token_hash

    @app.get('/health')
    def health():
        with db.connect() as con:
            con.execute('SELECT 1')
        return {'status': 'ok'}

    @app.post('/api/auth/login')
    def login(data: Login, request: Request):
        ip_hash = digest_token(request.client.host if request.client else 'unknown')
        now = time.time()
        with db.connect(write=True) as con:
            con.execute('DELETE FROM login_attempts WHERE at<?', (now - 900,))
            count = con.execute('SELECT COUNT(*) FROM login_attempts WHERE ip_hash=?', (ip_hash,)).fetchone()[0]
            if count >= 10:
                raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
            con.execute('INSERT INTO login_attempts VALUES (?,?)', (ip_hash, now))
        # Both paths perform password hashing; never log credentials or username.
        password_ok = check_password(data.password, settings.admin_password_hash)
        if not (hmac.compare_digest(data.username.encode(), settings.admin_username.encode()) and password_ok):
            raise HTTPException(401, 'Usuário ou senha inválidos.')
        token = secrets.token_urlsafe(48)
        with db.connect(write=True) as con:
            con.execute('DELETE FROM sessions WHERE expires<? OR password_fingerprint!=?', (now, digest_token(settings.admin_password_hash)))
            con.execute('DELETE FROM login_attempts WHERE ip_hash=?', (ip_hash,))
            con.execute('INSERT INTO sessions VALUES (?,?,?)',
                        (digest_token(token), now + settings.session_hours * 3600, digest_token(settings.admin_password_hash)))
        return {'access_token': token, 'token_type': 'bearer', 'expires_in': settings.session_hours * 3600}

    @app.post('/api/auth/logout', status_code=204)
    def logout(token_hash: str = Depends(authenticate)):
        with db.connect(write=True) as con:
            con.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash,))

    @app.get('/api/state', dependencies=[Depends(authenticate)])
    def state():
        with db.connect() as con:
            clients = [serialize_client(con, row) for row in con.execute('SELECT * FROM clients ORDER BY id DESC').fetchall()]
            return {'clients': clients, 'cfg': json.loads(meta(con, 'cfg')), 'cfgVersion': int(meta(con, 'cfg_version')),
                    'fu': int(meta(con, 'fu')), 'revision': int(meta(con, 'revision')),
                    'integration': {'configured': settings.webhook_configured,
                                    'lastReceivedAt': con.execute('SELECT MAX(received_at) FROM messages').fetchone()[0],
                                    'mode': 'receive_only'}}

    @app.post('/api/clients', status_code=201, dependencies=[Depends(authenticate)])
    def add_client(fields: ClientFields):
        data = new_client(fields.model_dump(mode='json'))
        phone_key = normalize_phone(fields.wa or fields.phone) or None
        with db.connect(write=True) as con:
            cfg = json.loads(meta(con, 'cfg'))
            data['follow'] = (date.today() + timedelta(days=cfg['dias'])).isoformat()
            cid = con.execute('INSERT INTO clients(phone_key,data) VALUES (?,?)', (phone_key, encode(data))).lastrowid
            bump(con)
            return serialize_client(con, get_client(con, cid)[0])

    @app.patch('/api/clients/{cid}', dependencies=[Depends(authenticate)])
    def edit_client(cid: int, change: EditClient):
        with db.connect(write=True) as con:
            row, data = get_client(con, cid)
            check_version(row['version'], change.version)
            data.update(change.fields.model_dump(mode='json'))
            append_hist(data, 'Cadastro atualizado')
            persist(con, cid, data, normalize_phone(data['wa'] or data['phone']) or None)
            return serialize_client(con, get_client(con, cid)[0])

    @app.post('/api/clients/{cid}/actions', dependencies=[Depends(authenticate)])
    def action(cid: int, change: Action):
        with db.connect(write=True) as con:
            row, data = get_client(con, cid)
            check_version(row['version'], change.version)
            cfg = json.loads(meta(con, 'cfg'))
            next_date = (date.today() + timedelta(days=cfg['dias'])).isoformat()
            if change.kind == 'stage':
                if change.stage is None:
                    raise HTTPException(422, 'Informe a etapa.')
                data['stage'] = change.stage
                append_hist(data, 'Movido para ' + STAGES[change.stage])
                if change.stage == 'vendidos':
                    data.update(closed=change.value, endDate=date.today().isoformat(), follow=None, next='Pós-venda')
                elif change.stage == 'perdidos':
                    data.update(reason=change.reason, endDate=date.today().isoformat(), follow=None, next='—')
                else:
                    data['follow'] = next_date
            elif change.kind == 'follow_done':
                append_hist(data, 'Follow-up realizado')
                data['follow'] = next_date
                data['next'] = 'Aguardar resposta'
                if data['stage'] == 'followup':
                    data['stage'] = 'aguardando'
                con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='fu'")
            elif change.kind == 'follow_reply':
                append_hist(data, 'Cliente respondeu')
                data.update(stage='negociando', follow=next_date, next='Dar continuidade à negociação')
            elif change.kind == 'follow_date':
                if change.follow is None:
                    raise HTTPException(422, 'Informe a data do follow-up.')
                data['follow'] = change.follow.isoformat()
                append_hist(data, 'Follow-up reagendado')
            elif change.kind == 'reason':
                data['reason'] = change.reason
                append_hist(data, 'Motivo da perda atualizado')
            persist(con, cid, data, row['phone_key'])
            return serialize_client(con, get_client(con, cid)[0])

    @app.delete('/api/clients/{cid}', status_code=204, dependencies=[Depends(authenticate)])
    def delete_client(cid: int, version: int):
        with db.connect(write=True) as con:
            row, _ = get_client(con, cid)
            check_version(row['version'], version)
            con.execute('DELETE FROM clients WHERE id=?', (cid,))
            bump(con)

    @app.put('/api/config', dependencies=[Depends(authenticate)])
    def config(change: EditConfig):
        with db.connect(write=True) as con:
            check_version(int(meta(con, 'cfg_version')), change.version)
            con.execute("UPDATE meta SET value=? WHERE key='cfg'", (encode(change.fields.model_dump()),))
            con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='cfg_version'")
            bump(con)
        return {'saved': True}

    @app.post('/api/import', dependencies=[Depends(authenticate)])
    def import_backup(backup: dict):
        # Validate the whole file before the transaction: no partially imported data.
        rows = backup.get('clients')
        if not isinstance(rows, list) or len(rows) > 10000:
            raise HTTPException(422, 'O backup deve conter até 10.000 clientes.')
        prepared = []
        editable = set(ClientFields.model_fields)
        try:
            for row in rows:
                fields = ClientFields.model_validate({k: v for k, v in row.items() if k in editable})
                data = new_client(fields.model_dump(mode='json'))
                if row.get('stage', 'novos') not in STAGES:
                    raise ValueError()
                data['stage'] = row.get('stage', 'novos')
                # Reuse validation for money/date/stage instead of trusting arbitrary backup fields.
                action_data = Action(version=1, kind='stage', value=row.get('closed', 0), follow=row.get('follow') or None)
                data.update(closed=action_data.value, follow=action_data.follow.isoformat() if action_data.follow else None)
                for key in ('last', 'endDate'):
                    value = row.get(key, '')
                    data[key] = date.fromisoformat(value).isoformat() if value else ''
                data['next'] = str(row.get('next', ''))[:500]
                data['reason'] = str(row.get('reason', ''))[:200]
                history = row.get('hist', [])
                chat = row.get('chat', [])
                if not isinstance(history, list) or not isinstance(chat, list) or len(history) + len(chat) > 10000:
                    raise ValueError()
                for h in history:
                    date.fromisoformat(h['d'])
                data['hist'] = [{'d': h['d'], 't': str(h.get('t', ''))[:500]} for h in history]
                data['legacy_chat'] = [{'m': str(m.get('m', ''))[:20000], 'me': bool(m.get('me')), 'source': 'legacy'} for m in chat]
                key = normalize_phone(fields.wa or fields.phone)
                if not key:
                    raise ValueError('Todos os clientes precisam de telefone ou WhatsApp para deduplicar a importação.')
                prepared.append((key, data))
        except (ValidationError, ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(422, 'Backup inválido. Confira os telefones, nomes, datas e valores; nada foi importado.')
        added = skipped = 0
        with db.connect(write=True) as con:
            for key, data in prepared:
                if con.execute('SELECT 1 FROM clients WHERE phone_key=?', (key,)).fetchone():
                    skipped += 1
                    continue
                con.execute('INSERT INTO clients(phone_key,data) VALUES (?,?)', (key, encode(data)))
                added += 1
            if added:
                bump(con)
        return {'added': added, 'skipped': skipped}

    @app.get('/webhooks/whatsapp', response_class=PlainTextResponse)
    def verify(request: Request):
        if not settings.meta_verify_token:
            raise HTTPException(503, 'Webhook ainda não configurado.')
        params = request.query_params
        if params.get('hub.mode') != 'subscribe' or not hmac.compare_digest(params.get('hub.verify_token', '').encode(), settings.meta_verify_token.encode()):
            raise HTTPException(403, 'Verificação recusada.')
        challenge = params.get('hub.challenge')
        if not challenge:
            raise HTTPException(400, 'Challenge ausente.')
        return challenge

    @app.post('/webhooks/whatsapp')
    async def receive(request: Request):
        if not settings.webhook_configured:
            raise HTTPException(503, 'Webhook ainda não configurado.')
        raw = await request.body()
        expected = 'sha256=' + hmac.new(settings.meta_app_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get('X-Hub-Signature-256', '').encode(), expected.encode()):
            raise HTTPException(403, 'Assinatura inválida.')
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError()
            with db.connect(write=True) as con:
                result = process_payload(con, payload, settings.meta_phone_number_id)
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError, KeyError):
            raise HTTPException(400, 'Evento inválido.')
        # Acknowledge only after the durable transaction committed; Meta can retry on a server error.
        return {'ok': True, **result}

    return app


def check_version(actual, expected):
    if actual != expected:
        raise HTTPException(409, 'O cadastro mudou em outra sessão ou recebeu uma mensagem. Atualize e tente novamente.')


def append_hist(data, text):
    now = utcnow()
    data.setdefault('hist', []).append({'d': now[:10], 'at': now, 't': text})
    data['last'] = now[:10]
