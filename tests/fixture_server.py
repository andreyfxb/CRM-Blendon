import functools
import http.server
import tempfile
import threading
import uvicorn
from backend.app import create_app
from backend.config import Settings
from backend.security import password_hash
with tempfile.TemporaryDirectory() as folder:
    server=http.server.ThreadingHTTPServer(('127.0.0.1',5500),functools.partial(http.server.SimpleHTTPRequestHandler,directory='.'))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    settings=Settings(folder+'/test.sqlite3','admin',password_hash('Only-local-test-123!'),('http://127.0.0.1:5500',),'test-secret','test-verify','test-phone-id')
    uvicorn.run(create_app(settings),host='127.0.0.1',port=8765,access_log=False,log_level='warning')
