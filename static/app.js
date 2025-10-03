// ============================================
// Gestion du LocalStorage pour les modèles
// ============================================

function getModels() {
  const models = localStorage.getItem('chaturbate_models');
  return models ? JSON.parse(models) : [];
}

function saveModels(models) {
  localStorage.setItem('chaturbate_models', JSON.stringify(models));
}

function extractUsername(url) {
  // Extraire le username depuis une URL Chaturbate
  const match = url.match(/chaturbate\.com\/([^\/\?]+)/);
  return match ? match[1].toLowerCase() : url.toLowerCase();
}

// ============================================
// Modal
// ============================================

function openAddModal() {
  document.getElementById('addModal').classList.add('active');
  document.getElementById('modelUrl').value = '';
  document.getElementById('modelUrl').focus();
}

function closeAddModal() {
  document.getElementById('addModal').classList.remove('active');
}

// ============================================
// Ajouter un modèle
// ============================================

async function addModel(event) {
  event.preventDefault();
  
  const url = document.getElementById('modelUrl').value.trim();
  const username = extractUsername(url);
  
  if (!username) {
    showNotification('URL invalide', 'error');
    return;
  }
  
  const models = getModels();
  
  // Vérifier si le modèle existe déjà
  if (models.find(m => m.username === username)) {
    showNotification('Ce modèle est déjà dans la liste', 'error');
    return;
  }
  
  // Ajouter le modèle
  models.push({
    username: username,
    addedAt: new Date().toISOString()
  });
  
  saveModels(models);
  closeAddModal();
  showNotification(`${username} ajouté avec succès!`, 'success');
  renderModels();
}

// ============================================
// Récupérer les informations d'un modèle
// ============================================

async function getModelInfo(username) {
  try {
    // Utiliser notre API backend pour éviter les problèmes CORS
    const response = await fetch(`/api/model/${username}/status`);
    if (response.ok) {
      const data = await response.json();
      return {
        username: data.username,
        thumbnail: data.thumbnail,
        isOnline: data.isOnline,
        viewers: data.viewers || 0
      };
    }
  } catch (e) {
    console.error(`Erreur récupération infos ${username}:`, e);
  }
  
  // Fallback: utiliser l'image par défaut
  return {
    username: username,
    thumbnail: `https://roomimg.stream.highwebmedia.com/ri/${username}.jpg`,
    isOnline: false,
    viewers: 0
  };
}

// ============================================
// Afficher les modèles
// ============================================

async function renderModels() {
  const models = getModels();
  const grid = document.getElementById('modelsGrid');
  const emptyState = document.getElementById('emptyState');
  
  if (models.length === 0) {
    grid.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }
  
  emptyState.style.display = 'none';
  grid.innerHTML = '';
  
  // Récupérer les sessions actives
  const sessions = await getActiveSessions();
  
  // Créer les cartes une par une
  for (const model of models) {
    const modelInfo = await getModelInfo(model.username);
    model.isOnline = modelInfo.isOnline;
    model.thumbnail = modelInfo.thumbnail;
    model.viewers = modelInfo.viewers;
    
    // Récupérer les enregistrements
    let recordingsCount = 0;
    let lastRecording = null;
    try {
      const recRes = await fetch(`/api/recordings/${model.username}`);
      if (recRes.ok) {
        const recData = await recRes.json();
        recordingsCount = recData.recordings?.length || 0;
        if (recData.recordings && recData.recordings.length > 0) {
          lastRecording = recData.recordings[0].date;
        }
      }
    } catch (e) {
      console.log(`Pas d'enregistrements pour ${model.username}`);
    }
    
    let statusClass = 'offline';
    const isRecording = sessions.some(s => s.person === model.username && s.running);
    
    if (isRecording) {
      statusClass = 'recording';
    } else if (model.isOnline) {
      statusClass = 'online';
    }
    
    const card = document.createElement('div');
    card.className = `model-card ${statusClass}`;
    card.setAttribute('data-username', model.username);
    card.onclick = () => openModelPage(model.username);
    
    card.innerHTML = `
      ${isRecording ? '<div class="badge recording">REC</div>' : ''}
      ${model.isOnline && !isRecording ? '<div class="badge live">LIVE</div>' : ''}
      <img 
        src="${model.thumbnail}" 
        alt="${model.username}"
        class="model-thumbnail"
        onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22200%22%3E%3Crect fill=%22%231a1f3a%22 width=%22280%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23a0aec0%22 font-family=%22system-ui%22 font-size=%2220%22%3E${model.username}%3C/text%3E%3C/svg%3E'"
      />
      <div class="model-info">
        <div class="model-name">${model.username}</div>
        <div class="model-status">
          <span class="status-dot ${isRecording ? 'recording' : model.isOnline ? 'online' : 'offline'}"></span>
          ${isRecording ? 'En enregistrement' : model.isOnline ? 'En ligne' : 'Hors ligne'}
          ${model.isOnline && model.viewers > 0 ? ` · ${model.viewers} viewers` : ''}
        </div>
        ${recordingsCount > 0 ? `
          <div class="model-recordings">
            <span class="recordings-count">📁 ${recordingsCount} rediffusion${recordingsCount > 1 ? 's' : ''}</span>
            ${lastRecording ? `<span class="last-recording">📅 Dernier: ${lastRecording}</span>` : ''}
          </div>
        ` : ''}
      </div>
    `;
    
    grid.appendChild(card);
  }
}

