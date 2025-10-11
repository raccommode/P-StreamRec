// ============================================
// Cache for instant performance
// ============================================

// Save models cache
function saveModelsCache(models) {
  localStorage.setItem('models_cache', JSON.stringify({
    models,
    timestamp: Date.now()
  }));
}

// Get models cache
function getModelsCache() {
  const cached = localStorage.getItem('models_cache');
  if (cached) {
    const data = JSON.parse(cached);
    // Cache valid for 5 minutes
    if (Date.now() - data.timestamp < 300000) {
      return data.models;
    }
  }
  return null;
}

// Save model info
function saveModelInfoCache(username, info) {
  const key = `model_info_${username}`;
  localStorage.setItem(key, JSON.stringify({
    ...info,
    timestamp: Date.now()
  }));
}

// Get cached info
function getModelInfoCache(username) {
  const key = `model_info_${username}`;
  const cached = localStorage.getItem(key);
  if (cached) {
    const data = JSON.parse(cached);
    // Cache valid for 30 seconds
    if (Date.now() - data.timestamp < 30000) {
      return data;
    }
  }
  return null;
}

// Load models from server
async function getModels() {
  try {
    const res = await fetch('/api/models');
    if (res.ok) {
      const data = await res.json();
      const models = data.models || [];
      saveModelsCache(models); // Save to cache
      return models;
    }
  } catch (e) {
    console.error('Error loading models:', e);
  }
  return [];
}

// Extract username from Chaturbate URL
function extractUsername(url) {
  if (!url) return null;
  
  // If it's just a username
  if (!url.includes('/') && !url.includes('.')) {
    return url.toLowerCase().trim();
  }
  
  // Extract from chaturbate.com/username URL
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
// Add a model
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
        autoRecord: true  // Enabled by default
      })
    });
    
    if (res.status === 409) {
      showNotification('This model is already in the list', 'error');
      return;
    }
    
    if (!res.ok) {
      showNotification('Error adding model', 'error');
      return;
    }
    
    closeAddModal();
    showNotification(`${username} added successfully!`, 'success');
    
    // Clear cache to force reload from server
    localStorage.removeItem('dashboard_cache');
    localStorage.removeItem('models_cache');
    
    renderModels();
  } catch (e) {
    console.error('Error adding model:', e);
    showNotification('Connection error', 'error');
  }
}

// ============================================
// Get model information
// ============================================

