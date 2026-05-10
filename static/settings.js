// ============================================
// Settings Page - Configuration and account management
// ============================================

// ============================================
// Tab Navigation
// ============================================
function initTabs() {
  var navItems = document.querySelectorAll('.settings-nav-item');
  navItems.forEach(function(item) {
    item.addEventListener('click', function() {
      var tabId = this.getAttribute('data-tab');
      // Deactivate all
      navItems.forEach(function(n) { n.classList.remove('active'); });
      document.querySelectorAll('.settings-tab').forEach(function(t) { t.classList.remove('active'); });
      // Activate clicked
      this.classList.add('active');
      var tab = document.getElementById('tab-' + tabId);
      if (tab) tab.classList.add('active');
      // Load stats on first visit
      if (tabId === 'statistics' && !statsLoaded) {
        loadSystemStats();
        statsLoaded = true;
      }
      if (tabId === 'logs' && !logsLoaded) {
        loadLogs();
        logsLoaded = true;
      }
      if (tabId === 'processes') {
        startProcessesPolling();
      } else {
        stopProcessesPolling();
      }
    });
  });
}

var statsLoaded = false;
var logsLoaded = false;
var logsOffset = 0;
var statsRefreshInterval = null;

// ============================================
// CAM4 session management (cookie-based)
// ============================================
async function checkCam4Status() {
  var statusEl = document.getElementById('cam4Status');
  var usernameRow = document.getElementById('cam4UsernameRow');
  var usernameEl = document.getElementById('cam4Username');
  var loginForm = document.getElementById('cam4LoginForm');
  var loggedInActions = document.getElementById('cam4LoggedInActions');
  if (!statusEl) return;

  try {
    var res = await fetch('/api/cam4/status');
    if (res.ok) {
      var data = await res.json();
      if (data.isLoggedIn) {
        statusEl.className = 'status-indicator connected';
        statusEl.textContent = 'Connected';
        if (usernameRow) usernameRow.style.display = data.username ? 'flex' : 'none';
        if (usernameEl) usernameEl.textContent = data.username || 'Session active';
        if (loginForm) loginForm.style.display = 'none';
        if (loggedInActions) loggedInActions.style.display = 'block';
      } else {
        statusEl.className = 'status-indicator disconnected';
        statusEl.textContent = 'Not Connected';
        if (usernameRow) usernameRow.style.display = 'none';
        if (loginForm) loginForm.style.display = 'block';
        if (loggedInActions) loggedInActions.style.display = 'none';
      }
    } else {
      statusEl.className = 'status-indicator unknown';
      statusEl.textContent = 'Unavailable';
    }
  } catch (e) {
    console.error('Error checking CAM4 status:', e);
    statusEl.className = 'status-indicator unknown';
    statusEl.textContent = 'Unavailable';
  }
}

async function loginCam4(event) {
  event.preventDefault();
  var username = document.getElementById('cam4User').value.trim();
  var password = document.getElementById('cam4Pass').value;
  var btn = document.getElementById('cam4LoginBtn');
  if (!username || !password) {
    showNotification('Please enter both username and password', 'error');
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = 'Logging in...'; }
  try {
    var res = await fetch('/api/cam4/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password })
    });
    var data = await res.json().catch(function(){ return {}; });
    if (res.ok && data.success) {
      showNotification('CAM4 login successful', 'success');
      document.getElementById('cam4Pass').value = '';
      await checkCam4Status();
    } else {
      showNotification('Login failed: ' + (data.detail || data.error || 'unknown error'), 'error');
    }
  } catch (e) {
    showNotification('Network error: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Log In'; }
  }
}

async function logoutCam4() {
  if (!confirm('Disconnect CAM4 account?')) return;
  try {
    var res = await fetch('/api/cam4/logout', { method: 'POST' });
    if (res.ok) {
      showNotification('CAM4 session cleared', 'success');
      await checkCam4Status();
    } else {
      showNotification('Failed to disconnect', 'error');
    }
  } catch (e) {
    showNotification('Network error: ' + e.message, 'error');
  }
}

async function syncCam4Following() {
  try {
    var res = await fetch('/api/cam4/following/sync', { method: 'POST' });
    var data = await res.json();
    if (res.ok) {
      showNotification(data.message || ('Synced ' + data.synced + ' favorites'), 'success');
    } else {
      showNotification('Sync failed: ' + (data.detail || 'unknown'), 'error');
    }
  } catch (e) {
    showNotification('Network error: ' + e.message, 'error');
  }
}

// ============================================
// Check Chaturbate login status
// ============================================
async function checkChaturbateStatus() {
  var statusEl = document.getElementById('cbStatus');
  var usernameRow = document.getElementById('cbUsernameRow');
  var usernameEl = document.getElementById('cbUsername');
  var loginForm = document.getElementById('cbLoginForm');
  var loggedInActions = document.getElementById('cbLoggedInActions');

  try {
    var res = await fetch('/api/chaturbate/status');
    if (res.ok) {
      var data = await res.json();

      if (data.isLoggedIn) {
        statusEl.className = 'status-indicator connected';
        statusEl.textContent = 'Connected';
        usernameRow.style.display = 'flex';
        usernameEl.textContent = data.username || 'Unknown';
        loginForm.style.display = 'none';
        loggedInActions.style.display = 'block';
      } else {
        statusEl.className = 'status-indicator disconnected';
        statusEl.textContent = 'Not Connected';
        usernameRow.style.display = 'none';
        loginForm.style.display = 'block';
        loggedInActions.style.display = 'none';
      }
    } else if (res.status === 404) {
      statusEl.className = 'status-indicator unknown';
      statusEl.textContent = 'Not Available';
      loginForm.style.display = 'none';
      loggedInActions.style.display = 'none';
    } else {
      statusEl.className = 'status-indicator disconnected';
      statusEl.textContent = 'Error';
      loginForm.style.display = 'block';
      loggedInActions.style.display = 'none';
    }
  } catch (e) {
    console.error('Error checking Chaturbate status:', e);
    statusEl.className = 'status-indicator unknown';
    statusEl.textContent = 'Unavailable';
    loginForm.style.display = 'block';
    loggedInActions.style.display = 'none';
  }
}

