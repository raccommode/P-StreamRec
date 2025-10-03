async function startSession() {
  const target = document.getElementById('target').value.trim();
  const name = document.getElementById('name').value.trim() || null;
  const person = (document.getElementById('person')?.value || '').trim() || null;
  if (!target) { alert('Veuillez saisir une URL m3u8 ou un nom.'); return; }
  const stype = (document.querySelector('input[name="stype"]:checked')?.value || 'auto');
  const source_type = stype === 'auto' ? null : stype;

  const res = await fetch('/api/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, source_type, name, person })
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
  const counter = document.getElementById('sessionCount');
  
  const runningSessions = sessions.filter(s => s.running).length;
  counter.textContent = `${runningSessions} session(s) active(s) / ${sessions.length} total`;
  
  box.innerHTML = '';
  sessions.forEach(s => {
    const statusClass = s.running ? 'status-recording' : 'status-offline';
    const statusText = s.running ? '🔴 En cours d\'enregistrement' : '⚫ Arrêté';
    const div = document.createElement('div');
    div.innerHTML = `
      <div class="row" style="justify-content:space-between; padding: 12px; background: #0f172a; border-radius: 8px;">
        <div>
          <div><span class="status-indicator ${statusClass}"></span><b>${s.name}</b> <small class="muted">#${s.id}</small></div>
          <div class="muted" style="margin-left:18px;">Dossier: <b>${s.person || '-'}</b></div>
          <div class="muted" style="margin-left:18px;">${statusText}</div>
          <div class="muted" style="margin-left:18px; font-size:12px;">Fichier: <code style="background:#1f2937; padding:2px 4px; border-radius:3px;">${s.record_path}</code></div>
        </div>
        <div class="row">
          <button onclick="attachPlayer('${s.playback_url}')" class="secondary">📺 Regarder</button>
          <button class="secondary" onclick="copyText('${location.origin + s.playback_url}')">📋 URL</button>
          <button class="danger" onclick="stopSession('${s.id}')">⏹️ Stop</button>
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
  try { 
    await navigator.clipboard.writeText(text);
    showNotification('URL copiée dans le presse-papier!');
  } catch {}
}

function showNotification(message) {
  const notif = document.createElement('div');
  notif.style.cssText = 'position:fixed; top:20px; right:20px; background:#10b981; color:white; padding:12px 20px; border-radius:8px; z-index:9999; animation: slideIn 0.3s;';
  notif.textContent = message;
  document.body.appendChild(notif);
  setTimeout(() => notif.remove(), 3000);
}

function setQuickTarget(username) {
  document.getElementById('target').value = username;
  document.querySelector('input[name="stype"][value="chaturbate"]').checked = true;
}

function showQuickAdd() {
  const links = document.getElementById('quickLinks');
  links.style.display = links.style.display === 'none' ? 'flex' : 'none';
}

async function stopAllSessions() {
  if (!confirm('Voulez-vous vraiment arrêter tous les enregistrements?')) return;
  const res = await fetch('/api/status');
  const sessions = await res.json();
  const running = sessions.filter(s => s.running);
  
  for (const session of running) {
    await fetch('/api/stop/' + session.id, { method: 'POST' });
  }
  
  showNotification(`${running.length} session(s) arrêtée(s)`);
  refreshStatus();
}

// Auto-refresh toutes les 5 secondes
setInterval(refreshStatus, 5000);

window.addEventListener('DOMContentLoaded', () => {
  refreshStatus();
  
  // Ajouter le style des animations
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
  `;
  document.head.appendChild(style);
});