// ============================================
// Récupérer les sessions actives
// ============================================

async function getActiveSessions() {
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.error('Erreur récupération sessions:', e);
  }
  return [];
}

// ============================================
// Ouvrir la page d'un modèle
// ============================================

function openModelPage(username) {
  // Créer une nouvelle page ou rediriger
  window.location.href = `/model.html?username=${username}`;
}

// ============================================
// Notifications
// ============================================

function showNotification(message, type = 'success') {
  const notif = document.createElement('div');
  const bgColor = type === 'success' ? '#10b981' : '#ef4444';
  notif.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${bgColor};
    color: white;
    padding: 1rem 1.5rem;
    border-radius: 10px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    z-index: 9999;
    animation: slideIn 0.3s ease-out;
    font-weight: 500;
  `;
  notif.textContent = message;
  document.body.appendChild(notif);
  
  setTimeout(() => {
    notif.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => notif.remove(), 300);
  }, 3000);
}

// ============================================
// Démarrage automatique des enregistrements
// ============================================

async function checkAndStartRecordings() {
  const models = getModels();
  const sessions = await getActiveSessions();
  
  for (const model of models) {
    const username = model.username;
    const session = sessions.find(s => s.person === username);
    const isRecording = session && session.running;
    
    if (!isRecording) {
      // Vérifier si le modèle est en ligne
      const info = await getModelInfo(username);
      if (info.isOnline) {
        // Démarrer l'enregistrement automatiquement
        console.log(`🔴 ${username} est en ligne, démarrage automatique...`);
        try {
          const res = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              target: username,
              source_type: 'chaturbate',
              person: username,
              name: username
            })
          });
          
          if (res.ok) {
            console.log(`✅ Enregistrement démarré automatiquement pour ${username}`);
            // Rafraîchir immédiatement pour voir le changement
            await renderModels();
          } else if (res.status === 409) {
            // Session déjà en cours, c'est normal, on ignore
            console.log(`⏭️ Session déjà en cours pour ${username}, skip`);
          } else {
            const error = await res.json();
            console.error(`❌ Erreur pour ${username}:`, error.detail);
          }
        } catch (e) {
          console.error(`❌ Erreur démarrage ${username}:`, e);
        }
      }
    }
  }
}

// ============================================
// Initialisation
// ============================================

window.addEventListener('DOMContentLoaded', () => {
  // Ajouter les styles d'animation
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(100%); opacity: 0; }
    }
  `;
  document.head.appendChild(style);
  
  // Afficher les modèles
  renderModels();
  
  // Ne PAS rafraîchir automatiquement pour éviter les doublons
  // L'utilisateur peut rafraîchir manuellement la page (F5) si besoin
  
  // Vérifier et démarrer les enregistrements toutes les 60 secondes
  setInterval(checkAndStartRecordings, 60000);
  checkAndStartRecordings(); // Premier check immédiat
  
  // Fermer la modal en cliquant en dehors
  document.getElementById('addModal').addEventListener('click', (e) => {
    if (e.target.id === 'addModal') {
      closeAddModal();
    }
  });
});