async function getModelInfo(username, useCache = true) {
  // Try cache first for instant display
  if (useCache) {
    const cached = getModelInfoCache(username);
    if (cached) {
      // Return cache immediately
      // and update in background
      getModelInfo(username, false).then(freshData => {
        saveModelInfoCache(username, freshData);
      });
      return cached;
    }
  }
  
  try {
    // Use our backend API to avoid CORS issues
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
    console.error(`Error fetching info for ${username}:`, e);
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
// Display models
// ============================================

// Load ALL data at once from optimized backend
async function getDashboardData() {
  try {
    const res = await fetch('/api/dashboard');
    if (res.ok) {
      const data = await res.json();
      // Save to cache
      localStorage.setItem('dashboard_cache', JSON.stringify({
        ...data,
        cachedAt: Date.now()
      }));
      return data;
    }
  } catch (e) {
    console.error('Error loading dashboard:', e);
  }
  
  // Fallback to cache
  const cached = localStorage.getItem('dashboard_cache');
  if (cached) {
    const data = JSON.parse(cached);
    // Cache valid for 1 minute
    if (Date.now() - data.cachedAt < 60000) {
      return data;
    }
  }
  
  return { models: [], sessions: [] };
}

// Dynamic status update without recreating cards
async function updateModelsStatus() {
  try {
    // ONE single request for everything!
    const dashboardData = await getDashboardData();
    const models = dashboardData.models || [];
    const sessions = dashboardData.sessions || [];
    
    const liveGrid = document.getElementById('liveGrid');
    const liveSection = document.getElementById('liveSection');
    let liveCount = 0;
    
    for (const modelInfo of models) {
      const card = document.querySelector(`.model-card[data-username="${modelInfo.username}"]`);
      if (!card) continue; // Card not yet created
      
      const isRecording = modelInfo.isRecording;
      const isLive = isRecording || modelInfo.isOnline;
      
      // Update card status
      card.className = `model-card ${isRecording ? 'recording' : modelInfo.isOnline ? 'online' : 'offline'}`;
      
      // Update badges
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
      
      // Add replays count badge
      if (modelInfo.recordingsCount > 0) {
        const recBadge = document.createElement('div');
        recBadge.className = 'badge recordings-count';
        recBadge.textContent = `📁 ${modelInfo.recordingsCount}`;
        recBadge.style.top = isRecording || modelInfo.isOnline ? '3rem' : '0.75rem';
        card.insertBefore(recBadge, card.firstChild);
      }
      
      // Update status text
      const statusDiv = card.querySelector('.model-status');
      if (statusDiv) {
        statusDiv.innerHTML = `
          <span class="status-dot ${isRecording ? 'recording' : modelInfo.isOnline ? 'online' : 'offline'}"></span>
          ${isRecording ? 'Recording' : modelInfo.isOnline ? 'Live' : 'Offline'}
          ${modelInfo.isOnline && modelInfo.viewers > 0 ? ` · ${modelInfo.viewers} viewers` : ''}
        `;
      }
      
      // Update thumbnail
      const thumbnail = card.querySelector('.model-thumbnail');
      if (thumbnail) {
        if (isLive) {
          // Live/Recording: Color + refresh thumbnail from stream
          thumbnail.style.filter = 'none';
          thumbnail.src = `/api/thumbnail/${modelInfo.username}?t=${Date.now()}`;
        } else {
          // Offline: Black and white (keep last replay thumbnail in cache)
          thumbnail.style.filter = 'grayscale(100%) brightness(0.7)';
          // Don't change URL to keep cached generated thumbnail
          if (!thumbnail.src.includes('/api/thumbnail/')) {
            thumbnail.src = `/api/thumbnail/${modelInfo.username}`;
          }
        }
      }
      
      // MOVE LIVE cards to LIVE section
      if (isLive) {
        liveCount++;
        if (card.parentElement !== liveGrid) {
          liveGrid.appendChild(card);
        }
      } else {
        // Move back to All Models section if not live
        const allGrid = document.getElementById('allGrid');
        if (allGrid && card.parentElement !== allGrid) {
          allGrid.appendChild(card);
        }
      }
    }
    
    // Show/hide LIVE section based on count
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
  
  // Try dashboard cache for instant display
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
  
  // Display cache immediately if available
  if (models.length > 0) {
    emptyState.style.display = 'none';
    grid.innerHTML = '';
    
    // Section LIVE MODELS
    const liveSection = document.createElement('div');
    liveSection.id = 'liveSection';
    liveSection.style.cssText = 'grid-column: 1 / -1; display: none; margin-bottom: 2rem;';
    liveSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #ef4444; font-size: 1.2rem;">🔴</span> Live Now</h2><div id="liveGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(liveSection);
    
    // Section ALL MODELS
    const allSection = document.createElement('div');
    allSection.id = 'allSection';
    allSection.style.cssText = 'grid-column: 1 / -1;';
    allSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #6366f1;">📁</span> All Models</h2><div id="allGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(allSection);
    
    // Create cards IMMEDIATELY with cached data
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
      
      // Add to All Models section by default
      const allGrid = document.getElementById('allGrid');
      if (allGrid) {
        allGrid.appendChild(card);
      } else {
        grid.appendChild(card);
      }
    }
  }
  
  // Load real data in background
  const dashboardData = await getDashboardData();
  const freshModels = dashboardData.models || [];
  
  if (freshModels.length === 0) {
    grid.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }
  
  // If no cache, display now
  if (models.length === 0) {
    emptyState.style.display = 'none';
    grid.innerHTML = '';
    
    const liveSection = document.createElement('div');
    liveSection.id = 'liveSection';
    liveSection.style.cssText = 'grid-column: 1 / -1; display: none; margin-bottom: 2rem;';
    liveSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #ef4444; font-size: 1.2rem;">🔴</span> Live Now</h2><div id="liveGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
    grid.appendChild(liveSection);
    
    const allSection = document.createElement('div');
    allSection.id = 'allSection';
    allSection.style.cssText = 'grid-column: 1 / -1;';
    allSection.innerHTML = '<h2 style="color: var(--text-primary); font-size: 1.5rem; margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;"><span style="color: #6366f1;">📁</span> All Models</h2><div id="allGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"></div>';
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
      
      // Add to All Models section
      const allGrid = document.getElementById('allGrid');
      if (allGrid) {
        allGrid.appendChild(card);
      } else {
        grid.appendChild(card);
      }
    }
  }
  
  // Update with real data (just badges and positions)
  updateModelsStatus();
}

// ============================================
// Get active sessions
// ============================================

async function getActiveSessions() {
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.error('Error fetching sessions:', e);
  }
  return [];
}

// ============================================
// Open model page
// ============================================

function openModelPage(username) {
  // Create a new page or redirect
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
// Automatic recording start
// ============================================

async function checkAndStartRecordings() {
  const models = await getModels();
  const sessions = await getActiveSessions();
  
  for (const model of models) {
    const username = model.username;
    const session = sessions.find(s => s.person === username);
    const isRecording = session && session.running;
    
    if (!isRecording) {
      // Check if model is online
      const info = await getModelInfo(username);
      if (info.isOnline) {
        // Start recording automatically
        console.log(`🔴 ${username} is online, starting automatically...`);
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
            console.log(`✅ Recording started automatically for ${username}`);
            // Update just statuses without reloading everything
            await updateModelsStatus();
          } else if (res.status === 409) {
            // Session already running, this is normal, skip
            console.log(`⏭️ Session already running for ${username}, skip`);
          } else {
            const error = await res.json();
            console.error(`❌ Error for ${username}:`, error.detail);
          }
        } catch (e) {
          console.error(`❌ Error starting ${username}:`, e);
        }
      }
    }
  }
}

// ============================================
// Initialization
// ============================================

window.addEventListener('DOMContentLoaded', () => {
  // Add animation styles
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
  
  // Display models
  renderModels();
  
  // Update statuses every 15 seconds (fast and dynamic)
  setInterval(updateModelsStatus, 15000);
  
  // Check and start recordings every 60 seconds
  setInterval(checkAndStartRecordings, 60000);
  checkAndStartRecordings(); // First immediate check
  
  // Close modal when clicking outside
  document.getElementById('addModal').addEventListener('click', (e) => {
    if (e.target.id === 'addModal') {
      closeAddModal();
    }
  });
});
