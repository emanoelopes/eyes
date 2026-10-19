"""Stub temporário: data/formadores.json não disponível neste boot.
Detecção de presença do formador fica desativada até o arquivo ser
regenerado (ver skill eti-monitor-salas-meet -> scripts/make_formadores_json.py).
"""
import json
import logging
import unicodedata
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


def _strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _name_matches(formador, name):
    """Compara um nome de participante do Meet contra um nome de formador,
    tolerante a acento/caixa e a apelido/empresa no lugar do nome completo
    (ex.: formador 'Fábia Costa' logado no Meet como 'Fábia Eng. Alim.')."""
    if not formador or not name:
        return False
    f = _strip_accents(formador.strip().lower())
    f_words = [w for w in f.split() if len(w) > 2]
    first_name = f_words[0] if f_words else None
    n = _strip_accents(name.strip().lower())
    matches = sum(1 for w in f_words if w in n)

    # Caso normal: ≥2 palavras em comum (evita falso-positivo de
    # sobrenome/primeiro-nome isolado batendo com outra pessoa).
    if matches >= 2:
        return True

    # Caso "apelido/empresa no Meet": só o primeiro nome bate, desde que
    # seja razoavelmente distintivo (>=4 letras) e apareça como palavra
    # inteira no nome exibido, não como substring de outra palavra.
    if first_name and len(first_name) >= 4 and first_name in n.split():
        return True

    return False


def name_matches_formador(group, name):
    """Versão pública de _name_matches, usada para excluir o formador da
    lista de 'não identificados' sem duplicar a lógica de matching."""
    formador = _MAP.get(group)
    return _name_matches(formador, name)


def find_formador_presence(group, participant_names):
    formador = _MAP.get(group)
    if not formador:
        return None, False, None
    participant_names = participant_names or []

    for name in participant_names:
        if _name_matches(formador, name):
            return formador, True, name

    return formador, False, None
