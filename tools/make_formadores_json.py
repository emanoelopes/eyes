"""Gera data/formadores.json (mapa sala -> nome do formador) a partir da
aba 'Turmas' da planilha GERAL-Formadores, para uso na detecção de
presença do formador no dashboard (app/formadores.py).

IMPORTANTE: usa o formador MAJORITÁRIO por sala (moda), não a última
linha encontrada. A aba 'Turmas' tem uma linha por cursista, e uma
alteração pontual de cursista/formador registrada incorretamente numa
única linha pode ficar por último na planilha sem refletir o formador
real da sala — pegar "a última linha" já causou um erro real (BS2
apareceu com "Ana Karoliny Alves da Silva" por causa de 1 linha isolada,
quando as outras 29 linhas da mesma sala diziam "Sara Rebeca Aguiar de
Carvalho", que é o formador correto).

Copie este script para /tmp/eyes/tools/make_formadores_json.py (o
/tmp/eyes é efêmero, ver SKILL.md) e rode com o venv do ETI:
    /home/emanoel/ETI/.venv/bin/python tools/make_formadores_json.py
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.eti_token_credentials import get_user_credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = '1O5bCZwsXXHm7TSiLTjhtks7FvHzhPBFT2vhPoLtoqCM'
OUTPUT = Path(__file__).resolve().parent.parent / 'data' / 'formadores.json'


def main():
    import json

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

    # Agrupa por sala, contando ocorrências de cada formador citado.
    por_sala = collections.defaultdict(collections.Counter)
    for r in minhas:
        nome_sala = r[idx['Nome Sala']].strip()
        formador = r[idx['Formador']].strip()
        if nome_sala and formador:
            por_sala[nome_sala][formador] += 1

    resultado = {}
    avisos = []
    for sala, contagem in por_sala.items():
        formador_majoritario, count = contagem.most_common(1)[0]
        resultado[sala] = formador_majoritario
        if len(contagem) > 1:
            outros = {f: c for f, c in contagem.items() if f != formador_majoritario}
            avisos.append(
                f'{sala}: {len(contagem)} formadores distintos na planilha '
                f'(escolhido "{formador_majoritario}" com {count} linhas; '
                f'outros: {outros})'
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    print(f'Gerado {len(resultado)} formadores em {OUTPUT}')
    if avisos:
        print('\nAVISOS (planilha tem mais de um formador citado para a mesma sala):')
        for a in avisos:
            print(' -', a)


if __name__ == '__main__':
    main()
