"""Log cumulativo de presença ao longo de todo o encontro (não um snapshot
pontual). Cada ciclo de reconciliação (reconcile_loop, a cada
RECONCILE_SECONDS) chama record(rooms) e atualiza, por grupo (CS1, BS3...),
o primeiro e o último instante em que cada participante foi visto —
incluindo quem já saiu antes do fim, o que um snapshot único não captura.

Persistência em disco (data/attendance_state.json): o estado é salvo a
cada record() (debounced — no máximo 1 escrita a cada
_SAVE_INTERVAL_SECONDS, para não martelar I/O a cada ciclo de 45s) e
recarregado no boot do uvicorn, DESDE QUE o arquivo salvo seja do mesmo
dia-base do encontro atual (campo "base_date"). Isso cobre o cenário que
o só-em-memória não cobria: se o processo cair/reiniciar NO MEIO do
encontro (travamento, manutenção manual, OOM), o histórico acumulado até
ali sobrevive e o relatório final continua completo.

Se o arquivo for de um dia anterior (ou de uma versão incompatível), é
ignorado e o estado começa vazio — nunca mistura presença de encontros
diferentes.
"""
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .cursistas import _normalize

log = logging.getLogger("meet-monitor.attendance")

_lock = threading.Lock()
_state = {}  # group -> {name_norm: {"name": str, "first_seen": iso, "last_seen": iso}}
_base_date = None  # data (YYYY-MM-DD, hora local) do encontro em andamento

_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "attendance_state.json"
_SAVE_INTERVAL_SECONDS = 30
_last_saved_at = 0.0


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def load():
    """Carrega o estado salvo em disco, SE for do mesmo dia de hoje (ou
    seja, do encontro em andamento). Chamar uma vez no boot, antes do
    primeiro record(). Idempotente — se não houver arquivo ou for de outro
    dia, começa com estado vazio (comportamento anterior)."""
    global _state, _base_date

    with _lock:
        _base_date = _today_str()

        if not _STATE_PATH.exists():
            _state = {}
            return

        try:
            payload = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Falha ao ler %s — iniciando log de presença vazio", _STATE_PATH)
            _state = {}
            return

        if payload.get("base_date") != _base_date:
            log.info(
                "attendance_state.json é de outro dia (%s != %s) — iniciando log vazio",
                payload.get("base_date"), _base_date,
            )
            _state = {}
            return

        _state = payload.get("groups") or {}
        total = sum(len(v) for v in _state.values())
        log.info(
            "Log de presença recuperado de %s: %d grupos / %d participantes",
            _STATE_PATH, len(_state), total,
        )


def _save_locked():
    """Grava o estado atual em disco. Chamar sempre com _lock já adquirido."""
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _STATE_PATH.with_suffix(".json.tmp")
    payload = {"base_date": _base_date, "groups": _state}
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(_STATE_PATH)  # escrita atômica — nunca deixa arquivo truncado


def record(rooms):
    """Atualiza o log cumulativo com o estado atual das salas (lista de
    RoomState, não dicts — chamado direto do reconcile_loop). Persiste em
    disco no máximo a cada _SAVE_INTERVAL_SECONDS (debounce)."""
    import time as _time

    global _base_date, _last_saved_at
    now_iso = datetime.now(timezone.utc).isoformat()

    with _lock:
        if _base_date is None:
            _base_date = _today_str()

        for r in rooms:
            group = getattr(r, "group", None)
            if not group:
                continue

            bucket = _state.setdefault(group, {})

            for s in (getattr(r, "participant_sessions", None) or []):
                name = s.get("name")
                nn = _normalize(name)
                if not nn:
                    continue

                joined = s.get("joined_at") or now_iso

                if nn not in bucket:
                    bucket[nn] = {
                        "name": str(name).strip(),
                        "first_seen": joined,
                        "last_seen": now_iso,
                    }
                else:
                    entry = bucket[nn]
                    if joined < entry["first_seen"]:
                        entry["first_seen"] = joined
                    entry["last_seen"] = now_iso

        now_mono = _time.monotonic()
        if now_mono - _last_saved_at >= _SAVE_INTERVAL_SECONDS:
            try:
                _save_locked()
                _last_saved_at = now_mono
            except Exception:
                log.exception("Falha ao persistir %s", _STATE_PATH)


def save_now():
    """Força a gravação imediata (ignora o debounce) — útil antes de
    encerrar o processo (fechar_monitor.sh já chama /api/report/save, que
    por sua vez não depende disso, mas é uma rede de segurança extra)."""
    with _lock:
        try:
            _save_locked()
        except Exception:
            log.exception("Falha ao persistir %s", _STATE_PATH)


def snapshot_group(group):
    """Cópia da tabela acumulada do grupo: {name_norm: {name, first_seen,
    last_seen}}."""
    with _lock:
        return {k: dict(v) for k, v in _state.get(group, {}).items()}


def reset():
    global _base_date
    with _lock:
        _state.clear()
        _base_date = _today_str()
        try:
            if _STATE_PATH.exists():
                _STATE_PATH.unlink()
        except Exception:
            pass