// ============================================
// Login to Chaturbate
// ============================================
async function loginChaturbate(event) {
  event.preventDefault();

  var username = document.getElementById('cbUser').value.trim();
  var password = document.getElementById('cbPass').value;
  var loginBtn = document.getElementById('cbLoginBtn');

  if (!username || !password) {
    showNotification('Please enter both username and password', 'error');
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = 'Logging in...';

  try {
    var res = await fetch('/api/chaturbate/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username,
        password: password
      })
    });

    if (res.ok) {
      var data = await res.json();
      showNotification('Successfully connected to Chaturbate!', 'success');
      document.getElementById('cbUser').value = '';
      document.getElementById('cbPass').value = '';
      await checkChaturbateStatus();
    } else {
      var err = {};
      try { err = await res.json(); } catch (e2) {}
      showNotification(err.detail || 'Login failed. Check your credentials.', 'error');
    }
  } catch (e) {
    console.error('Error logging in:', e);
    showNotification('Connection error', 'error');
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = 'Log In';
  }
}

// ============================================
// Logout from Chaturbate
// ============================================
async function logoutChaturbate() {
  if (!confirm('Disconnect your Chaturbate account?')) return;

  try {
    var res = await fetch('/api/chaturbate/logout', { method: 'POST' });
    if (res.ok) {
      showNotification('Chaturbate account disconnected', 'success');
      await checkChaturbateStatus();
    } else {
      showNotification('Failed to disconnect', 'error');
    }
  } catch (e) {
    console.error('Error logging out:', e);
    showNotification('Connection error', 'error');
  }
}

// ============================================
// Check FlareSolverr status
// ============================================
async function checkFlareSolverr(manual) {
  var statusEl = document.getElementById('flareStatus');
  var versionRow = document.getElementById('flareVersionRow');
  var versionEl = document.getElementById('flareVersion');
  var urlEl = document.getElementById('flareUrl');
  var messageRow = document.getElementById('flareMessageRow');
  var messageEl = document.getElementById('flareMessage');
  var testBtn = document.getElementById('flareTestBtn');

  if (manual && testBtn) {
    testBtn.disabled = true;
    testBtn.textContent = 'Testing...';
  }
  statusEl.className = 'status-indicator unknown';
  statusEl.textContent = 'Checking...';

  try {
    var res = await fetch('/api/chaturbate/status', { cache: 'no-store' });
    if (res.ok) {
      var data = await res.json();

      if (data.flaresolverrAvailable) {
        statusEl.className = 'status-indicator connected';
        statusEl.textContent = 'Healthy';
      } else {
        statusEl.className = 'status-indicator disconnected';
        statusEl.textContent = 'Not Available';
      }

      if (data.flaresolverrMessage) {
        if (messageRow) messageRow.style.display = '';
        if (messageEl) messageEl.textContent = data.flaresolverrMessage;
      }

      if (data.flaresolverrVersion && versionRow && versionEl) {
        versionRow.style.display = '';
        versionEl.textContent = data.flaresolverrVersion;
      }

      if (data.flaresolverrUrl && urlEl) {
        urlEl.textContent = data.flaresolverrUrl;
      }

      if (manual) {
        showNotification(
          data.flaresolverrAvailable ? 'FlareSolverr reachable' : 'FlareSolverr: ' + (data.flaresolverrMessage || 'unreachable'),
          data.flaresolverrAvailable ? 'success' : 'error'
        );
      }
    } else {
      statusEl.className = 'status-indicator unknown';
      statusEl.textContent = 'Unknown';
    }
  } catch (e) {
    statusEl.className = 'status-indicator unknown';
    statusEl.textContent = 'Not Available';
    if (messageEl) messageEl.textContent = 'Network error reaching P-StreamRec API';
    if (messageRow) messageRow.style.display = '';
  } finally {
    if (manual && testBtn) {
      testBtn.disabled = false;
      testBtn.textContent = 'Test connection';
    }
  }
}

// ============================================
// Load app version and config
// ============================================
async function loadAppInfo() {
  try {
    var res = await fetch('/api/version');
    if (res.ok) {
      var data = await res.json();
      document.getElementById('appVersionSetting').textContent = 'v' + (data.version || 'unknown');

      if (data.output_dir || data.config) {
        var config = data.config || data;
        if (config.output_dir) document.getElementById('outputDir').textContent = config.output_dir;
        if (config.ffmpeg_path) document.getElementById('ffmpegPath').textContent = config.ffmpeg_path;
        if (config.check_interval) document.getElementById('checkInterval').textContent = config.check_interval + 's';
      }
    }
  } catch (e) {
    console.error('Error loading app info:', e);
    document.getElementById('apiStatus').className = 'status-indicator disconnected';
    document.getElementById('apiStatus').textContent = 'Disconnected';
  }
}

// ============================================
// Recording Settings (auto_convert, keep_ts)
// ============================================

async function loadRecordingSettings() {
  try {
    var res = await fetch('/api/settings/recording');
    if (res.ok) {
      var data = await res.json();
      var autoConvertToggle = document.getElementById('autoConvertToggle');
      var keepTsToggle = document.getElementById('keepTsToggle');
      var showTsToggle = document.getElementById('showTsToggle');
      var autoDeleteToggle = document.getElementById('autoDeleteToggle');
      var autoDeleteThreshold = document.getElementById('autoDeleteThreshold');
      var thresholdRow = document.getElementById('autoDeleteThresholdRow');
      var thresholdValue = document.getElementById('thresholdValue');

      if (autoConvertToggle) autoConvertToggle.checked = !!data.auto_convert;
      if (keepTsToggle) keepTsToggle.checked = !!data.keep_ts;
      if (showTsToggle) showTsToggle.checked = !!data.show_ts_files;
      if (autoDeleteToggle) {
        autoDeleteToggle.checked = !!data.auto_delete_watched;
        if (thresholdRow) thresholdRow.style.display = data.auto_delete_watched ? 'flex' : 'none';
      }
      if (autoDeleteThreshold) {
        var thresh = data.auto_delete_threshold || 90;
        autoDeleteThreshold.value = thresh;
        if (thresholdValue) thresholdValue.textContent = thresh + '%';
      }
      var maxResSelect = document.getElementById('maxResolutionSelect');
      if (maxResSelect) {
        maxResSelect.value = String(data.max_resolution || 0);
      }
      var defaultResSelect = document.getElementById('defaultResolutionSelect');
      if (defaultResSelect) {
        defaultResSelect.value = String(data.default_resolution || 0);
      }
    }
  } catch (e) {
    console.error('Error loading recording settings:', e);
  }
}

