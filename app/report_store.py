"""Persistência dos relatórios gerados a cada encontro.

Estratégia: ao final do plantão (chamado pelo cron/tools/fechar_monitor.sh
ou manualmente via POST /api/report/save), captura um snapshot do estado
atual das salas, monta o relatório (app/report.build_report_data) e grava
3 arquivos em data/relatorios/<data>_<dia>/:
  - relatorio.json  (dados estruturados, para reprocessar/agregar depois)
  - relatorio.txt   (texto puro, o mesmo enviado no chat)
  - relatorio.html  (versão com dataviz)

Não versiona nada aqui automaticamente (dados sensíveis: nomes/e-mails de
cursistas) — data/relatorios/ deve entrar no .gitignore, igual
salas.csv/cursistas.json/formadores.json.
"""
import json
from datetime import datetime
from pathlib import Path

from .report import build_report_data, render_text, render_html

REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "relatorios"


def save_report(rooms_snapshot):
    """Recebe STORE.snapshot() (lista de dicts de sala) e persiste os 3
    arquivos do relatório do momento. Retorna o Path do diretório criado."""
    data = build_report_data(rooms_snapshot)

    now = datetime.now()
    slug_dia = now.strftime('%Y-%m-%d')
    slug_hora = now.strftime('%H%M')
    dia_semana = data['dia'].lower()
    out_dir = REPORTS_DIR / f'{slug_dia}_{dia_semana}_{slug_hora}'
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / 'relatorio.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    (out_dir / 'relatorio.txt').write_text(render_text(data), encoding='utf-8')
    (out_dir / 'relatorio.html').write_text(render_html(data), encoding='utf-8')

    return out_dir


def list_saved_reports(limit=30):
    """Lista os relatórios já salvos, mais recentes primeiro."""
    if not REPORTS_DIR.exists():
        return []
    dirs = sorted(
        (d for d in REPORTS_DIR.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    return [d.name for d in dirs[:limit]]
