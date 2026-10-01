"""Log cumulativo de presença ao longo de todo o encontro (não um snapshot
pontual). Cada ciclo de reconciliação (reconcile_loop, a cada
RECONCILE_SECONDS) chama record(rooms) e atualiza, por grupo (CS1, BS3...),
o primeiro e o último instante em que cada participante foi visto —
incluindo quem já saiu antes do fim, o que um snapshot único não captura.

Estado em memória, reiniciado quando o processo uvicorn reinicia — o que
já acontece uma vez por dia (cron abre o monitor ~10min antes do encontro
e fecha ~10min depois), então cada "vida" do processo corresponde a um
único encontro. Se o processo for reiniciado NO MEIO do encontro (ex.:
durante manutenção), o histórico acumulado até ali é perdido — o
relatório final nesse caso reflete só o que foi visto após o restart.
"""
import threading
from datetime import datetime, timezone

from .cursistas import _normalize

_lock = threading.Lock()
_state = {}  # group -> {name_norm: {"name": str, "first_seen": iso, "last_seen": iso}}


def record(rooms):
    """Atualiza o log cumulativo com o estado atual das salas (lista de
    RoomState, não dicts — chamado direto do reconcile_loop)."""
    now_iso = datetime.now(timezone.utc).isoformat()

    with _lock:
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


def snapshot_group(group):
    """Cópia da tabela acumulada do grupo: {name_norm: {name, first_seen,
    last_seen}}."""
    with _lock:
        return {k: dict(v) for k, v in _state.get(group, {}).items()}


def reset():
    with _lock:
        _state.clear()
