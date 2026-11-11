"""Create a consistent, private SQLite backup using the online backup API."""
import argparse
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source')
parser.add_argument('destination')
args = parser.parse_args()
source = Path(args.source).resolve()
destination = Path(args.destination).resolve()
if not source.is_file() or source == destination or destination.exists():
    parser.error('A origem precisa existir e o destino deve ser um arquivo novo e diferente.')
destination.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)
    if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('Falha na verificação do backup.')
try:
    destination.chmod(0o600)
except OSError:
    pass
print('Backup consistente criado. Guarde o arquivo em armazenamento privado.')
