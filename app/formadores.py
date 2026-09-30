"""Stub temporário: data/formadores.json não disponível neste boot.
Detecção de presença do formador fica desativada até o arquivo ser
regenerado (ver skill eti-monitor-salas-meet -> scripts/make_formadores_json.py).
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent.parent / "data" / "formadores.json"
_MAP = {}
if _PATH.exists():
    try:
        _MAP = json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.warning("Falha ao carregar %s", _PATH)
else:
    log.warning("data/formadores.json ausente — presença de formador desativada")


def find_formador_presence(group, participant_names):
    formador = _MAP.get(group)
    if not formador:
        return None, False, None
    participant_names = participant_names or []
    for name in participant_names:
        if not name:
            continue
        n = name.strip().lower()
        f = formador.strip().lower()
        f_words = [w for w in f.split() if len(w) > 2]
        matches = sum(1 for w in f_words if w in n)
        if matches >= 2:
            return formador, True, name
    return formador, False, None
