import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.eti_token_credentials import get_user_credentials
except Exception:
    from .auth import get_user_credentials
from .config import ROOT, ROOMS_CSV, RECONCILE_SECONDS
from .formadores import find_formador_presence
from .google_meet import MeetClient
from .pubsub_listener import PubSubListener
from .rooms import load_rooms
from .state import STORE
from .workspace_events import WorkspaceEventsClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('meet-monitor')

# IPs autorizados a acessar o painel (além de localhost, sempre liberado).
# Configurável via variável de ambiente ALLOWED_IPS (separados por vírgula).
ALLOWED_IPS = {
    ip.strip()
    for ip in os.environ.get('ALLOWED_IPS', '10.102.226.208').split(',')
    if ip.strip()
}
ALWAYS_ALLOWED = {'127.0.0.1', '::1'}

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

    log.info(
        "Evento Workspace recebido: %s | %s",
        event_type,
        conf,
    )

    refresh_for_conference(conf)


RECONCILE_CONCURRENCY = 8


async def refresh_rooms_parallel(rooms, resolve=False):
    """Atualiza as salas em paralelo (limitado por semáforo) para reduzir a
    defasagem entre o estado real do Meet e o que o painel mostra — antes
    a varredura sequencial de 70 salas levava ~28s; em paralelo (limite de
    8 simultâneas) fica bem mais rápido, sem aumentar o volume total de
    chamadas à API do Google (mesmo número de requests, só em lotes).
    """
    sem = asyncio.Semaphore(RECONCILE_CONCURRENCY)
    fn = meet_client.resolve_room if resolve else meet_client.refresh_room

    async def _one(room):
        async with sem:
            await asyncio.to_thread(fn, room)
            STORE.index_space(room)
            if room.conference_record and room.space_name:
                STORE.conference_to_space[room.conference_record] = room.space_name

    await asyncio.gather(*(_one(room) for room in rooms))


async def reconcile_loop():
    while True:
        rooms = list(STORE.rooms.values())
        await refresh_rooms_parallel(rooms)
        update_formador_presence(rooms)
        await asyncio.sleep(RECONCILE_SECONDS)


def update_formador_presence(rooms):
    """Após atualizar todas as salas, verifica em qual sala/célula de cada
    grupo (CS1, BS3, ...) o formador está presente, e propaga essa
    informação para TODAS as salas do grupo (assim a sala principal mostra
    onde o formador está, mesmo que ele esteja numa célula).
    """
    by_group = {}
    for room in rooms:
        group = getattr(room, "group", None)
        if not group:
            continue
        by_group.setdefault(group, []).append(room)

    for group, group_rooms in by_group.items():
        formador = None
        presente = False
        local = None

        for room in group_rooms:
            f, p, _matched_name = find_formador_presence(
                group, room.participant_names
            )
            formador = f
            if p:
                presente = True
                local = room.title
                break

        for room in group_rooms:
            room.formador = formador
            room.formador_presente = presente
            room.formador_localizacao = local


@asynccontextmanager
async def lifespan(app: FastAPI):
    global meet_client, listener, reconcile_task, subscription_info
    rooms = load_rooms(ROOMS_CSV)
    STORE.set_rooms(rooms)
    log.info('Carregadas %d salas de %s', len(rooms), ROOMS_CSV)

    credentials = await asyncio.to_thread(get_user_credentials)
    meet_client = MeetClient(credentials)

    await refresh_rooms_parallel(rooms, resolve=True)

    update_formador_presence(rooms)

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


