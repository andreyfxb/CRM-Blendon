"""Only inbound Cloud API messages and delivery status events; never sends messages."""
import json
import logging
from datetime import datetime, timezone
from .db import bump, encode, new_client, utcnow
from .models import ClientFields, normalize_phone

logger = logging.getLogger('axion.webhook')
LABELS = {'image': 'Imagem', 'audio': 'Áudio', 'video': 'Vídeo', 'document': 'Documento',
          'sticker': 'Figurinha', 'location': 'Localização', 'contacts': 'Contato',
          'reaction': 'Reação', 'interactive': 'Interação', 'button': 'Botão',
          'unsupported': 'Conteúdo não suportado', 'unknown': 'Tipo desconhecido'}


def timestamp(value):
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat(timespec='seconds')
    except (TypeError, ValueError, OverflowError, OSError):
        return utcnow()


def content(message):
    kind = str(message.get('type', 'unknown'))[:64]
    if kind == 'text':
        text = message.get('text', {}).get('body', '')
    elif kind == 'button':
        text = message.get('button', {}).get('text', '')
    elif kind == 'interactive':
        item = message.get('interactive', {})
        reply = item.get('button_reply') or item.get('list_reply') or {}
        text = reply.get('title', '')
    else:
        text = '[' + LABELS.get(kind, 'Mensagem não textual') + ']'
        detail = message.get(kind, {})
        if isinstance(detail, dict) and isinstance(detail.get('caption'), str):
            text += ' ' + detail['caption']
    return kind, str(text)[:20000]


def process_payload(con, payload, expected_phone_id):
    received = duplicate = status_count = ignored = 0
    if payload.get('object') != 'whatsapp_business_account':
        return {'received': 0, 'duplicate': 0, 'statuses': 0, 'ignored': 1}
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            # Do not process echoes/history as inbound contacts; coexistence history is a separate scope.
            if change.get('field') != 'messages':
                ignored += 1
                continue
            value = change.get('value', {})
            if str(value.get('metadata', {}).get('phone_number_id', '')) != expected_phone_id:
                ignored += 1
                continue
            for status in value.get('statuses', []):
                if not status.get('id') or not status.get('status'):
                    continue
                status_count += con.execute('INSERT OR IGNORE INTO statuses VALUES (?,?,?)',
                    (str(status['id'])[:512], str(status['status'])[:64], timestamp(status.get('timestamp')))).rowcount
            names = {str(c.get('wa_id', '')): str(c.get('profile', {}).get('name', ''))[:200] for c in value.get('contacts', [])}
            for message in value.get('messages', []):
                msg_id = str(message.get('id', ''))
                if not msg_id or len(msg_id) > 512:
                    ignored += 1
                    continue
                if con.execute('SELECT 1 FROM messages WHERE id=?', (msg_id,)).fetchone():
                    duplicate += 1
                    continue
                try:
                    phone = normalize_phone('+' + str(message.get('from', '')))
                    if not phone:
                        raise ValueError()
                except ValueError:
                    ignored += 1
                    continue
                at = timestamp(message.get('timestamp'))
                row = con.execute('SELECT * FROM clients WHERE phone_key=?', (phone,)).fetchone()
                if row is None:
                    fields = ClientFields(name=names.get(str(message.get('from'))) or '+' + phone,
                                          phone='+' + phone, wa='+' + phone, created=at[:10]).model_dump(mode='json')
                    data = new_client(fields, at)
                    # Policy preference is a reminder only; it does not trigger an outbound message.
                    from datetime import date, timedelta
                    cfg = json.loads(con.execute("SELECT value FROM meta WHERE key='cfg'").fetchone()[0])
                    data['follow'] = (date.fromisoformat(at[:10]) + timedelta(days=cfg['dias'])).isoformat()
                    client_id = con.execute('INSERT INTO clients(phone_key,data) VALUES (?,?)', (phone, encode(data))).lastrowid
                else:
                    client_id = row['id']
                    data = json.loads(row['data'])
                    # Preserve operator-edited name, origin, stage and commercial fields.
                    data['last'] = max(data.get('last', ''), at[:10])
                    con.execute('UPDATE clients SET data=?,version=version+1 WHERE id=?', (encode(data), client_id))
                kind, text = content(message)
                con.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)', (msg_id, client_id, at, kind, text, utcnow()))
                received += 1
    if received or status_count:
        bump(con)
    # Counts only: no token, phone, query string, signature or conversation body in logs.
    logger.info('webhook processed received=%d duplicate=%d statuses=%d ignored=%d', received, duplicate, status_count, ignored)
    return {'received': received, 'duplicate': duplicate, 'statuses': status_count, 'ignored': ignored}
