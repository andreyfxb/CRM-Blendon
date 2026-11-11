"""Run the local synthetic fixture and frontend tests, never a real WhatsApp number."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = {**os.environ, 'PYTHONPATH': str(root)}
server = subprocess.Popen([sys.executable, 'tests/fixture_server.py'], cwd=root, env=env)
try:
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError('O servidor de teste encerrou antes de iniciar.')
        try:
            urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=0.5)
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError('Servidor de teste indisponível. Confira se as portas 5500 e 8765 estão livres.')
    suite = 'tests/frontend.cjs' if '--browser' in sys.argv else 'tests/frontend-dom.cjs'
    result = subprocess.run(['node', suite], cwd=root, env=env)
    raise SystemExit(result.returncode)
finally:
    server.terminate()
    server.wait(timeout=10)
