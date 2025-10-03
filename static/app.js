async function startSession() {
  const target = document.getElementById('target').value.trim();
  const name = document.getElementById('name').value.trim() || null;
  if (!target) { alert('Veuillez saisir une URL m3u8 ou un nom.'); return; }
  const stype = (document.querySelector('input[name="stype"]:checked')?.value || 'auto');
  const source_type = stype === 'auto' ? null : stype;

  const res = await fetch('/api/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, source_type, name })
  });
  if (!res.ok) {
    const err = await res.json().catch(()=>({detail: res.statusText}));
    alert('Erreur: ' + (err.detail || '')); return;
  }
  const data = await res.json();
  attachPlayer(data.playback_url);
  document.getElementById('nowPlaying').textContent = `Lecture: ${data.name} (session ${data.id})`;
  refreshStatus();
}

async function refreshStatus() {
  const res = await fetch('/api/status');
  const sessions = await res.json();
  const box = document.getElementById('sessions');
  box.innerHTML = '';
  sessions.forEach(s => {
    const div = document.createElement('div');
    div.innerHTML = `
      <div class="row" style="justify-content:space-between;">
        <div>
          <div><b>${s.name}</b> <small class="muted">#${s.id}</small></div>
          <div class="muted">personne: <b>${s.person || '-'}</b></div>
          <div class="muted">${s.running ? 'en cours' : 'arrêté'} — <span class="small">${s.created_at}</span></div>
          <div class="muted">record: <span class="small">${s.record_path}</span></div>
        </div>
        <div class="row">
          <button onclick="attachPlayer('${s.playback_url}')">Lire</button>
          <button class="secondary" onclick="copyText('${location.origin + s.playback_url}')">Copier URL</button>
          <button class="danger" onclick="stopSession('${s.id}')">Stop</button>
        </div>
      </div>`;
    box.appendChild(div);
  })
}

async function stopSession(id) {
  const res = await fetch('/api/stop/' + id, { method: 'POST' });
  if (!res.ok) { alert('Arrêt impossible'); return; }
  refreshStatus();
}

function attachPlayer(url) {
  const video = document.getElementById('player');
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = url; video.play();
  } else if (window.Hls && window.Hls.isSupported()) {
    if (video._hls) { video._hls.destroy(); }
    const hls = new Hls({ liveDurationInfinity: true });
    hls.loadSource(url); hls.attachMedia(video);
    video._hls = hls;
  } else {
    alert('HLS non supporté par ce navigateur.');
  }
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); } catch {}
}

window.addEventListener('DOMContentLoaded', refreshStatus);
