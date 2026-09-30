"""Gera data/cursistas.json (mapa sala -> lista de nomes completos de
cursistas) a partir da aba 'Turmas' da planilha GERAL-Formadores, para uso
na heurística de nome completo do relatório de presença (app/main.py).

Copie este script para /tmp/eyes/tools/make_cursistas_json.py (o /tmp/eyes
é efêmero, ver SKILL.md) e rode com o venv do ETI:
    /home/emanoel/ETI/.venv/bin/python tools/make_cursistas_json.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.eti_token_credentials import get_user_credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = '1O5bCZwsXXHm7TSiLTjhtks7FvHzhPBFT2vhPoLtoqCM'
OUTPUT = Path(__file__).resolve().parent.parent / 'data' / 'cursistas.json'


def main():
    creds = get_user_credentials()
    svc = build('sheets', 'v4', credentials=creds)

    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='Turmas!A1:K2000',
    ).execute()
    values = resp.get('values', [])

    header = values[0]
    idx = {h: i for i, h in enumerate(header)}
    rows = [r for r in values[1:] if r and len(r) >= len(header)]

    minhas = [r for r in rows if r[idx['Apoio de TI']].strip() == 'Emanoel']

    por_sala = {}
    for r in minhas:
        nome_sala = r[idx['Nome Sala']].strip()
        cursista = r[idx['Cursista']].strip()
        if nome_sala and cursista:
            por_sala.setdefault(nome_sala, set()).add(cursista)

    resultado = {sala: sorted(nomes) for sala, nomes in por_sala.items()}

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    total = sum(len(v) for v in resultado.values())
    print(f'Gerado {len(resultado)} salas / {total} cursistas em {OUTPUT}')


if __name__ == '__main__':
    main()
