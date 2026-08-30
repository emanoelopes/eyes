from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from .config import CLIENT_SECRET, TOKEN_FILE, MEET_SCOPES


def get_user_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), MEET_SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CLIENT_SECRET.exists():
            raise RuntimeError(
                f'Arquivo OAuth não encontrado: {CLIENT_SECRET}. '
                'Baixe o cliente OAuth do tipo Aplicativo para computador e salve nesse caminho.'
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), MEET_SCOPES)
        creds = flow.run_local_server(port=0, prompt='consent')
        TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')

    return creds
