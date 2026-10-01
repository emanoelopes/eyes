"""Monta os dados do relatório de presença/monitoramento (uma vez) e
oferece renderizadores para texto puro (WhatsApp/e-mail) e HTML com
dataviz (Chart.js via CDN). Usado por app/main.py nos endpoints
/api/report, /api/report.json, /api/report.html e /api/report/save, e
por app/report_store.py na persistência automática ao final do plantão.

IMPORTANTE: o relatório cobre o encontro DO INÍCIO AO FIM, não só o
instante em que foi gerado — usa app/attendance.py (log cumulativo
atualizado a cada ciclo de reconciliação) em vez do snapshot atual das
salas. Quem entrou e já saiu antes da geração do relatório ainda aparece,
com o tempo total que ficou conectado e indicação de que já saiu.
"""
from datetime import datetime, timezone

from . import attendance
from .cursistas import resolve_full_name, absent_students, roster_for_group, _normalize

DIA_SEMANA = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
GROUP_ORDER = {'CS': 0, 'BS': 1, 'OS': 2}


def _group_sort_key(name):
    import re
    m = re.match(r'^(CS|BS|OS)(\d+)$', name)
    if not m:
        return (99, 0)
    return (GROUP_ORDER.get(m.group(1), 99), int(m.group(2)))


def _is_main(title):
    return str(title).strip().lower().startswith('sala')


def _norm_name(n):
    return str(n or '').strip().lower()


def _unique_count(room_list):
    names = set()
    anon = 0
    for r in room_list:
        for n in (r.get('participant_names') or []):
            nn = _norm_name(n)
            if nn:
                names.add(nn)
            else:
                anon += 1
    return len(names) + anon