async function updateRecordingSetting(key, value) {
  try {
    var body = {};
    body[key] = value;
    var res = await fetch('/api/settings/recording', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (res.ok) {
      showNotification('Setting updated', 'success');
      // Toggle threshold row visibility when auto_delete_watched changes
      if (key === 'auto_delete_watched') {
        var thresholdRow = document.getElementById('autoDeleteThresholdRow');
        if (thresholdRow) thresholdRow.style.display = value ? 'flex' : 'none';
      }
    } else {
      showNotification('Failed to update setting', 'error');
      loadRecordingSettings();
    }
  } catch (e) {
    console.error('Error updating recording setting:', e);
    showNotification('Connection error', 'error');
    loadRecordingSettings();
  }
}

// ============================================
// Notifications
// ============================================
function showNotification(message, type) {
  type = type || 'success';
  var notif = document.createElement('div');
  var bgColor = type === 'success' ? '#10b981' : '#ef4444';
  notif.style.cssText = 'position:fixed;top:20px;right:20px;background:' + bgColor + ';color:white;padding:1rem 1.5rem;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,0.3);z-index:9999;font-weight:500;animation:slideIn 0.3s ease-out;';
  notif.textContent = message;
  document.body.appendChild(notif);

  setTimeout(function() {
    notif.style.opacity = '0';
    notif.style.transform = 'translateX(100px)';
    notif.style.transition = 'all 0.3s ease-out';
    setTimeout(function() { notif.remove(); }, 300);
  }, 3000);
}

// ============================================
// Tag Blacklist Management
// ============================================

let blacklistedTags = [];

async function loadBlacklistedTags() {
  try {
    var res = await fetch('/api/settings/blacklisted-tags');
    if (res.ok) {
      var data = await res.json();
      blacklistedTags = data.tags || [];
      renderBlacklistedTags();
    }
  } catch (e) {
    console.error('Error loading blacklisted tags:', e);
  }
}

function renderBlacklistedTags() {
  var container = document.getElementById('blacklistedTagsList');
  if (!container) return;

  if (blacklistedTags.length === 0) {
    container.innerHTML = '<span style="font-size: 0.85rem; color: var(--text-muted);">No blacklisted tags yet.</span>';
    return;
  }

  container.innerHTML = blacklistedTags.map(function(tag) {
    return '<span style="display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.7rem; border-radius: 6px; background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.85rem; font-weight: 500;">' +
      escapeHtml(tag) +
      '<button onclick="removeBlacklistedTag(\'' + escapeHtml(tag) + '\')" style="background: none; border: none; color: #f87171; cursor: pointer; font-size: 1.1rem; padding: 0; line-height: 1;">&times;</button>' +
    '</span>';
  }).join('');
}

async function addBlacklistedTag() {
  var input = document.getElementById('blacklistInput');
  var tag = input.value.trim().toLowerCase();
  if (!tag) return;
  if (blacklistedTags.indexOf(tag) !== -1) {
    showNotification('Tag already blacklisted', 'error');
    return;
  }

  blacklistedTags.push(tag);
  input.value = '';

  try {
    var res = await fetch('/api/settings/blacklisted-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: blacklistedTags })
    });
    if (res.ok) {
      renderBlacklistedTags();
      showNotification('Tag "' + tag + '" blacklisted', 'success');
    } else {
      blacklistedTags.pop();
      showNotification('Failed to save', 'error');
    }
  } catch (e) {
    blacklistedTags.pop();
    showNotification('Connection error', 'error');
  }
}

async function removeBlacklistedTag(tag) {
  blacklistedTags = blacklistedTags.filter(function(t) { return t !== tag; });

  try {
    var res = await fetch('/api/settings/blacklisted-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: blacklistedTags })
    });
    if (res.ok) {
      renderBlacklistedTags();
      showNotification('Tag removed', 'success');
    }
  } catch (e) {
    showNotification('Connection error', 'error');
  }
}

