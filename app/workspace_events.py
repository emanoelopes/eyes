import time
from google.auth.transport.requests import AuthorizedSession
from googleapiclient.discovery import build
from .config import EVENT_TYPES, TOPIC_NAME


class WorkspaceEventsClient:
    def __init__(self, credentials):
        self.credentials = credentials
        self.session = AuthorizedSession(credentials)

    def get_user_id(self):
        service = build('people', 'v1', credentials=self.credentials, cache_discovery=False)
        person = service.people().get(resourceName='people/me', personFields='names').execute()
        name = person.get('resourceName', '')
        if not name.startswith('people/'):
            raise RuntimeError('Não foi possível identificar o ID do usuário Google.')
        return name.split('/', 1)[1]

    def _wait_operation(self, operation):
        name = operation.get('name')
        if not name:
            return operation
        for _ in range(30):
            r = self.session.get(f'https://workspaceevents.googleapis.com/v1/{name}', timeout=20)
            r.raise_for_status()
            data = r.json()
            if data.get('done'):
                if 'error' in data:
                    raise RuntimeError(str(data['error']))
                return data.get('response', data)
            time.sleep(1)
        raise RuntimeError('Timeout aguardando criação da assinatura Workspace Events.')

    def ensure_user_subscription(self):
        if not TOPIC_NAME:
            raise RuntimeError('GOOGLE_CLOUD_PROJECT não configurado no .env')
        user_id = self.get_user_id()
        target = f'//cloudidentity.googleapis.com/users/{user_id}'
        event_type = EVENT_TYPES[0]
        params = {
            'filter': f'event_types:"{event_type}" AND target_resource="{target}"',
            'pageSize': 10,
        }
        r = self.session.get('https://workspaceevents.googleapis.com/v1/subscriptions', params=params, timeout=20)
        r.raise_for_status()
        found = r.json().get('subscriptions', [])

        if found:
            sub = found[0]
            name = sub['name']
            patch = self.session.patch(
                f'https://workspaceevents.googleapis.com/v1/{name}',
                params={'updateMask': 'ttl'},
                json={'name': name, 'ttl': '0s'},
                timeout=20,
            )
            if patch.ok:
                return self._wait_operation(patch.json())
            return sub

        body = {
            'targetResource': target,
            'eventTypes': EVENT_TYPES,
            'notificationEndpoint': {'pubsubTopic': TOPIC_NAME},
            'payloadOptions': {'includeResource': False},
            'ttl': '0s',
        }
        r = self.session.post('https://workspaceevents.googleapis.com/v1/subscriptions', json=body, timeout=20)
        if not r.ok:
            raise RuntimeError(f'Falha criando assinatura Workspace Events: {r.status_code} {r.text}')
        return self._wait_operation(r.json())
