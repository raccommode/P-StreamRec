// ============================================
// Gestion du LocalStorage pour les modèles
// ============================================

// Charger les modèles depuis le serveur
async function getModels() {
  try {
    const res = await fetch('/api/models');
    if (res.ok) {
      const data = await res.json();
      return data.models || [];
    }
  } catch (e) {
    console.error('Erreur chargement modèles:', e);
  }
  return [];
}

// Extraire le username depuis une URL Chaturbate
function extractUsername(url) {
  if (!url) return null;
  
  // Si c'est juste un username
  if (!url.includes('/') && !url.includes('.')) {
    return url.toLowerCase().trim();
  }
  
  // Extraire depuis URL chaturbate.com/username
  const match = url.match(/chaturbate\.com\/([a-zA-Z0-9_-]+)/);
  if (match) {
    return match[1].toLowerCase().trim();
  }
  
  return null;
}

// ============================================
// Modal
// ============================================

function openAddModal() {
  document.getElementById('addModal').classList.add('active');
  document.getElementById('modelUrl').value = '';
  document.getElementById('recordQuality').value = 'best';
  document.getElementById('retentionDays').value = '30';
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
  const quality = document.getElementById('recordQuality').value;
  const retentionDays = parseInt(document.getElementById('retentionDays').value);
  
  if (!username) {
    showNotification('URL invalide', 'error');
    return;
  }
  
  try {
    // Ajouter le modèle via l'API serveur
    const res = await fetch('/api/models', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        username: username,
        addedAt: new Date().toISOString(),
        recordQuality: quality,
        retentionDays: retentionDays,
        autoRecord: true  // Par défaut activé
      })
    });
    
    if (res.status === 409) {
      showNotification('Ce modèle est déjà dans la liste', 'error');
      return;
    }
    
    if (!res.ok) {
      showNotification('Erreur lors de l\'ajout', 'error');
      return;
    }
    
    closeAddModal();
    showNotification(`${username} ajouté avec succès!`, 'success');
    renderModels();
  } catch (e) {
    console.error('Erreur ajout modèle:', e);
    showNotification('Erreur de connexion', 'error');
  }
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

// Mise à jour dynamique des statuts sans recréer les cartes
async function updateModelsStatus() {
  try {
    const sessions = await getActiveSessions();
    const models = await getModels();
    const liveGrid = document.getElementById('liveGrid');
    const liveSection = document.getElementById('liveSection');
    let liveCount = 0;
    
    // Charger TOUTES les infos en PARALLÈLE (beaucoup plus rapide)
    const modelsInfo = await Promise.all(
      models.map(async (model) => {
        const [info, recordingsRes] = await Promise.all([
          getModelInfo(model.username),
          fetch(`/api/recordings/${model.username}`).catch(() => null)
        ]);
        
        let recordingsCount = 0;
        if (recordingsRes && recordingsRes.ok) {
          const recData = await recordingsRes.json();
          recordingsCount = recData.recordings?.length || 0;
        }
        
        return { ...info, recordingsCount };
      })
    );
    
    for (let i = 0; i < models.length; i++) {
      const model = models[i];
      const modelInfo = modelsInfo[i];
      
      const card = document.querySelector(`.model-card[data-username="${model.username}"]`);
      if (!card) continue; // Carte pas encore créée
      
      const isRecording = sessions.some(s => s.person === model.username && s.running);
      const isLive = isRecording || modelInfo.isOnline;
      
      // Mettre à jour le statut de la carte
      card.className = `model-card ${isRecording ? 'recording' : modelInfo.isOnline ? 'online' : 'offline'}`;
      
      // Mettre à jour les badges
      const existingBadges = card.querySelectorAll('.badge');
      existingBadges.forEach(b => b.remove());
      
      if (isRecording) {
        const badge = document.createElement('div');
        badge.className = 'badge recording';
        badge.textContent = 'REC';
        card.insertBefore(badge, card.firstChild);
      } else if (modelInfo.isOnline) {
        const badge = document.createElement('div');
        badge.className = 'badge live';
        badge.textContent = 'LIVE';
        card.insertBefore(badge, card.firstChild);
      }
      
      // Ajouter pastille nombre de rediffusions
      if (modelInfo.recordingsCount > 0) {
        const recBadge = document.createElement('div');
        recBadge.className = 'badge recordings-count';
        recBadge.textContent = `📁 ${modelInfo.recordingsCount}`;
        recBadge.style.top = isRecording || modelInfo.isOnline ? '3rem' : '0.75rem';
        card.insertBefore(recBadge, card.firstChild);
      }
      
      // Mettre à jour le texte de statut
      const statusDiv = card.querySelector('.model-status');
      if (statusDiv) {
        statusDiv.innerHTML = `
          <span class="status-dot ${isRecording ? 'recording' : modelInfo.isOnline ? 'online' : 'offline'}"></span>
          ${isRecording ? 'Recording' : modelInfo.isOnline ? 'Live' : 'Offline'}
          ${modelInfo.isOnline && modelInfo.viewers > 0 ? ` · ${modelInfo.viewers} viewers` : ''}
        `;
      }
      
      // Mettre à jour la miniature
      const thumbnail = card.querySelector('.model-thumbnail');
      if (thumbnail) {
        if (isLive) {
          // Live/Recording : Couleur + rafraîchir la miniature depuis le stream
          thumbnail.style.filter = 'none';
          thumbnail.src = `/api/thumbnail/${model.username}?t=${Date.now()}`;
        } else {
          // Offline : Noir et blanc (garde la miniature de la dernière rediffusion en cache)
          thumbnail.style.filter = 'grayscale(100%) brightness(0.7)';
          // Ne pas changer l'URL pour garder la miniature générée en cache
          if (!thumbnail.src.includes('/api/thumbnail/')) {
            thumbnail.src = `/api/thumbnail/${model.username}`;
          }
        }
      }
      
      // DÉPLACER les cartes LIVE dans la section LIVE
      if (isLive) {
        liveCount++;
        if (card.parentElement !== liveGrid) {
          liveGrid.appendChild(card);
        }
      } else {
        // Remettre dans la section principale si pas live
        const mainGrid = document.getElementById('modelsGrid');
        if (card.parentElement !== mainGrid) {
          mainGrid.appendChild(card);
        }
      }
    }
    
    // Afficher/masquer la section LIVE selon le nombre
    if (liveSection) {
      liveSection.style.display = liveCount > 0 ? 'contents' : 'none';
    }
  } catch (e) {
    console.error('Error updating status:', e);
  }
}