function escapeHtml(text) {
  if (!text) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ============================================
// System Statistics
// ============================================

function formatBytes(bytes) {
  if (bytes === 0 || bytes == null) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
  if (i >= units.length) i = units.length - 1;
  return (bytes / Math.pow(1024, i)).toFixed(i > 1 ? 1 : 0) + ' ' + units[i];
}

function formatNumber(num) {
  if (num == null) return '-';
  return num.toLocaleString();
}

function formatUptime(seconds) {
  if (!seconds) return '-';
  var d = Math.floor(seconds / 86400);
  var h = Math.floor((seconds % 86400) / 3600);
  var m = Math.floor((seconds % 3600) / 60);
  var parts = [];
  if (d > 0) parts.push(d + 'd');
  if (h > 0) parts.push(h + 'h');
  parts.push(m + 'm');
  return parts.join(' ');
}

function setGauge(id, percent, color) {
  var el = document.getElementById(id);
  if (!el) return;
  var circumference = 2 * Math.PI * 50; // r=50
  var offset = circumference - (percent / 100) * circumference;
  el.style.strokeDasharray = circumference;
  el.style.strokeDashoffset = offset;
  if (color) el.style.stroke = color;
}

function getGaugeColor(percent) {
  if (percent < 50) return '#10b981';
  if (percent < 75) return '#f59e0b';
  return '#ef4444';
}

async function loadSystemStats() {
  try {
    var res = await fetch('/api/system/stats');
    if (!res.ok) {
      console.error('Failed to load stats:', res.status);
      return;
    }
    var data = await res.json();
    renderStats(data);
  } catch (e) {
    console.error('Error loading system stats:', e);
  }
}

function renderStats(data) {
  // --- System Overview ---
  var el;
  el = document.getElementById('stat-uptime');
  if (el) el.textContent = formatUptime(data.process.uptime_seconds);
  el = document.getElementById('stat-pid');
  if (el) el.textContent = data.process.pid;
  el = document.getElementById('stat-threads');
  if (el) el.textContent = data.process.threads;
  el = document.getElementById('stat-active-rec');
  if (el) el.textContent = data.sessions.active_count;

  // --- Disk ---
  var diskPct = data.disk.percent;
  setGauge('disk-gauge', diskPct, getGaugeColor(diskPct));
  el = document.getElementById('disk-gauge-text');
  if (el) el.textContent = diskPct + '%';
  el = document.getElementById('disk-gauge-sub');
  if (el) el.textContent = formatBytes(data.disk.free) + ' free';
  el = document.getElementById('stat-disk-total');
  if (el) el.textContent = formatBytes(data.disk.total);
  el = document.getElementById('stat-disk-used');
  if (el) el.textContent = formatBytes(data.disk.used);
  el = document.getElementById('stat-disk-free');
  if (el) el.textContent = formatBytes(data.disk.free);

  // --- CPU ---
  var cpuPct = data.cpu.usage_percent;
  setGauge('cpu-gauge', cpuPct, getGaugeColor(cpuPct));
  el = document.getElementById('cpu-gauge-text');
  if (el) el.textContent = cpuPct.toFixed(1) + '%';
  el = document.getElementById('cpu-gauge-sub');
  if (el) el.textContent = (data.cpu.cores_logical || 0) + ' cores';
  el = document.getElementById('stat-cpu-physical');
  if (el) el.textContent = data.cpu.cores_physical || '-';
  el = document.getElementById('stat-cpu-logical');
  if (el) el.textContent = data.cpu.cores_logical || '-';
  el = document.getElementById('stat-cpu-freq');
  if (el) {
    if (data.cpu.frequency && data.cpu.frequency.current) {
      el.textContent = Math.round(data.cpu.frequency.current) + ' MHz';
    } else {
      el.textContent = '-';
    }
  }

  // CPU cores visualization
  var coresEl = document.getElementById('stat-cpu-cores');
  if (coresEl && data.cpu.per_core) {
    coresEl.innerHTML = data.cpu.per_core.map(function(pct, i) {
      var bg = getGaugeColor(pct);
      var alpha = Math.max(0.15, pct / 100);
      return '<div class="stats-core" style="background: ' + bg + '; opacity: ' + (0.3 + alpha * 0.7).toFixed(2) + ';" title="Core ' + i + ': ' + pct.toFixed(0) + '%">' + pct.toFixed(0) + '</div>';
    }).join('');
  }

  // --- RAM ---
  var ramPct = data.ram.percent;
  setGauge('ram-gauge', ramPct, getGaugeColor(ramPct));
  el = document.getElementById('ram-gauge-text');
  if (el) el.textContent = ramPct.toFixed(1) + '%';
  el = document.getElementById('ram-gauge-sub');
  if (el) el.textContent = formatBytes(data.ram.used) + ' used';
  el = document.getElementById('stat-ram-total');
  if (el) el.textContent = formatBytes(data.ram.total);
  el = document.getElementById('stat-ram-used');
  if (el) el.textContent = formatBytes(data.ram.used);
  el = document.getElementById('stat-ram-available');
  if (el) el.textContent = formatBytes(data.ram.available);

  // --- Storage Breakdown ---
  var storage = data.storage;
  var totalStorage = storage.ts_files.size + storage.mp4_files.size + storage.thumbnails.size + storage.other_files.size;

  // Storage bar
  var barEl = document.getElementById('storage-bar');
  if (barEl && totalStorage > 0) {
    var segments = [
      { size: storage.ts_files.size, color: '#6366f1', label: 'TS' },
      { size: storage.mp4_files.size, color: '#10b981', label: 'MP4' },
      { size: storage.thumbnails.size, color: '#f59e0b', label: 'Thumbs' },
      { size: storage.other_files.size, color: '#6b7280', label: 'Other' },
    ];
    barEl.innerHTML = segments.map(function(s) {
      var pct = (s.size / totalStorage * 100);
      if (pct < 0.5) return '';
      return '<div class="stats-storage-segment" style="width: ' + pct.toFixed(1) + '%; background: ' + s.color + ';" title="' + s.label + ': ' + formatBytes(s.size) + '"></div>';
    }).join('');
  } else if (barEl) {
    barEl.innerHTML = '<div style="height:100%;width:100%;display:flex;align-items:center;justify-content:center;font-size:0.75rem;color:var(--text-muted);">No data</div>';
  }

  el = document.getElementById('stat-ts-info');
  if (el) el.textContent = formatBytes(storage.ts_files.size) + ' (' + storage.ts_files.count + ' files)';
  el = document.getElementById('stat-mp4-info');
  if (el) el.textContent = formatBytes(storage.mp4_files.size) + ' (' + storage.mp4_files.count + ' files)';
  el = document.getElementById('stat-thumb-info');
  if (el) el.textContent = formatBytes(storage.thumbnails.size) + ' (' + storage.thumbnails.count + ' files)';
  el = document.getElementById('stat-other-info');
  if (el) el.textContent = formatBytes(storage.other_files.size) + ' (' + storage.other_files.count + ' files)';
  el = document.getElementById('stat-total-rec-size');
  if (el) el.textContent = formatBytes(storage.total_recordings_size);

  // --- Process Resources ---
  el = document.getElementById('stat-proc-cpu');
  if (el) el.textContent = data.process.cpu_percent.toFixed(1) + '%';
  el = document.getElementById('stat-proc-mem');
  if (el) el.textContent = formatBytes(data.process.memory_rss);
  el = document.getElementById('stat-proc-vms');
  if (el) el.textContent = formatBytes(data.process.memory_vms);
  el = document.getElementById('stat-proc-files');
  if (el) el.textContent = data.process.open_files;
  el = document.getElementById('stat-proc-conn');
  if (el) el.textContent = data.process.connections;

  // --- Network I/O ---
  el = document.getElementById('stat-net-recv');
  if (el) el.textContent = formatBytes(data.network.bytes_recv);
  el = document.getElementById('stat-net-sent');
  if (el) el.textContent = formatBytes(data.network.bytes_sent);
  el = document.getElementById('stat-net-pin');
  if (el) el.textContent = formatNumber(data.network.packets_recv);
  el = document.getElementById('stat-net-pout');
  if (el) el.textContent = formatNumber(data.network.packets_sent);

  // --- Child Processes ---
  var childrenEl = document.getElementById('stats-children-list');
  if (childrenEl) {
    if (data.children.length === 0) {
      childrenEl.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem 0;">No active child processes (ffmpeg, etc.)</p>';
    } else {
      childrenEl.innerHTML = data.children.map(function(c) {
        return '<div class="stats-child-item">' +
          '<span class="stats-child-name" title="' + escapeHtml(c.cmdline) + '">' + escapeHtml(c.name) + ' <span style="color:var(--text-muted);font-size:0.75rem;">PID ' + c.pid + '</span></span>' +
          '<div class="stats-child-meta">' +
            '<span title="CPU">' + c.cpu_percent.toFixed(1) + '% CPU</span>' +
            '<span title="Memory">' + formatBytes(c.memory_rss) + '</span>' +
            '<span style="color:' + (c.status === 'running' ? 'var(--success)' : 'var(--text-muted)') + ';">' + c.status + '</span>' +
          '</div>' +
        '</div>';
      }).join('');
    }
  }

  // --- Top Models by Storage ---
  var topModelsEl = document.getElementById('stats-top-models');
  if (topModelsEl) {
    var models = storage.by_model || [];
    if (models.length === 0) {
      topModelsEl.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem 0;">No recording data yet</p>';
    } else {
      var maxSize = models[0].total_size || 1;
      topModelsEl.innerHTML = models.map(function(m, i) {
        var barPct = (m.total_size / maxSize * 100).toFixed(1);
        return '<div class="stats-model-item">' +
          '<span class="stats-model-rank">' + (i + 1) + '</span>' +
          '<div class="stats-model-info">' +
            '<div class="stats-model-name">' + escapeHtml(m.username) + '</div>' +
            '<div class="stats-model-detail">' + m.ts_count + ' TS, ' + m.mp4_count + ' MP4</div>' +
          '</div>' +
          '<div class="stats-model-bar-bg"><div class="stats-model-bar-fill" style="width:' + barPct + '%;"></div></div>' +
          '<span class="stats-model-size">' + formatBytes(m.total_size) + '</span>' +
        '</div>';
      }).join('');
    }
  }
}

// ============================================
// Update System
// ============================================

var lastUpdateData = null;

async function checkForUpdate() {
  var btn = document.getElementById('check-update-btn');
  var statusEl = document.getElementById('update-check-status');
  var latestRow = document.getElementById('update-latest-row');
  var latestEl = document.getElementById('update-latest-version');
  var publishedRow = document.getElementById('update-published-row');
  var publishedEl = document.getElementById('update-published-at');
  var applyBtn = document.getElementById('apply-update-btn');
  var notesContainer = document.getElementById('update-release-notes');
  var notesContent = document.getElementById('update-notes-content');
  var manualEl = document.getElementById('update-manual-commands');

  btn.disabled = true;
  btn.textContent = 'Checking...';
  statusEl.className = 'status-indicator unknown';
  statusEl.textContent = 'Checking...';
  applyBtn.style.display = 'none';
  notesContainer.style.display = 'none';
  manualEl.style.display = 'none';

  try {
    var res = await fetch('/api/system/check-update');
    if (!res.ok) {
      statusEl.className = 'status-indicator disconnected';
      statusEl.textContent = 'Error';
      showNotification('Failed to check for updates', 'error');
      return;
    }

    var data = await res.json();
    lastUpdateData = data;

    if (data.error && !data.latest_version) {
      statusEl.className = 'status-indicator disconnected';
      statusEl.textContent = 'Error';
      showNotification('Update check failed: ' + data.error, 'error');
      return;
    }

    // Show latest version
    latestRow.style.display = 'flex';
    latestEl.textContent = 'v' + (data.latest_version || 'unknown');

    if (data.published_at) {
      publishedRow.style.display = 'flex';
      var date = new Date(data.published_at);
      publishedEl.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    }

    if (data.update_available) {
      statusEl.className = 'status-indicator unknown';
      statusEl.textContent = 'Update available';

      if (data.release_notes) {
        notesContainer.style.display = 'block';
        notesContent.textContent = data.release_notes;
      }

      if (data.docker_available) {
        applyBtn.style.display = 'inline-flex';
      } else {
        // Docker socket not mounted — show manual commands directly
        applyBtn.style.display = 'none';
        var commandsText = document.getElementById('update-commands-text');
        manualEl.style.display = 'block';
        commandsText.textContent = 'docker compose pull && docker compose up -d';
      }

      showNotification('Update available: v' + data.latest_version, 'success');
    } else {
      statusEl.className = 'status-indicator connected';
      statusEl.textContent = 'Up to date';
      showNotification('You are running the latest version', 'success');
    }
  } catch (e) {
    console.error('Error checking for updates:', e);
    statusEl.className = 'status-indicator disconnected';
    statusEl.textContent = 'Error';
    showNotification('Connection error', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Check for Updates';
  }
}

async function applyUpdate() {
  var applyBtn = document.getElementById('apply-update-btn');
  var progressEl = document.getElementById('update-progress');
  var progressBar = document.getElementById('update-progress-bar');
  var progressText = document.getElementById('update-progress-text');
  var manualEl = document.getElementById('update-manual-commands');
  var commandsText = document.getElementById('update-commands-text');

  if (!confirm('Update to the latest version? The application will restart.')) return;

  applyBtn.disabled = true;
  applyBtn.textContent = 'Updating...';
  progressEl.style.display = 'block';
  progressBar.style.width = '10%';
  progressText.textContent = 'Pulling latest image...';

  try {
    progressBar.style.width = '30%';
    var res = await fetch('/api/system/update', { method: 'POST' });
    var data = await res.json();

    if (data.success) {
      progressBar.style.width = '80%';
      progressText.textContent = 'Restarting application...';

      showNotification('Update in progress! Page will reload shortly...', 'success');

      // Poll for the app to come back
      progressBar.style.width = '90%';
      progressText.textContent = 'Waiting for restart...';

      setTimeout(function() {
        progressBar.style.width = '100%';
        waitForRestart();
      }, 5000);
    } else {
      progressBar.style.width = '0%';
      progressEl.style.display = 'none';
      applyBtn.disabled = false;
      applyBtn.textContent = 'Update Now';

      if (data.manual_commands) {
        manualEl.style.display = 'block';
        commandsText.textContent = data.manual_commands;
      }

      showNotification(data.message || 'Update failed', 'error');
    }
  } catch (e) {
    console.error('Error applying update:', e);
    progressBar.style.width = '0%';
    progressEl.style.display = 'none';
    applyBtn.disabled = false;
    applyBtn.textContent = 'Update Now';
    showNotification('Connection error during update', 'error');
  }
}

function waitForRestart() {
  var progressText = document.getElementById('update-progress-text');
  var attempts = 0;
  var maxAttempts = 30;

  var interval = setInterval(function() {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(interval);
      progressText.textContent = 'Restart is taking longer than expected. Please refresh manually.';
      return;
    }

    progressText.textContent = 'Waiting for restart... (' + attempts + 's)';

    fetch('/api/version', { signal: AbortSignal.timeout(3000) })
      .then(function(res) {
        if (res.ok) {
          clearInterval(interval);
          progressText.textContent = 'Updated successfully! Reloading...';
          showNotification('Update complete!', 'success');
          setTimeout(function() { window.location.reload(); }, 1000);
        }
      })
      .catch(function() {
        // Still restarting
      });
  }, 2000);
}

function copyUpdateCommands() {
  var text = document.getElementById('update-commands-text').textContent;
  navigator.clipboard.writeText(text).then(function() {
    showNotification('Commands copied to clipboard', 'success');
  }).catch(function() {
    showNotification('Failed to copy', 'error');
  });
}

// ============================================
// Initialization
// ============================================
window.addEventListener('DOMContentLoaded', function() {
  // Add animation keyframes
  var style = document.createElement('style');
  style.textContent = '@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }';
  document.head.appendChild(style);

  // Initialize tab navigation
  initTabs();

  // Load all data in parallel
  checkChaturbateStatus();
  checkCam4Status();
  checkFlareSolverr();
  loadAppInfo();
  loadBlacklistedTags();
  loadRecordingSettings();

  // Set up blacklist input Enter key
  var blacklistInput = document.getElementById('blacklistInput');
  if (blacklistInput) {
    blacklistInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') addBlacklistedTag();
    });
  }

  // Auto-refresh stats every 30 seconds when on stats tab
  setInterval(function() {
    var statsTab = document.getElementById('tab-statistics');
    if (statsTab && statsTab.classList.contains('active')) {
      loadSystemStats();
    }
  }, 30000);
});