def _parse_iso(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except Exception:
        return None


def _format_duration(minutes):
    if minutes is None:
        return None
    h, m = divmod(minutes, 60)
    return f'{h}h{m:02d}min' if h else f'{m}min'


def _format_hora(iso):
    dt = _parse_iso(iso)
    return dt.astimezone().strftime('%H:%M') if dt else None


def build_report_data(rooms):
    """Monta a estrutura de dados do relatório a partir de STORE.snapshot()
    (para saber o estado ATUAL de cada sala/formador) combinado com
    app/attendance.py (para a presença acumulada do encontro inteiro).
    Não depende do FastAPI — pode ser chamada de qualquer contexto
    (endpoint, script de persistência, teste)."""
    now = datetime.now()
    now_utc = datetime.now(timezone.utc)
    hoje = DIA_SEMANA[now.weekday()]

    rooms_hoje = [r for r in rooms if r.get('day') == hoje]
    rooms_for_report = rooms_hoje if rooms_hoje else rooms
    usou_filtro_hoje = bool(rooms_hoje)

    by_group = {}
    for r in rooms_for_report:
        g = r.get('group') or 'OUTRAS'
        by_group.setdefault(g, []).append(r)

    groups_out = []
    for group in sorted(by_group, key=_group_sort_key):
        items = by_group[group]
        main_room = next((r for r in items if _is_main(r['title'])), None)
        cells_active = sum(1 for r in items if r['active'] and not _is_main(r['title']))
        formador = next((r.get('formador') for r in items if r.get('formador')), None)
        presente = any(r.get('formador_presente') for r in items)
        local = next((r.get('formador_localizacao') for r in items if r.get('formador_localizacao')), None)

        # Quem está conectado NESTE EXATO MOMENTO (para marcar "ainda
        # conectado" x "já saiu" na lista cumulativa).
        currently_connected = set()
        for r in items:
            for s in (r.get('participant_sessions') or []):
                nn = _normalize(s.get('name'))
                if nn:
                    currently_connected.add(nn)

        cumulative = attendance.snapshot_group(group)

        presence = []
        nomes_resolvidos_completos = []
        for nn, entry in cumulative.items():
            nome = entry['name']
            completo, achou = resolve_full_name(nome, group)
            nomes_resolvidos_completos.append(completo if achou else nome)

            first_dt = _parse_iso(entry['first_seen'])
            last_dt = _parse_iso(entry['last_seen'])
            ainda_conectado = nn in currently_connected
            fim = now_utc if ainda_conectado else (last_dt or now_utc)
            minutos = None
            if first_dt:
                minutos = max(int((fim - first_dt).total_seconds() // 60), 0)

            presence.append({
                'meet_name': nome,
                'full_name': completo if achou else None,
                'resolved': bool(achou and completo.strip().lower() != nome.strip().lower()),
                'label': completo if achou else nome,
                'joined_at': entry['first_seen'],
                'hora_entrada': _format_hora(entry['first_seen']),
                'hora_saida': None if ainda_conectado else _format_hora(entry['last_seen']),
                'ainda_conectado': ainda_conectado,
                'duration_minutes': minutos,
                'duration_label': _format_duration(minutos),
            })
        presence.sort(key=lambda p: p['label'].lower())

        roster = roster_for_group(group)
        ausentes = absent_students(group, nomes_resolvidos_completos) if roster else []

        groups_out.append({
            'group': group,
            'formador': formador,
            'formador_presente': presente,
            'formador_localizacao': local,
            'status_sala_ativa': bool(main_room and main_room['active']),
            'gravando': bool(main_room and main_room['recording']),
            'participants_total': len(presence),
            'cells_active': cells_active,
            'cells_total': 6,
            'presence': presence,
            'absent': ausentes,
            'roster_size': len(roster),
        })

    total_active_rooms = sum(1 for r in rooms_for_report if r['active'] and _is_main(r['title']))
    total_active_cells = sum(1 for r in rooms_for_report if r['active'] and not _is_main(r['title']))
    total_participants = sum(len(g['presence']) for g in groups_out)
    total_recording = sum(1 for r in rooms_for_report if r['recording'])

    return {
        'generated_at': now.isoformat(),
        'generated_at_label': now.strftime('%d/%m/%Y %H:%M'),
        'dia': hoje,
        'used_today_filter': usou_filtro_hoje,
        'total_grupos': len(by_group),
        'total_active_rooms': total_active_rooms,
        'total_active_cells': total_active_cells,
        'total_participants': total_participants,
        'total_recording': total_recording,
        'groups': groups_out,
    }


def render_text(data):
    lines = []
    lines.append('RELATÓRIO DE MONITORAMENTO — SALAS DO PLANTÃO ETI')
    lines.append(f"Gerado em: {data['generated_at_label']} ({data['dia']})")
    lines.append('Cobertura: do início do encontro até agora (quem já saiu também aparece,')
    lines.append(' marcado como [SAIU], com o período em que esteve conectado).')
    if not data['used_today_filter']:
        lines.append('(Aviso: nenhuma sala marcada para hoje — mostrando todas as salas.)')
    lines.append('')
    lines.append('RESUMO GERAL')
    lines.append(f"- Salas principais ativas: {data['total_active_rooms']}/{data['total_grupos']}")
    lines.append(f"- Células ativas: {data['total_active_cells']}/{data['total_grupos'] * 6}")
    lines.append(f"- Participantes únicos que passaram pelo encontro (total): {data['total_participants']}")
    lines.append(f"- Gravações em andamento: {data['total_recording']}")
    lines.append('(Contagem de participantes deduplicada por nome — um cursista logado')
    lines.append(' simultaneamente na sala principal e numa célula conta uma única vez.)')
    lines.append('(A lista de "Ausentes" cruza com a matrícula oficial pelo nome; cursistas')
    lines.append(' que aparecem no Meet com nome muito abreviado/incompleto podem constar')
    lines.append(' como ausentes por engano — confirme visualmente antes de dar falta.)')
    lines.append('')
    lines.append('DETALHAMENTO POR SALA')
    lines.append('-' * 50)

    for g in data['groups']:
        status_sala = 'ATIVA' if g['status_sala_ativa'] else 'INATIVA'
        gravando = 'Sim' if g['gravando'] else 'Não'

        lines.append(f"{g['group']}" + (f" — Formador: {g['formador']}" if g['formador'] else ' — Formador: não identificado'))
        lines.append(f"  Sala principal: {status_sala} | Gravando: {gravando}")
        lines.append(f"  Participantes únicos (sala + células): {g['participants_total']} | Células ativas: {g['cells_active']}/{g['cells_total']}")
        if g['formador']:
            if g['formador_presente']:
                lines.append(f"  Presença do formador: confirmada em \"{g['formador_localizacao']}\"")
            else:
                lines.append('  Presença do formador: NÃO detectada em nenhuma sala/célula do grupo')

        if g['presence']:
            lines.append(f"  Lista de presença ({len(g['presence'])}):")
            for i, p in enumerate(g['presence'], start=1):
                label = p['label']
                if p['resolved']:
                    label = f"{p['full_name']} (Meet: \"{p['meet_name']}\")"
                if not p['ainda_conectado']:
                    label += ' [SAIU]'
                if p['hora_entrada'] and p['duration_label']:
                    if p['ainda_conectado']:
                        label += f" — entrou às {p['hora_entrada']}, conectado há {p['duration_label']}"
                    else:
                        label += f" — {p['hora_entrada']} até {p['hora_saida']} (ficou {p['duration_label']})"
                lines.append(f'    {i}. {label}')
        else:
            lines.append('  Lista de presença: nenhum participante identificado.')

        if g['roster_size']:
            lines.append(f"  Ausentes ({len(g['absent'])} de {g['roster_size']} matriculados):")
            if g['absent']:
                for i, nome in enumerate(g['absent'], start=1):
                    lines.append(f'    {i}. {nome}')
            else:
                lines.append('    Nenhum — todos os matriculados estão conectados.')
        else:
            lines.append('  Ausentes: lista de matrícula da sala não disponível.')

        lines.append('')

    return '\n'.join(lines)


def render_html(data):
    labels = [g['group'] for g in data['groups']]
    presentes = [len(g['presence']) for g in data['groups']]
    ausentes = [len(g['absent']) for g in data['groups']]
    formador_presente = [1 if g['formador_presente'] else 0 for g in data['groups']]

    def esc(s):
        return (
            str(s)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )

    group_sections = []
    for g in data['groups']:
        status_class = 'on' if g['status_sala_ativa'] else 'off'
        formador_class = 'on' if g['formador_presente'] else 'off'

        def _periodo(p):
            if p['ainda_conectado']:
                return f"{p['hora_entrada'] or '-'} → agora"
            return f"{p['hora_entrada'] or '-'} → {p['hora_saida'] or '-'}"

        def _status_badge(p):
            if p['ainda_conectado']:
                return '<span class="badge on">conectado</span>'
            return '<span class="badge off">saiu</span>'

        presence_rows = ''.join(
            f"<tr class=\"{'' if p['ainda_conectado'] else 'row-saiu'}\"><td>{i}</td><td>{esc(p['label'])}"
            + (f' <span class="meet-orig">(Meet: "{esc(p["meet_name"])}")</span>' if p['resolved'] else '')
            + f"</td><td>{esc(_periodo(p))}</td><td>{esc(p['duration_label'] or '-')}</td>"
            + f"<td>{_status_badge(p)}</td></tr>"
            for i, p in enumerate(g['presence'], start=1)
        ) or '<tr><td colspan="5">Nenhum participante identificado.</td></tr>'

        absent_items = ''.join(f'<li>{esc(n)}</li>' for n in g['absent']) or '<li>Nenhum — todos presentes.</li>'

        group_sections.append(f'''
        <section class="group-card">
          <div class="group-card-head">
            <h2>{esc(g['group'])}</h2>
            <span class="badge {status_class}">{'ATIVA' if g['status_sala_ativa'] else 'INATIVA'}</span>
            <span class="badge {'rec' if g['gravando'] else ''}">{'GRAVANDO' if g['gravando'] else 'sem gravação'}</span>
          </div>
          <p class="formador-line">
            👤 Formador: <strong>{esc(g['formador'] or 'não identificado')}</strong>
            <span class="badge {formador_class}">{'PRESENTE — ' + esc(g['formador_localizacao'] or '') if g['formador_presente'] else 'NÃO DETECTADO'}</span>
          </p>
          <div class="group-grid">
            <div>
              <h3>Passaram pelo encontro ({len(g['presence'])})</h3>
              <table>
                <thead><tr><th>#</th><th>Nome</th><th>Período</th><th>Tempo total</th><th>Status</th></tr></thead>
                <tbody>{presence_rows}</tbody>
              </table>
            </div>
            <div>
              <h3>Ausentes ({len(g['absent'])} de {g['roster_size']})</h3>
              <ul class="absent-list">{absent_items}</ul>
            </div>
          </div>
        </section>
        ''')

    aviso_hoje = '' if data['used_today_filter'] else (
        '<p class="warn">Aviso: nenhuma sala marcada para hoje — mostrando todas as salas.</p>'
    )

    return f'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório ETI — {esc(data['dia'])} {esc(data['generated_at_label'])}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: Inter, "Segoe UI", Arial, sans-serif; background: #f4f6f8; color: #17202a; margin: 0; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  h1 {{ margin: 0 0 4px; font-size: 26px; }}
  header p {{ margin: 0 0 20px; color: #68737d; }}
  .warn {{ background: #fff4e5; border: 1px solid #f0c36d; padding: 10px 14px; border-radius: 8px; color: #7a5200; }}
  .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
  .summary > div {{ background: white; border: 1px solid #e1e5e9; border-radius: 10px; padding: 16px; }}
  .summary strong {{ font-size: 26px; display: block; }}
  .summary span {{ color: #68737d; font-size: 13px; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }}
  .chart-box {{ background: white; border: 1px solid #e1e5e9; border-radius: 10px; padding: 16px; }}
  .group-card {{ background: white; border: 1px solid #e1e5e9; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
  .group-card-head {{ display: flex; align-items: center; gap: 10px; }}
  .group-card-head h2 {{ margin: 0; font-size: 20px; }}
  .badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 999px; background: #eef1f3; color: #59636d; }}
  .badge.on {{ background: #e6f4ea; color: #137333; }}
  .badge.off {{ background: #fdecea; color: #a13c2f; }}
  .badge.rec {{ background: #fdecea; color: #a13c2f; }}
  .formador-line {{ font-size: 14px; margin: 10px 0; }}
  .group-grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-top: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 5px 6px; border-bottom: 1px solid #eef1f3; }}
  .meet-orig {{ color: #9aa5b1; font-size: 11px; }}
  .row-saiu {{ opacity: 0.6; }}
  .absent-list {{ font-size: 13px; margin: 0; padding-left: 18px; color: #7a2e2e; }}
  @media (max-width: 800px) {{
    .summary {{ grid-template-columns: 1fr 1fr; }}
    .charts {{ grid-template-columns: 1fr; }}
    .group-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<main>
  <header>
    <h1>Relatório de Monitoramento — Plantão ETI</h1>
    <p>Gerado em {esc(data['generated_at_label'])} ({esc(data['dia'])})</p>
    {aviso_hoje}
  </header>

  <section class="summary">
    <div><strong>{data['total_active_rooms']}/{data['total_grupos']}</strong><span>salas ativas</span></div>
    <div><strong>{data['total_active_cells']}/{data['total_grupos'] * 6}</strong><span>células ativas</span></div>
    <div><strong>{data['total_participants']}</strong><span>participantes únicos</span></div>
    <div><strong>{data['total_recording']}</strong><span>gravações em andamento</span></div>
  </section>

  <section class="charts">
    <div class="chart-box"><canvas id="chartPresenca"></canvas></div>
    <div class="chart-box"><canvas id="chartFormador"></canvas></div>
  </section>

  {''.join(group_sections)}
</main>
<script>
  const labels = {labels!r};
  const presentes = {presentes!r};
  const ausentes = {ausentes!r};
  const formadorPresente = {formador_presente!r};

  new Chart(document.getElementById('chartPresenca'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{ label: 'Presentes', data: presentes, backgroundColor: '#137333' }},
        {{ label: 'Ausentes', data: ausentes, backgroundColor: '#c5221f' }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ title: {{ display: true, text: 'Presentes x Ausentes por sala' }} }},
      scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }}
    }}
  }});

  new Chart(document.getElementById('chartFormador'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{ label: 'Formador presente (1=sim, 0=não)', data: formadorPresente, backgroundColor: '#2b6cb0' }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ title: {{ display: true, text: 'Presença do formador por sala' }} }},
      scales: {{ y: {{ beginAtZero: true, max: 1, ticks: {{ stepSize: 1 }} }} }}
    }}
  }});
</script>
</body>
</html>'''