async function renderModels() {
  const models = await getModels();
  const grid = document.getElementById('modelsGrid');
  const emptyState = document.getElementById('emptyState');
  
  if (models.length === 0) {
    grid.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }
  
  emptyState.style.display = 'none';
  grid.innerHTML = '';
  
  // Section LIVE MODELS
  const liveSection = document.createElement('div');
  liveSection.id = 'liveSection';
  liveSection.style.display = 'none'; // Masqué par défaut
  liveSection.innerHTML = '<h2 style="grid-column: 1 / -1; color: var(--text-primary); font-size: 1.5rem; margin: 1rem 0 0.5rem; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #ef4444;">🔴</span> Live Now</h2><div id="liveGrid" class="models-grid" style="grid-column: 1 / -1; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
  grid.appendChild(liveSection);
  
  // Section OFFLINE MODELS
  const offlineSection = document.createElement('div');
  offlineSection.id = 'offlineSection';
  offlineSection.style.gridColumn = '1 / -1';
  offlineSection.style.display = 'contents';
  offlineSection.innerHTML = '<h2 style="grid-column: 1 / -1; color: var(--text-primary); font-size: 1.5rem; margin: 2rem 0 0.5rem;">All Models</h2>';
  grid.appendChild(offlineSection);
  
  // Créer les cartes IMMÉDIATEMENT avec des placeholders
  for (const model of models) {
    const card = document.createElement('div');
    card.className = 'model-card offline';
    card.setAttribute('data-username', model.username);
    card.onclick = () => openModelPage(model.username);
    
    card.innerHTML = `
      <img 
        src="/api/thumbnail/${model.username}" 
        alt="${model.username}"
        class="model-thumbnail"
        onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22200%22%3E%3Crect fill=%22%231a1f3a%22 width=%22280%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23a0aec0%22 font-family=%22system-ui%22 font-size=%2220%22%3E${model.username}%3C/text%3E%3C/svg%3E'"
      />
      <div class="model-info">
        <div class="model-name">${model.username}</div>
        <div class="model-status">
          <span class="status-dot offline"></span>
          Loading...
        </div>
      </div>
    `;
    
    grid.appendChild(card);
  }
  
  // Ensuite mettre à jour dynamiquement les statuts
  updateModelsStatus();
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
  const models = await getModels();
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
            // Mettre à jour juste les statuts sans tout recharger
            await updateModelsStatus();
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
  
  // Mettre à jour les statuts toutes les 15 secondes (rapide et dynamique)
  setInterval(updateModelsStatus, 15000);
  
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