@app.middleware('http')
async def restrict_by_ip(request: Request, call_next):
    client_ip = request.client.host if request.client else None

    if client_ip not in ALWAYS_ALLOWED and client_ip not in ALLOWED_IPS:
        log.warning('Acesso negado para IP %s (%s)', client_ip, request.url.path)
        return JSONResponse(
            status_code=403,
            content={'detail': 'Acesso não autorizado a partir deste IP.'},
        )

    return await call_next(request)


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
    def is_main(title):
        return str(title).strip().lower().startswith('sala')
    return {
        'rooms': len(rooms),
        'active': sum(1 for r in rooms if r['active']),
        'active_rooms': sum(1 for r in rooms if r['active'] and is_main(r['title'])),
        'active_cells': sum(1 for r in rooms if r['active'] and not is_main(r['title'])),
        'participants': sum(r['participants'] for r in rooms),
        'recording': sum(1 for r in rooms if r['recording']),
        'workspaceSubscription': subscription_info,
    }


GROUP_ORDER = {'CS': 0, 'BS': 1, 'OS': 2}


def _group_sort_key(name):
    import re
    m = re.match(r'^(CS|BS|OS)(\d+)$', name)
    if not m:
        return (99, 0)
    return (GROUP_ORDER.get(m.group(1), 99), int(m.group(2)))


@app.get('/api/report', response_class=PlainTextResponse)
def report():
    rooms = STORE.snapshot()

    def is_main(title):
        return str(title).strip().lower().startswith('sala')

    dia_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
    hoje = dia_semana[datetime.now().weekday()]

    rooms_hoje = [r for r in rooms if r.get('day') == hoje]
    rooms_for_report = rooms_hoje if rooms_hoje else rooms

    by_group = {}
    for r in rooms_for_report:
        g = r.get('group') or 'OUTRAS'
        by_group.setdefault(g, []).append(r)

    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    total_active_rooms = sum(1 for r in rooms_for_report if r['active'] and is_main(r['title']))
    total_active_cells = sum(1 for r in rooms_for_report if r['active'] and not is_main(r['title']))
    total_participants = sum(r['participants'] for r in rooms_for_report)
    total_recording = sum(1 for r in rooms_for_report if r['recording'])
    total_grupos = len(by_group)

    lines = []
    lines.append('RELATÓRIO DE MONITORAMENTO — SALAS DO PLANTÃO ETI')
    lines.append(f'Gerado em: {now} ({hoje})')
    if not rooms_hoje:
        lines.append('(Aviso: nenhuma sala marcada para hoje — mostrando todas as salas.)')
    lines.append('')
    lines.append('RESUMO GERAL')
    lines.append(f'- Salas principais ativas: {total_active_rooms}/{total_grupos}')
    lines.append(f'- Células ativas: {total_active_cells}/{total_grupos * 6}')
    lines.append(f'- Participantes conectados (total): {total_participants}')
    lines.append(f'- Gravações em andamento: {total_recording}')
    lines.append('')
    lines.append('DETALHAMENTO POR SALA')
    lines.append('-' * 50)

    for group in sorted(by_group, key=_group_sort_key):
        items = by_group[group]
        main_room = next((r for r in items if is_main(r['title'])), None)
        cells_active = sum(1 for r in items if r['active'] and not is_main(r['title']))
        participants_total = sum(r['participants'] for r in items)
        formador = next((r.get('formador') for r in items if r.get('formador')), None)
        presente = any(r.get('formador_presente') for r in items)
        local = next((r.get('formador_localizacao') for r in items if r.get('formador_localizacao')), None)

        status_sala = 'ATIVA' if (main_room and main_room['active']) else 'INATIVA'
        gravando = 'Sim' if (main_room and main_room['recording']) else 'Não'

        lines.append(f'{group}' + (f' — Formador: {formador}' if formador else ' — Formador: não identificado'))
        lines.append(f'  Sala principal: {status_sala} | Gravando: {gravando}')
        lines.append(f'  Participantes (sala + células): {participants_total} | Células ativas: {cells_active}/6')
        if formador:
            if presente:
                lines.append(f'  Presença do formador: confirmada em "{local}"')
            else:
                lines.append('  Presença do formador: NÃO detectada em nenhuma sala/célula do grupo')
        lines.append('')

    return '\n'.join(lines)
