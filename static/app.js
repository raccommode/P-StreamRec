// ============================================
// Cache pour performance instantanée
// ============================================

// Sauvegarder le cache des modèles
function saveModelsCache(models) {
  localStorage.setItem('models_cache', JSON.stringify({
    models,
    timestamp: Date.now()
  }));
}

// Récupérer le cache des modèles
function getModelsCache() {
  const cached = localStorage.getItem('models_cache');
  if (cached) {
    const data = JSON.parse(cached);
    // Cache valide pendant 5 minutes
    if (Date.now() - data.timestamp < 300000) {
      return data.models;
    }
  }
  return null;
}

// Sauvegarder les infos des modèles
function saveModelInfoCache(username, info) {
  const key = `model_info_${username}`;
  localStorage.setItem(key, JSON.stringify({
    ...info,
    timestamp: Date.now()
  }));
}

// Récupérer les infos en cache
function getModelInfoCache(username) {
  const key = `model_info_${username}`;
  const cached = localStorage.getItem(key);
  if (cached) {
    const data = JSON.parse(cached);
    // Cache valide pendant 30 secondes
    if (Date.now() - data.timestamp < 30000) {
      return data;
    }
  }
  return null;
}

// Charger les modèles depuis le serveur
async function getModels() {
  try {
    const res = await fetch('/api/models');
    if (res.ok) {
      const data = await res.json();
      const models = data.models || [];
      saveModelsCache(models); // Sauvegarder en cache
      return models;
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
    
    // Vider le cache pour forcer un rechargement depuis le serveur
    localStorage.removeItem('dashboard_cache');
    localStorage.removeItem('models_cache');
    
    renderModels();
  } catch (e) {
    console.error('Erreur ajout modèle:', e);
    showNotification('Erreur de connexion', 'error');
  }
}

// ============================================
// Récupérer les informations d'un modèle
// ============================================

async function getModelInfo(username, useCache = true) {
  // Essayer le cache d'abord pour l'affichage instantané
  if (useCache) {
    const cached = getModelInfoCache(username);
    if (cached) {
      // Retourner le cache immédiatement
      // et mettre à jour en arrière-plan
      getModelInfo(username, false).then(freshData => {
        saveModelInfoCache(username, freshData);
      });
      return cached;
    }
  }
  
  try {
    // Utiliser notre API backend pour éviter les problèmes CORS
    const response = await fetch(`/api/model/${username}/status`);
    if (response.ok) {
      const data = await response.json();
      const info = {
        username: data.username,
        thumbnail: data.thumbnail,
        isOnline: data.isOnline,
        viewers: data.viewers || 0
      };
      saveModelInfoCache(username, info);
      return info;
    }
  } catch (e) {
    console.error(`Erreur récupération infos ${username}:`, e);
  }
  
  // Fallback: utiliser l'image par défaut
  const fallback = {
    username: username,
    thumbnail: `https://roomimg.stream.highwebmedia.com/ri/${username}.jpg`,
    isOnline: false,
    viewers: 0
  };
  saveModelInfoCache(username, fallback);
  return fallback;
}

// ============================================
// Afficher les modèles
// ============================================

// Charger TOUTES les données d'un coup depuis le backend optimisé
async function getDashboardData() {
  try {
    const res = await fetch('/api/dashboard');
    if (res.ok) {
      const data = await res.json();
      // Sauvegarder en cache
      localStorage.setItem('dashboard_cache', JSON.stringify({
        ...data,
        cachedAt: Date.now()
      }));
      return data;
    }
  } catch (e) {
    console.error('Error loading dashboard:', e);
  }
  
  // Fallback sur le cache
  const cached = localStorage.getItem('dashboard_cache');
  if (cached) {
    const data = JSON.parse(cached);
    // Cache valide pendant 1 minute
    if (Date.now() - data.cachedAt < 60000) {
      return data;
    }
  }
  
  return { models: [], sessions: [] };
}

// Mise à jour dynamique des statuts sans recréer les cartes
async function updateModelsStatus() {
  try {
    // UNE SEULE requête pour tout !
    const dashboardData = await getDashboardData();
    const models = dashboardData.models || [];
    const sessions = dashboardData.sessions || [];
    
    const liveGrid = document.getElementById('liveGrid');
    const liveSection = document.getElementById('liveSection');
    let liveCount = 0;
    
    for (const modelInfo of models) {
      const card = document.querySelector(`.model-card[data-username="${modelInfo.username}"]`);
      if (!card) continue; // Carte pas encore créée
      
      const isRecording = modelInfo.isRecording;
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
          thumbnail.src = `/api/thumbnail/${modelInfo.username}?t=${Date.now()}`;
        } else {
          // Offline : Noir et blanc (garde la miniature de la dernière rediffusion en cache)
          thumbnail.style.filter = 'grayscale(100%) brightness(0.7)';
          // Ne pas changer l'URL pour garder la miniature générée en cache
          if (!thumbnail.src.includes('/api/thumbnail/')) {
            thumbnail.src = `/api/thumbnail/${modelInfo.username}`;
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
        // Remettre dans la section All Models si pas live
        const allGrid = document.getElementById('allGrid');
        if (allGrid && card.parentElement !== allGrid) {
          allGrid.appendChild(card);
        }
      }
    }
    
    // Afficher/masquer la section LIVE selon le nombre
    if (liveSection) {
      liveSection.style.display = liveCount > 0 ? 'block' : 'none';
    }
  } catch (e) {
    console.error('Error updating status:', e);
  }
}

async function renderModels() {
  const grid = document.getElementById('modelsGrid');
  const emptyState = document.getElementById('emptyState');
  
  // Essayer le cache dashboard pour affichage instantané
  const cached = localStorage.getItem('dashboard_cache');
  let models = [];
  
  if (cached) {
    try {
      const data = JSON.parse(cached);
      if (Date.now() - data.cachedAt < 60000) {
        models = data.models || [];
      }
    } catch (e) {}
  }
  
  // Afficher immédiatement le cache si disponible
  if (models.length > 0) {
    emptyState.style.display = 'none';
    grid.innerHTML = '';
    
    // Section LIVE MODELS
    const liveSection = document.createElement('div');
    liveSection.id = 'liveSection';
    liveSection.style.cssText = 'grid-column: 1 / -1; display: none; margin-bottom: 2rem;';
    liveSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #ef4444; font-size: 1.2rem;">🔴</span> En Direct</h2><div id="liveGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(liveSection);
    
    // Section ALL MODELS
    const allSection = document.createElement('div');
    allSection.id = 'allSection';
    allSection.style.cssText = 'grid-column: 1 / -1;';
    allSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #6366f1;">📁</span> Tous les Modèles</h2><div id="allGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(allSection);
    
    // Créer les cartes IMMÉDIATEMENT avec les données du cache
    for (const modelInfo of models) {
      const card = document.createElement('div');
      card.className = 'model-card offline';
      card.setAttribute('data-username', modelInfo.username);
      card.onclick = () => openModelPage(modelInfo.username);
      
      const statusText = modelInfo.isOnline ? 'Live' : 'Offline';
      const statusClass = modelInfo.isOnline ? 'online' : 'offline';
      
      card.innerHTML = `
        <img 
          src="/api/thumbnail/${modelInfo.username}" 
          alt="${modelInfo.username}"
          class="model-thumbnail"
          style="filter: ${modelInfo.isOnline ? 'none' : 'grayscale(100%) brightness(0.7)'};"
          onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22200%22%3E%3Crect fill=%22%231a1f3a%22 width=%22280%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23a0aec0%22 font-family=%22system-ui%22 font-size=%2220%22%3E${modelInfo.username}%3C/text%3E%3C/svg%3E'"
        />
        <div class="model-info">
          <div class="model-name">${modelInfo.username}</div>
          <div class="model-status">
            <span class="status-dot ${statusClass}"></span>
            ${statusText}
          </div>
        </div>
      `;
      
      // Ajouter dans la section All Models par défaut
      const allGrid = document.getElementById('allGrid');
      if (allGrid) {
        allGrid.appendChild(card);
      } else {
        grid.appendChild(card);
      }
    }
  }
  
  // Charger les vraies données en arrière-plan
  const dashboardData = await getDashboardData();
  const freshModels = dashboardData.models || [];
  
  if (freshModels.length === 0) {
    grid.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }
  
  // Si pas de cache, afficher maintenant
  if (models.length === 0) {
    emptyState.style.display = 'none';
    grid.innerHTML = '';
    
    const liveSection = document.createElement('div');
    liveSection.id = 'liveSection';
    liveSection.style.cssText = 'grid-column: 1 / -1; display: none; margin-bottom: 2rem;';
    liveSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #ef4444; font-size: 1.2rem;">🔴</span> En Direct</h2><div id="liveGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(liveSection);
    
    const allSection = document.createElement('div');
    allSection.id = 'allSection';
    allSection.style.cssText = 'grid-column: 1 / -1;';
    allSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #6366f1;">📁</span> Tous les Modèles</h2><div id="allGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(allSection);
    
    for (const modelInfo of freshModels) {
      const card = document.createElement('div');
      card.className = 'model-card offline';
      card.setAttribute('data-username', modelInfo.username);
      card.onclick = () => openModelPage(modelInfo.username);
      
      const statusText = modelInfo.isOnline ? 'Live' : 'Offline';
      const statusClass = modelInfo.isOnline ? 'online' : 'offline';
      
      card.innerHTML = `
        <img 
          src="/api/thumbnail/${modelInfo.username}" 
          alt="${modelInfo.username}"
          class="model-thumbnail"
          style="filter: ${modelInfo.isOnline ? 'none' : 'grayscale(100%) brightness(0.7)'};"
          onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22200%22%3E%3Crect fill=%22%231a1f3a%22 width=%22280%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23a0aec0%22 font-family=%22system-ui%22 font-size=%2220%22%3E${modelInfo.username}%3C/text%3E%3C/svg%3E'"
        />
        <div class="model-info">
          <div class="model-name">${modelInfo.username}</div>
          <div class="model-status">
            <span class="status-dot ${statusClass}"></span>
            ${statusText}
          </div>
        </div>
      `;
      
      // Ajouter dans la section All Models
      const allGrid = document.getElementById('allGrid');
      if (allGrid) {
        allGrid.appendChild(card);
      } else {
        grid.appendChild(card);
      }
    }
  }
  
  // Mettre à jour avec les vraies données (juste les badges et positions)
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
