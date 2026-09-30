"""Conector de credenciais que reaproveita o token OAuth já usado pelo
projeto ETI (conta suporte.eti.01), em vez de exigir um fluxo OAuth
Desktop separado.
"""
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

TOKEN_PATH = Path('/home/emanoel/.hermes/profiles/eti/google_token.json')


def get_user_credentials():
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(f'Token ETI não encontrado em {TOKEN_PATH}')

    data = json.loads(TOKEN_PATH.read_text(encoding='utf-8'))

    # Usa os escopos REAIS gravados no token (não força um conjunto fixo,
    # pois o token ETI não tem userinfo.profile e isso causa invalid_scope
    # no refresh se forçado).
    scopes = data.get('scopes') or data.get('scope', '').split()

    creds = Credentials(
        token=data.get('token') or data.get('access_token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=scopes,
    )

    if not creds.valid:
        creds.refresh(Request())
        # Persiste o token atualizado de volta no arquivo ETI.
        data['token'] = creds.token
        if creds.expiry:
            data['expiry'] = creds.expiry.isoformat() + 'Z'
        TOKEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    return creds
