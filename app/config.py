from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
TOPIC_ID = os.getenv('PUBSUB_TOPIC_ID', 'meet-monitor-events').strip()
PUBSUB_SUBSCRIPTION_ID = os.getenv('PUBSUB_SUBSCRIPTION_ID', 'meet-monitor-events-sub').strip()
ROOMS_CSV = ROOT / os.getenv('ROOMS_CSV', 'data/salas.csv')
CLIENT_SECRET = ROOT / 'credentials' / 'client_secret.json'
TOKEN_FILE = ROOT / 'token.json'
RUNTIME_DIR = ROOT / '.runtime'
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', '8000'))
RECONCILE_SECONDS = int(os.getenv('RECONCILE_SECONDS', '45'))

TOPIC_NAME = f'projects/{PROJECT_ID}/topics/{TOPIC_ID}' if PROJECT_ID else ''
PUBSUB_SUBSCRIPTION_NAME = (
    f'projects/{PROJECT_ID}/subscriptions/{PUBSUB_SUBSCRIPTION_ID}' if PROJECT_ID else ''
)

MEET_SCOPES = [
    'https://www.googleapis.com/auth/meetings.space.readonly',
    'https://www.googleapis.com/auth/userinfo.profile',
]

EVENT_TYPES = [
    'google.workspace.meet.conference.v2.started',
    'google.workspace.meet.conference.v2.ended',
    'google.workspace.meet.participant.v2.joined',
    'google.workspace.meet.participant.v2.left',
    'google.workspace.meet.recording.v2.started',
    'google.workspace.meet.recording.v2.ended',
]
