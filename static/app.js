let rooms = [];

function esc(s) {
  return String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function render() {
  const q = document.querySelector('#search').value.trim().toLowerCase();
  const data = rooms.filter(r => r.title.toLowerCase().includes(q));
  document.querySelector('#rooms').innerHTML = data.map(r => `
    <article class="room ${r.active ? 'active' : ''}">
      <div class="room-head">
        <div>
          <h2>${esc(r.title)}</h2>
          <small>${esc(r.day)}</small>
        </div>
        <span class="status ${r.active ? 'on' : 'off'}">${r.active ? 'ATIVA' : 'INATIVA'}</span>
      </div>
      <div class="metrics">
        <div><b>${r.participants}</b><span>Participantes</span></div>
        <div><b>${r.recording ? 'SIM' : 'NÃO'}</b><span>Gravando</span></div>
      </div>
      ${r.error ? `<p class="error">${esc(r.error)}</p>` : ''}
      <a class="join" href="${esc(r.meet_url)}" target="_blank" rel="noopener noreferrer">Entrar</a>
    </article>
  `).join('');
}

async function refresh() {
  try {
    const [rr, ss] = await Promise.all([fetch('/api/rooms'), fetch('/api/status')]);
    rooms = await rr.json();
    const s = await ss.json();
    document.querySelector('#active').textContent = s.active;
    document.querySelector('#participants').textContent = s.participants;
    document.querySelector('#recording').textContent = s.recording;
    document.querySelector('#total').textContent = s.rooms;
    document.querySelector('#updated').textContent = `Atualizado: ${new Date().toLocaleTimeString('pt-BR')}`;
    render();
  } catch (e) {
    document.querySelector('#updated').textContent = 'Falha ao consultar backend';
  }
}

document.querySelector('#search').addEventListener('input', render);
refresh();
setInterval(refresh, 3000);
