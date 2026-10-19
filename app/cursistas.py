"""Heurística para resolver o nome completo do cursista a partir do nome
exibido no Google Meet (que costuma vir incompleto, abreviado, com apelido
ou até vazio de sobrenome), cruzando com a lista oficial de cursistas por
sala (data/cursistas.json, gerado por tools/make_cursistas_json.py a partir
da aba 'Turmas' da planilha GERAL-Formadores).

Estratégia (nessa ordem, primeira que bater com confiança suficiente):
1. Igualdade exata (normalizada: sem acento, minúsculas, espaços colapsados).
2. Todas as palavras do nome do Meet aparecem como palavras do candidato
   (ex. "nalu" não bate com nada, mas "Sara Rebeca" bate com "SARA REBECA
   AGUIAR DE CARVALHO").
3. Maior sobreposição de tokens (Jaccard) acima de um limiar, desde que haja
   pelo menos 2 tokens em comum (evita falso-positivo por sobrenome único
   ou primeiro nome comum tipo "Maria").
Se nada bater com confiança, devolve o nome do Meet como veio (sem inventar).
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "cursistas.json"
_MAP = {}
if _PATH.exists():
    try:
        _MAP = json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        _MAP = {}


def _strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _normalize(s):
    s = _strip_accents(str(s or "")).lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s):
    return set(_normalize(s).split())


# Palavras curtas/comuns demais para contar como "token forte" no matching
# (evita bater só por "maria", "de", "da", "dos"...).
_STOPWORDS = {"de", "da", "do", "das", "dos", "e"}

# Frequência de cada token na lista oficial de CADA turma — usado para
# identificar palavras "genéricas" (Maria, Silva, José, Sousa...) que,
# sozinhas ou em dupla, NÃO servem para confirmar identidade: um nome do
# Meet como "Alcione Maria da Silva Santos Santos" bate em 2 tokens
# ("maria", "silva") com a cursista real "MARIA ELZA DA SILVA" só por
# coincidência de sobrenomes/primeiros-nomes comuns — sem nenhum token
# realmente distintivo em comum ("elza" não aparece, "alcione" não existe
# na turma). Exigir que pelo menos 1 token do match seja raro na turma
# evita esse falso-positivo perigoso (mascara intruso como cursista real).
_TOKEN_FREQ_BY_GROUP = {}


def _token_freq(group):
    if group not in _TOKEN_FREQ_BY_GROUP:
        counter = Counter()
        for cand in _MAP.get(group) or []:
            for t in _tokens(cand) - _STOPWORDS:
                counter[t] += 1
        _TOKEN_FREQ_BY_GROUP[group] = counter
    return _TOKEN_FREQ_BY_GROUP[group]


def _has_discriminative_overlap(overlap, group):
    """True se ao menos 1 token do overlap for raro na turma (aparece em
    menos de 3 candidatos distintos da lista oficial)."""
    freq = _token_freq(group)
    return any(freq.get(t, 0) < 3 for t in overlap)


def resolve_full_name(meet_name, group):
    """Retorna (nome_resolvido, encontrado: bool).
    `nome_resolvido` é o nome completo do cursista quando a heurística acha
    um candidato confiável; caso contrário, devolve `meet_name` original.
    """
    candidatos = _MAP.get(group) or []
    if not candidatos or not meet_name or not str(meet_name).strip():
        return meet_name, False

    meet_norm = _normalize(meet_name)
    meet_tokens = _tokens(meet_name) - _STOPWORDS

    if not meet_tokens:
        return meet_name, False

    # 1) Igualdade exata normalizada.
    for cand in candidatos:
        if _normalize(cand) == meet_norm:
            return cand, True

    melhor = None
    melhor_score = 0.0
    melhor_overlap = 0
    melhor_overlap_set = set()

    for cand in candidatos:
        cand_tokens = _tokens(cand) - _STOPWORDS
        if not cand_tokens:
            continue
        overlap = meet_tokens & cand_tokens
        if not overlap:
            continue

        # 2) Todo o nome do Meet está contido no candidato (subconjunto de
        # tokens) — cobre "Sara Rebeca" -> "Sara Rebeca Aguiar de Carvalho".
        if meet_tokens.issubset(cand_tokens):
            score = 1.0 + len(overlap) / max(len(cand_tokens), 1)
        else:
            # 3) Jaccard simples entre os dois conjuntos de tokens.
            score = len(overlap) / len(meet_tokens | cand_tokens)

        if score > melhor_score:
            melhor_score = score
            melhor = cand
            melhor_overlap = len(overlap)
            melhor_overlap_set = overlap

    # Exige pelo menos 2 tokens fortes em comum (ou nome do Meet inteiro
    # contido no candidato com 1 token forte, para nomes de 1 palavra só)
    # E que pelo menos 1 desses tokens seja raro na turma — evita confirmar
    # alguém só por coincidência de nomes genéricos como "Maria"/"Silva"
    # (ver _has_discriminative_overlap: já causou um falso-positivo real,
    # mascarando um intruso como se fosse uma cursista matriculada).
    overlap_ok = melhor_overlap >= 2 or (
        meet_tokens.issubset(_tokens(melhor) - _STOPWORDS) if melhor else False
    ) and melhor_overlap >= 1 and len(meet_tokens) >= 2

    if melhor and overlap_ok and _has_discriminative_overlap(melhor_overlap_set, group):
        return melhor, True

    return meet_name, False


def roster_for_group(group):
    """Lista oficial (nomes completos) de cursistas matriculados na sala,
    conforme a aba Turmas da planilha GERAL-Formadores."""
    return list(_MAP.get(group) or [])


def absent_students(group, present_full_names):
    """Retorna, em ordem alfabética, os nomes da lista oficial do grupo que
    NÃO batem com nenhum nome já resolvido/presente (`present_full_names`:
    coleção de nomes completos ou nomes do Meet já processados por
    resolve_full_name). Comparação normalizada (acento/caixa)."""
    presentes_norm = {_normalize(n) for n in present_full_names}
    return sorted(
        (c for c in roster_for_group(group) if _normalize(c) not in presentes_norm),
        key=lambda s: s.lower(),
    )