// ============================================
// Logs Viewer
// ============================================

function escapeLogHtml(str) {
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

async function loadLogs() {
  logsOffset = 0;
  var level = document.getElementById('logLevelFilter').value;
  try {
    var url = '/api/logs?limit=200&offset=0';
    if (level) url += '&level=' + level;
    var res = await fetch(url);
    if (!res.ok) return;
    var data = await res.json();
    renderLogs(data.logs, false);
    document.getElementById('logTotal').textContent = data.total;
    logsOffset = data.logs.length;

    // Load error/warning counts
    var errRes = await fetch('/api/logs?level=ERROR&limit=1&offset=0');
    var warnRes = await fetch('/api/logs?level=WARNING&limit=1&offset=0');
    if (errRes.ok) {
      var errData = await errRes.json();
      document.getElementById('logErrors').textContent = errData.total;
    }
    if (warnRes.ok) {
      var warnData = await warnRes.json();
      document.getElementById('logWarnings').textContent = warnData.total;
    }
  } catch (e) {
    console.error('Error loading logs:', e);
  }
}

async function loadMoreLogs() {
  var level = document.getElementById('logLevelFilter').value;
  try {
    var url = '/api/logs?limit=200&offset=' + logsOffset;
    if (level) url += '&level=' + level;
    var res = await fetch(url);
    if (!res.ok) return;
    var data = await res.json();
    if (data.logs.length === 0) {
      document.getElementById('loadMoreLogs').textContent = 'No more logs';
      return;
    }
    renderLogs(data.logs, true);
    logsOffset += data.logs.length;
  } catch (e) {
    console.error('Error loading more logs:', e);
  }
}

function renderLogs(logs, append) {
  var container = document.getElementById('logsContainer');
  if (!append) container.innerHTML = '';

  if (logs.length === 0 && !append) {
    container.innerHTML = '<p style="color: var(--text-muted); padding: 2rem; text-align: center;">No logs found</p>';
    return;
  }

  var html = logs.map(function(log) {
    var time = log.timestamp.split(' ')[1] || log.timestamp;
    return '<div class="log-entry">' +
      '<span class="log-timestamp">' + escapeLogHtml(time) + '</span>' +
      '<span class="log-level log-level-' + log.level + '">' + log.level + '</span>' +
      '<span class="log-module">' + escapeLogHtml(log.module) + '</span>' +
      '<span class="log-message">' + escapeLogHtml(log.message) + '</span>' +
    '</div>';
  }).join('');

  container.insertAdjacentHTML('beforeend', html);
  document.getElementById('loadMoreLogs').textContent = 'Load More';
}

// ============================================
// Processes tab — live ffmpeg process inspector
// ============================================
var processesPollInterval = null;
var processesExpanded = {};   // session_id -> expanded?
var processesLastSnap = {};   // session_id -> last snapshot (for partial updates)
var PROCESSES_REFRESH_MS = 10000;

function startProcessesPolling() {
  if (processesPollInterval) return;
  refreshProcesses();
  processesPollInterval = setInterval(refreshProcesses, PROCESSES_REFRESH_MS);
}

function stopProcessesPolling() {
  if (processesPollInterval) {
    clearInterval(processesPollInterval);
    processesPollInterval = null;
  }
}

function fmtBytes(n) {
  if (n == null) return '-';
  var u = ['B', 'KB', 'MB', 'GB', 'TB'];
  var i = 0;
  var v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(i === 0 ? 0 : 1) + ' ' + u[i];
}

function fmtDuration(secs) {
  if (secs == null) return '-';
  secs = Math.max(0, Math.floor(secs));
  var h = Math.floor(secs / 3600);
  var m = Math.floor((secs % 3600) / 60);
  var s = secs % 60;
  if (h > 0) return h + 'h ' + (m < 10 ? '0' : '') + m + 'm';
  if (m > 0) return m + 'm ' + (s < 10 ? '0' : '') + s + 's';
  return s + 's';
}

function escapeProcHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function statusDotClass(p) {
  if (!p.running || !p.pid) return 'stopped';
  if (p.status === 'Z') return 'zombie';
  return '';
}

async function refreshProcesses() {
  var tbody = document.getElementById('proc-tbody');
  if (!tbody) return;
  try {
    var res = await fetch('/api/processes');
    if (!res.ok) {
      tbody.innerHTML = '<tr><td colspan="10" class="proc-empty">Failed to load (' + res.status + ')</td></tr>';
      return;
    }
    var data = await res.json();
    renderProcesses(data);
  } catch (e) {
    console.error('refreshProcesses:', e);
    tbody.innerHTML = '<tr><td colspan="10" class="proc-empty">Connection error</td></tr>';
  }
}

function renderProcesses(data) {
  var procs = (data && data.processes) || [];
  var totals = (data && data.totals) || {};
  var tbody = document.getElementById('proc-tbody');
  var totalsEl = document.getElementById('proc-totals');
  var badgeEl = document.getElementById('processesCountBadge');

  if (badgeEl) {
    badgeEl.textContent = totals.active || 0;
    if (totals.active > 0) badgeEl.classList.add('active');
    else badgeEl.classList.remove('active');
  }

  if (totalsEl) {
    totalsEl.textContent = (totals.active || 0) + ' active / ' + (totals.total || 0) +
      ' · CPU ' + (totals.cpu_percent_sum != null ? totals.cpu_percent_sum.toFixed(1) : '?') + '%' +
      ' · RAM ' + fmtBytes(totals.rss_bytes_sum || 0) +
      ' · ' + (totals.host_cores || '?') + ' cores';
  }

  if (procs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="proc-empty">No active ffmpeg processes</td></tr>';
    processesLastSnap = {};
    return;
  }

  var rows = procs.map(function(p) {
    processesLastSnap[p.session_id] = p;
    var dot = '<span class="proc-status-dot ' + statusDotClass(p) + '" title="' + escapeProcHtml(p.status || '?') + '"></span>';
    var actions =
      '<button class="proc-action-btn"        onclick="event.stopPropagation(); procStop(\'' + escapeProcHtml(p.session_id) + '\')"    title="Stop (graceful)">&#9209;</button>' +
      '<button class="proc-action-btn"        onclick="event.stopPropagation(); procRestart(\'' + escapeProcHtml(p.session_id) + '\')" title="Restart (stop + monitor re-spawns)">&#8635;</button>' +
      '<button class="proc-action-btn danger" onclick="event.stopPropagation(); procKill(\'' + escapeProcHtml(p.session_id) + '\')"    title="Force kill (SIGKILL)">&#9760;</button>' +
      '<button class="proc-action-btn"        onclick="event.stopPropagation(); procPreview(\'' + escapeProcHtml(p.playback_url || '') + '\')" title="Open HLS preview">&#9654;</button>';

    var row = '<tr class="proc-row" data-sid="' + escapeProcHtml(p.session_id) + '" onclick="toggleProcRow(\'' + escapeProcHtml(p.session_id) + '\')">' +
      '<td>' + dot + '</td>' +
      '<td>' + (p.pid != null ? p.pid : '-') + '</td>' +
      '<td>' + escapeProcHtml(p.person || p.name || '-') + '</td>' +
      '<td>' + fmtDuration(p.uptime_seconds) + '</td>' +
      '<td>' + (p.cpu_percent != null ? p.cpu_percent.toFixed(1) : '-') + '</td>' +
      '<td>' + fmtBytes(p.rss_bytes) + '</td>' +
      '<td>' + escapeProcHtml(p.quality || '-') + '</td>' +
      '<td>' + fmtBytes(p.record_size_bytes) + '</td>' +
      '<td>' + (p.segment_count != null ? p.segment_count : '-') + '</td>' +
      '<td class="proc-actions">' + actions + '</td>' +
    '</tr>';
    var detail = '';
    if (processesExpanded[p.session_id]) {
      detail = '<tr class="proc-detail-row" data-sid="' + escapeProcHtml(p.session_id) + '">' +
                 '<td colspan="10" style="padding:0;"><div class="proc-detail" id="proc-detail-' + escapeProcHtml(p.session_id) + '">' +
                   renderProcDetail(p) +
                 '</div></td>' +
               '</tr>';
    }
    return row + detail;
  });

  tbody.innerHTML = rows.join('');

  // Refresh log tail for each currently-expanded row (fire-and-forget)
  Object.keys(processesExpanded).forEach(function(sid) {
    if (processesExpanded[sid]) loadProcessLog(sid);
  });
}

function renderProcDetail(p) {
  var input = p.input_url || '-';
  var inputShort = input.length > 80 ? input.slice(0, 80) + '…' : input;
  var io = '';
  if (p.io_read_bytes != null || p.io_write_bytes != null) {
    io = '<div class="kv"><span class="k">IO read</span><span class="v">' + fmtBytes(p.io_read_bytes) + '</span></div>' +
         '<div class="kv"><span class="k">IO write</span><span class="v">' + fmtBytes(p.io_write_bytes) + '</span></div>';
  }
  return '' +
    '<h4>Process</h4>' +
    '<div class="kv"><span class="k">Session</span><span class="v">' + escapeProcHtml(p.session_id) + '</span></div>' +
    '<div class="kv"><span class="k">PID</span><span class="v">' + (p.pid != null ? p.pid : '-') + '</span></div>' +
    '<div class="kv"><span class="k">State</span><span class="v">' + escapeProcHtml(p.status || '?') + '</span></div>' +
    '<div class="kv"><span class="k">Started</span><span class="v">' + escapeProcHtml(p.start_date || '-') + '</span></div>' +
    '<div class="kv"><span class="k">Uptime</span><span class="v">' + fmtDuration(p.uptime_seconds) + '</span></div>' +
    '<div class="kv"><span class="k">Threads</span><span class="v">' + (p.num_threads != null ? p.num_threads : '-') + '</span></div>' +
    '<div class="kv"><span class="k">FDs</span><span class="v">' + (p.num_fds != null ? p.num_fds : '-') + '</span></div>' +
    '<div class="kv"><span class="k">Nice</span><span class="v">' + (p.nice != null ? p.nice : '-') + '</span></div>' +
    '<h4>Resources</h4>' +
    '<div class="kv"><span class="k">CPU</span><span class="v">' + (p.cpu_percent != null ? p.cpu_percent.toFixed(1) + ' %' : '-') + '</span></div>' +
    '<div class="kv"><span class="k">RSS</span><span class="v">' + fmtBytes(p.rss_bytes) + '</span></div>' +
    '<div class="kv"><span class="k">VSZ</span><span class="v">' + fmtBytes(p.vsz_bytes) + '</span></div>' +
    io +
    '<h4>Paths</h4>' +
    '<div class="kv"><span class="k">Quality</span><span class="v">' + escapeProcHtml(p.record_quality || '?') + ' &rarr; ' + escapeProcHtml(p.quality || '?') + ' (effective)</span></div>' +
    '<div class="kv"><span class="k">Input m3u8</span><span class="v">' + escapeProcHtml(inputShort) +
      '<button class="copy-btn" onclick="event.stopPropagation(); navigator.clipboard.writeText(' + JSON.stringify(input) + ').catch(function(){})">copy</button>' +
    '</span></div>' +
    '<div class="kv"><span class="k">Output</span><span class="v">' + escapeProcHtml(p.record_path || '-') + '</span></div>' +
    '<div class="kv"><span class="k">HLS</span><span class="v">' + escapeProcHtml(p.playback_url || '-') + '</span></div>' +
    '<div class="kv"><span class="k">Segments</span><span class="v">' + (p.segment_count != null ? p.segment_count : '-') +
      ' (' + fmtBytes(p.segment_bytes || 0) + ')</span></div>' +
    '<h4>FFmpeg log (tail)</h4>' +
    '<pre class="proc-log" id="proc-log-' + escapeProcHtml(p.session_id) + '">loading…</pre>';
}

function toggleProcRow(sid) {
  processesExpanded[sid] = !processesExpanded[sid];
  refreshProcesses();
}

async function loadProcessLog(sid) {
  var el = document.getElementById('proc-log-' + sid);
  if (!el) return;
  try {
    var res = await fetch('/api/processes/' + encodeURIComponent(sid) + '/log?lines=30');
    if (!res.ok) { el.textContent = '(log unavailable: ' + res.status + ')'; return; }
    var data = await res.json();
    var lines = data.lines || [];
    el.textContent = lines.length ? lines.join('\n') : '(empty)';
  } catch (e) {
    el.textContent = '(log fetch error)';
  }
}

async function procStop(sid) {
  if (!confirm('Stop ffmpeg session ' + sid + '? The auto-monitor may re-spawn it shortly if auto-record is on.')) return;
  try {
    var res = await fetch('/api/processes/' + encodeURIComponent(sid) + '/stop', { method: 'POST' });
    if (res.ok) showNotification('Stopped ' + sid, 'success');
    else        showNotification('Failed to stop', 'error');
  } catch (e) { showNotification('Connection error', 'error'); }
  setTimeout(refreshProcesses, 500);
}

async function procKill(sid) {
  if (!confirm('Force-kill (SIGKILL) ffmpeg session ' + sid + '?\n\nUse only if a graceful stop is hanging.')) return;
  try {
    var res = await fetch('/api/processes/' + encodeURIComponent(sid) + '/kill', { method: 'POST' });
    if (res.ok) showNotification('Killed ' + sid, 'success');
    else        showNotification('Failed to kill', 'error');
  } catch (e) { showNotification('Connection error', 'error'); }
  setTimeout(refreshProcesses, 500);
}

async function procRestart(sid) {
  if (!confirm('Restart ffmpeg session ' + sid + '?\n\nThis stops the current process; the auto-monitor will re-spawn it within a few seconds with a freshly-resolved URL.')) return;
  try {
    var res = await fetch('/api/processes/' + encodeURIComponent(sid) + '/restart', { method: 'POST' });
    if (res.ok) showNotification('Restart queued for ' + sid, 'success');
    else        showNotification('Failed to restart', 'error');
  } catch (e) { showNotification('Connection error', 'error'); }
  setTimeout(refreshProcesses, 1500);
}

function procPreview(url) {
  if (!url) { showNotification('No HLS URL for this session', 'error'); return; }
  // Open in a new tab; the existing /watch page can render arbitrary HLS via Hls.js,
  // but the simplest reliable fallback is opening the m3u8 directly.
  window.open(url, '_blank', 'noopener');
}

async function stopAllProcesses() {
  var snap = Object.keys(processesLastSnap);
  if (snap.length === 0) { showNotification('Nothing to stop', 'success'); return; }
  if (!confirm('Stop ALL ' + snap.length + ' ffmpeg sessions?\n\nAuto-monitor may re-spawn them if auto-record is on.')) return;
  for (var i = 0; i < snap.length; i++) {
    try {
      await fetch('/api/processes/' + encodeURIComponent(snap[i]) + '/stop', { method: 'POST' });
    } catch (e) {}
  }
  showNotification('Stop requested for ' + snap.length + ' sessions', 'success');
  setTimeout(refreshProcesses, 800);
}

// Reuse the global notification helper if present, else fall back to alert.
if (typeof showNotification !== 'function') {
  // minimal fallback so the file is self-contained even if loaded standalone
  window.showNotification = function(msg) { console.log(msg); };
}
