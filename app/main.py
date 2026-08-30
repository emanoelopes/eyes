import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import get_user_credentials
from .config import ROOT, ROOMS_CSV, RECONCILE_SECONDS
from .google_meet import MeetClient
from .pubsub_listener import PubSubListener
from .rooms import load_rooms
from .state import STORE
from .workspace_events import WorkspaceEventsClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('meet-monitor')

meet_client = None
listener = None
reconcile_task = None
subscription_info = None


def conference_name_from_payload(payload):
    for key in ('conferenceRecord', 'participantSession', 'recording'):
        obj = payload.get(key) or {}
        name = obj.get('name', '')
        if name.startswith('conferenceRecords/'):
            parts = name.split('/')
            return '/'.join(parts[:2])
    return None


def refresh_for_conference(conference_name):
    if not conference_name:
        return
    try:
        conference = meet_client.get_conference(conference_name)
        space = conference.get('space')
        if not space:
            return
        STORE.conference_to_space[conference_name] = space
        room = STORE.room_for_space(space)
        if room:
            meet_client.refresh_room(room)
    except Exception:
        log.exception('Falha atualizando %s', conference_name)


def handle_event(event_type, payload, attributes):
    conf = conference_name_from_payload(payload)
    if event_type.endswith('.ended') and '.conference.' in event_type:
        refresh_for_conference(conf)
        return
    refresh_for_conference(conf)


async def reconcile_loop():
    while True:
        rooms = list(STORE.rooms.values())
        for room in rooms:
            await asyncio.to_thread(meet_client.refresh_room, room)
            STORE.index_space(room)
        await asyncio.sleep(RECONCILE_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global meet_client, listener, reconcile_task, subscription_info
    rooms = load_rooms(ROOMS_CSV)
    STORE.set_rooms(rooms)
    log.info('Carregadas %d salas de %s', len(rooms), ROOMS_CSV)

    credentials = await asyncio.to_thread(get_user_credentials)
    meet_client = MeetClient(credentials)

    for room in rooms:
        await asyncio.to_thread(meet_client.resolve_room, room)
        STORE.index_space(room)
        if room.conference_record and room.space_name:
            STORE.conference_to_space[room.conference_record] = room.space_name

    try:
        events = WorkspaceEventsClient(credentials)
        subscription_info = await asyncio.to_thread(events.ensure_user_subscription)
        log.info('Workspace Events ativo: %s', subscription_info.get('name'))
    except Exception:
        log.exception('Workspace Events não pôde ser configurado automaticamente')

    try:
        listener = PubSubListener(handle_event)
        await asyncio.to_thread(listener.start)
        log.info('Listener Pub/Sub iniciado')
    except Exception:
        log.exception('Pub/Sub não iniciado. Confira ADC/service account no README.')

    reconcile_task = asyncio.create_task(reconcile_loop())
    yield

    if reconcile_task:
        reconcile_task.cancel()
    if listener:
        await asyncio.to_thread(listener.stop)


app = FastAPI(title='Monitor Google Meet', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/api/rooms')
def rooms():
    data = STORE.snapshot()
    data.sort(key=lambda x: (not x['active'], x['title'].lower()))
    return data


@app.get('/api/status')
def status():
    rooms = STORE.snapshot()
    return {
        'rooms': len(rooms),
        'active': sum(1 for r in rooms if r['active']),
        'participants': sum(r['participants'] for r in rooms),
        'recording': sum(1 for r in rooms if r['recording']),
        'workspaceSubscription': subscription_info,
    }
