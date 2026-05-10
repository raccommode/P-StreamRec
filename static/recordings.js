// ============================================
// Recordings Page - Model cards + recording list
// ============================================

// State
let allRecordings = {};
let currentDetailUser = '';
let currentPlayer = null;
let showTsFiles = false;
let currentPlayingRecordingId = '';
let currentPlayingUsername = '';
let currentPlayingFilename = '';
let currentDetailModel = null;        // cached settings for the open model
let currentDetailRecordings = [];     // cached recordings used for timeline
let timelineNowInterval = null;       // setInterval id for the blinking-now line update
let globalMaxResolution = 0;          // 0 = no global cap; otherwise pixel height
let globalDefaultResolution = 0;      // 0 = "best"; otherwise pixel height (used when enrolling new models)

// ============================================
// Load recordings grouped by model
// ============================================
async function loadShowTsSetting() {
  try {
    var res = await fetch('/api/settings/recording');
    if (res.ok) {
      var data = await res.json();
      showTsFiles = !!data.show_ts_files;
      globalMaxResolution = parseInt(data.max_resolution, 10) || 0;
      globalDefaultResolution = parseInt(data.default_resolution, 10) || 0;
    }
  } catch (e) {
    console.error('Error loading show_ts setting:', e);
  }
}

// Map "best", "1080p", "480", etc. to a numeric height (0 = best/none).
function qualityToHeight(q) {
  if (!q) return 0;
  var s = String(q).trim().toLowerCase();
  if (s === 'best' || s === 'auto' || s === 'highest') return 0;
  var m = s.match(/^(\d+)\s*p?$/);
  return m ? parseInt(m[1], 10) : 0;
}

// Combine per-model quality with the global cap. Mirrors the server logic.
function effectiveHeight(modelQuality, globalCap) {
  var perModel = qualityToHeight(modelQuality);
  if (globalCap && perModel) return Math.min(globalCap, perModel);
  return perModel || globalCap || 0;  // 0 means "best available"
}

async function loadRecordingsByModel() {
  try {
    var res = await fetch('/api/recordings-by-model?show_ts=' + showTsFiles);
    if (res.ok) {
      var data = await res.json();
      return data.models || [];
    }
  } catch (e) {
    console.error('Error loading recordings by model:', e);
  }
  return [];
}

// ============================================
// Load all recordings for flat stats
// ============================================
async function loadAllRecordings() {
  try {
    var res = await fetch('/api/all-recordings?limit=10000&show_ts=' + showTsFiles);
    if (res.ok) {
      var data = await res.json();
      return data;
    }
  } catch (e) {
    console.error('Error loading all recordings:', e);
  }
  return { recordings: [], total: 0, totalSize: 0 };
}

// ============================================
// Format helpers
// ============================================
function formatSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var i = 0;
  var size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return size.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

function formatDuration(seconds) {
  if (!seconds || seconds === 0) return '-';
  var h = Math.floor(seconds / 3600);
  var m = Math.floor((seconds % 3600) / 60);
  var s = Math.floor(seconds % 60);
  if (h > 0) return h + 'h ' + m + 'm';
  return m + 'm ' + s + 's';
}

function formatDate(timestamp) {
  if (!timestamp) return '-';
  try {
    var date = new Date(timestamp * 1000);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return '-';
  }
}

// ============================================
// Render model cards grid
// ============================================
function renderModelGrid(models) {
  var grid = document.getElementById('modelGrid');
  var emptyEl = document.getElementById('emptyRecordings');

  if (!models || models.length === 0) {
    grid.innerHTML = '';
    emptyEl.style.display = 'flex';
    return;
  }

  emptyEl.style.display = 'none';

  grid.innerHTML = models.map(function(model) {
    var thumbUrl = model.thumbnail || '/api/thumbnail/' + model.username;

    var countLabel = model.recordingCount + ' rec';
    if (model.recordingCount === 0) {
      countLabel = 'No recordings';
    }

    return '<div class="rec-model-card" onclick="showModelRecordings(\'' + escapeHtml(model.username) + '\')">' +
      '<div class="rec-model-card-thumb">' +
        '<img src="' + escapeHtml(thumbUrl) + '" alt="' + escapeHtml(model.username) + '" ' +
          'onerror="this.src=\'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22200%22%3E%3Crect fill=%22%231a1f3a%22 width=%22280%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23a0aec0%22 font-family=%22system-ui%22 font-size=%2216%22%3E' + escapeHtml(model.username) + '%3C/text%3E%3C/svg%3E\'" loading="lazy" />' +
        '<span class="rec-model-count">' + countLabel + '</span>' +
      '</div>' +
      '<div class="rec-model-card-info">' +
        '<span class="rec-model-username">' + escapeHtml(model.username) + '</span>' +
        '<span class="rec-model-size">' + formatSize(model.totalSize) + '</span>' +
      '</div>' +
    '</div>';
  }).join('');
}

// ============================================
// Show recordings for a specific model
// ============================================
async function showModelRecordings(username) {
  currentDetailUser = username;

  document.getElementById('modelGrid').style.display = 'none';
  document.getElementById('recordingsDetail').style.display = 'block';
  document.getElementById('detailUsername').textContent = username;

  // Load auto-record status for the detail toggle button + populate edit panel
  loadDetailRecordStatus(username);
  loadModelSettings(username);

  var list = document.getElementById('recordingsList');
  list.innerHTML = '<div class="empty-message"><div class="icon">&#9203;</div><p>Loading...</p></div>';

  try {
    var res = await fetch('/api/recordings/' + encodeURIComponent(username) + '?show_ts=' + showTsFiles);
    if (!res.ok) {
      list.innerHTML = '<div class="empty-message"><div class="icon">&#9888;</div><p>Failed to load recordings.</p></div>';
      return;
    }

    var data = await res.json();
    var recordings = data.recordings || [];

    document.getElementById('detailCount').textContent = recordings.length + ' recording' + (recordings.length !== 1 ? 's' : '');

    if (recordings.length === 0) {
      list.innerHTML = '<div class="empty-message"><div class="icon">&#127910;</div><p>No recordings found.</p></div>';
      return;
    }

    // Sort newest first (already sorted by API, but ensure)
    recordings.sort(function(a, b) {
      return (b.createdAt || b.date || 0) - (a.createdAt || a.date || 0);
    });

    // Cache for timeline + render it
    currentDetailRecordings = recordings;
    renderTimeline(username, recordings);

    // Load playback positions
    var positions = {};
    for (var i = 0; i < recordings.length; i++) {
      var recId = recordings[i].recordingId;
      if (recId) {
        try {
          var posRes = await fetch('/api/playback-position/' + encodeURIComponent(recId));
          if (posRes.ok) {
            var posData = await posRes.json();
            if (posData.position > 0) {
              positions[recId] = posData;
            }
          }
        } catch (e) {}
      }
    }

    list.innerHTML = recordings.map(function(rec) {
      var thumbUrl = rec.thumbnail || '/api/thumbnail/' + username;
      var recId = rec.recordingId || '';
      var pos = positions[recId];
      var resumeBadge = '';
      if (pos && pos.position > 0 && pos.duration > 0) {
        var pct = Math.round((pos.position / pos.duration) * 100);
        resumeBadge = '<div class="resume-badge">Resume at ' + formatDuration(pos.position) + ' (' + pct + '%)</div>';
        resumeBadge += '<div class="progress-bar"><div class="progress-fill" style="width:' + pct + '%"></div></div>';
      }

      // Badge conversion failure + bouton retry
      var failBadge = '';
      var retryBtn = '';
      if (!rec.isConverted && (rec.conversionAttempts || 0) > 0) {
        var errMsg = rec.conversionError ? escapeHtml(rec.conversionError) : 'Conversion failed';
        failBadge = '<div class="conversion-fail-badge" title="' + errMsg + '">&#9888; Conversion failed (' + rec.conversionAttempts + ')</div>';
        retryBtn = '<button class="rec-action-btn" onclick="event.stopPropagation(); retryConversion(\'' + escapeHtml(recId) + '\', this)" title="Retry conversion">&#8635;</button>';
      }

      return '<div class="recording-item" onclick="playRecording(\'' + escapeHtml(username) + '\', \'' + escapeHtml(rec.filename) + '\', \'' + escapeHtml(recId) + '\')">' +
        '<div class="recording-item-thumb">' +
          '<img src="' + escapeHtml(thumbUrl) + '" alt="" loading="lazy" ' +
            'onerror="this.style.display=\'none\'" />' +
          '<span class="recording-duration">' + (rec.duration_str || formatDuration(rec.duration)) + '</span>' +
        '</div>' +
        '<div class="recording-item-info">' +
          '<div class="recording-date">' + formatDate(rec.createdAt) + '</div>' +
          '<div class="recording-meta">' +
            '<span>' + (rec.size_display || formatSize(rec.size)) + '</span>' +
          '</div>' +
          failBadge +
          resumeBadge +
        '</div>' +
        '<div class="recording-item-actions">' +
          retryBtn +
          '<button class="rec-action-btn" onclick="event.stopPropagation(); downloadRecording(\'' + escapeHtml(username) + '\', \'' + escapeHtml(rec.filename) + '\')" title="Download">&#11015;</button>' +
          '<button class="rec-action-btn danger" onclick="event.stopPropagation(); deleteRecording(\'' + escapeHtml(username) + '\', \'' + escapeHtml(rec.filename) + '\', this)" title="Delete">&#128465;</button>' +
        '</div>' +
      '</div>';
    }).join('');

  } catch (e) {
    console.error('Error loading recordings:', e);
    list.innerHTML = '<div class="empty-message"><div class="icon">&#9888;</div><p>Error loading recordings.</p></div>';
  }
}

// ============================================
// Show model grid (back button)
// ============================================
function showModelGrid() {
  document.getElementById('modelGrid').style.display = 'grid';
  document.getElementById('recordingsDetail').style.display = 'none';
  currentDetailUser = '';
  currentDetailModel = null;
  currentDetailRecordings = [];
  if (timelineNowInterval) {
    clearInterval(timelineNowInterval);
    timelineNowInterval = null;
  }
}

// ============================================
// Per-model settings (resolution / retention / auto-record)
// ============================================
function updateEffectiveHint() {
  var hint = document.getElementById('effectiveQualityHint');
  var qSel = document.getElementById('editQuality');
  if (!hint || !qSel) return;
  var eff = effectiveHeight(qSel.value, globalMaxResolution);
  var perModel = qualityToHeight(qSel.value);
  var capped = !!(globalMaxResolution && (perModel === 0 || globalMaxResolution < perModel));
  if (eff === 0) {
    hint.textContent = 'Effective: best available (no cap)';
    hint.classList.remove('capped');
  } else if (capped) {
    hint.textContent = 'Effective: ' + eff + 'p (capped by global max ' + globalMaxResolution + 'p — Settings)';
    hint.classList.add('capped');
  } else {
    hint.textContent = 'Effective: ' + eff + 'p';
    hint.classList.remove('capped');
  }
}

async function loadModelSettings(username) {
  var qSel = document.getElementById('editQuality');
  var rInp = document.getElementById('editRetention');
  var aSel = document.getElementById('editAutoRecord');
  var saveBtn = document.getElementById('saveModelBtn');
  if (!qSel || !rInp || !aSel) return;

  // Reset to defaults while loading
  qSel.value = 'best';
  rInp.value = 30;
  aSel.value = 'true';
  saveBtn.disabled = false;
  saveBtn.textContent = 'Save Changes';

  // Wire change handler once
  if (!qSel.dataset.hintBound) {
    qSel.addEventListener('change', updateEffectiveHint);
    qSel.dataset.hintBound = '1';
  }

  // Refresh the global cap + default so the hint is accurate for the open detail.
  try {
    var sres = await fetch('/api/settings/recording');
    if (sres.ok) {
      var sdata = await sres.json();
      globalMaxResolution = parseInt(sdata.max_resolution, 10) || 0;
      globalDefaultResolution = parseInt(sdata.default_resolution, 10) || 0;
    }
  } catch (e) { /* keep cached value */ }

  try {
    var res = await fetch('/api/models');
    if (!res.ok) return;
    var data = await res.json();
    var found = null;
    for (var i = 0; i < (data.models || []).length; i++) {
      if (data.models[i].username === username) { found = data.models[i]; break; }
    }
    currentDetailModel = found;

    if (found) {
      var q = found.recordQuality || 'best';
      // Ensure the value is selectable even if the DB has something not in the
      // hard-coded list (e.g. legacy values) — append a hidden option.
      var hasOpt = false;
      for (var j = 0; j < qSel.options.length; j++) {
        if (qSel.options[j].value === q) { hasOpt = true; break; }
      }
      if (!hasOpt) {
        var opt = document.createElement('option');
        opt.value = q; opt.textContent = q;
        qSel.appendChild(opt);
      }
      qSel.value = q;
      rInp.value = (found.retentionDays != null) ? found.retentionDays : 30;
      aSel.value = found.autoRecord ? 'true' : 'false';
      saveBtn.textContent = 'Save Changes';
      console.debug('[recordings] loaded settings for', username, found, 'globalMax=', globalMaxResolution);
    } else {
      // Not tracked yet — preselect the global default so the user sees what
      // will be applied on enrolment.
      saveBtn.textContent = 'Add & Save';
      var defQ = globalDefaultResolution > 0 ? (globalDefaultResolution + 'p') : 'best';
      var hasDef = false;
      for (var k = 0; k < qSel.options.length; k++) {
        if (qSel.options[k].value === defQ) { hasDef = true; break; }
      }
      if (!hasDef) {
        var dopt = document.createElement('option');
        dopt.value = defQ; dopt.textContent = defQ;
        qSel.appendChild(dopt);
      }
      qSel.value = defQ;
      console.debug('[recordings] model not tracked yet:', username, 'default=', defQ);
    }
    updateEffectiveHint();
  } catch (e) {
    console.error('Error loading model settings:', e);
  }
}

async function saveModelSettings() {
  var username = currentDetailUser;
  if (!username) return;
  var qSel = document.getElementById('editQuality');
  var rInp = document.getElementById('editRetention');
  var aSel = document.getElementById('editAutoRecord');
  var saveBtn = document.getElementById('saveModelBtn');

  var payload = {
    recordQuality: qSel.value,
    retentionDays: Math.max(1, parseInt(rInp.value, 10) || 30),
    autoRecord: aSel.value === 'true'
  };

  saveBtn.disabled = true;
  var originalLabel = saveBtn.textContent;
  saveBtn.textContent = 'Saving...';

  try {
    // Try update first; if model is not tracked, fall back to create
    var res = await fetch('/api/models/' + encodeURIComponent(username), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.status === 404) {
      // Not tracked — create instead
      res = await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username,
          autoRecord: payload.autoRecord,
          recordQuality: payload.recordQuality,
          retentionDays: payload.retentionDays
        })
      });
    }

    if (res.ok || res.status === 409) {
      showNotification('Settings saved', 'success');
      // Reflect new state in detail header button
      updateDetailRecordButton(payload.autoRecord);
      // Refresh cached settings
      loadModelSettings(username);
    } else {
      var err = await res.json().catch(function(){ return {}; });
      showNotification(err.detail || 'Failed to save settings', 'error');
    }
  } catch (e) {
    console.error('Error saving model settings:', e);
    showNotification('Connection error', 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = originalLabel;
  }
}

// ============================================
// 7-day recording timeline
// ============================================
function renderTimeline(username, recordings) {
  var grid = document.getElementById('timelineGrid');
  var ticksEl = document.getElementById('timelineTicks');
  if (!grid) return;

  // Build the 7 days (oldest -> newest), each starting at local midnight
  var now = new Date();
  var days = [];
  for (var d = 6; d >= 0; d--) {
    var dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() - d, 0, 0, 0, 0);
    var dayEnd = new Date(dayStart.getTime() + 24 * 3600 * 1000);
    days.push({ start: dayStart, end: dayEnd });
  }

  var dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  // Build rows
  var todayKey = days[6].start.getTime();
  grid.innerHTML = days.map(function(day) {
    var isToday = day.start.getTime() === todayKey;
    var label = '<div class="timeline-day-label' + (isToday ? ' today' : '') + '">' +
      '<span class="dow">' + dayNames[day.start.getDay()] + '</span>' +
      '<span>' + day.start.getDate() + '</span>' +
    '</div>';
    var bar = '<div class="timeline-bar" data-day-start="' + day.start.getTime() + '"></div>';
    return label + bar;
  }).join('');

  // Place recording segments inside each day's bar
  var bars = grid.querySelectorAll('.timeline-bar');
  for (var b = 0; b < bars.length; b++) {
    var bar = bars[b];
    var dayStart = parseInt(bar.dataset.dayStart, 10);
    var dayEnd = dayStart + 24 * 3600 * 1000;

    for (var i = 0; i < recordings.length; i++) {
      var rec = recordings[i];
      var startTs = (rec.createdAt || rec.date || 0);
      if (!startTs) continue;
      var startMs = startTs * 1000;
      var durMs = Math.max(0, (rec.duration || 0)) * 1000;
      // If duration unknown, give it a 1-minute marker so it's visible
      if (durMs === 0) durMs = 60 * 1000;
      var endMs = startMs + durMs;

      // Skip if the recording does not overlap with this day
      if (endMs <= dayStart || startMs >= dayEnd) continue;

      var clampedStart = Math.max(startMs, dayStart);
      var clampedEnd = Math.min(endMs, dayEnd);
      var leftPct = ((clampedStart - dayStart) / (24 * 3600 * 1000)) * 100;
      var widthPct = Math.max(0.4, ((clampedEnd - clampedStart) / (24 * 3600 * 1000)) * 100);

      var startStr = new Date(startMs).toLocaleString();
      var endStr = new Date(endMs).toLocaleString();
      var seg = document.createElement('div');
      seg.className = 'timeline-rec';
      seg.style.left = leftPct + '%';
      seg.style.width = widthPct + '%';
      seg.title = (rec.filename || 'recording') + '\n' + startStr + ' -> ' + endStr +
                  '\n' + (rec.duration_str || formatDuration(rec.duration));
      (function(r) {
        seg.addEventListener('click', function(ev) {
          ev.stopPropagation();
          if (r.filename) {
            playRecording(username, r.filename, r.recordingId || '');
          }
        });
      })(rec);
      bar.appendChild(seg);
    }
  }

  // Hour ticks under the grid (every 3h)
  if (ticksEl) {
    var html = '';
    for (var h = 0; h <= 24; h += 3) {
      var pct = (h / 24) * 100;
      var label = (h === 24) ? '24h' : (h + 'h');
      html += '<span class="tick" style="left:' + pct + '%">' + label + '</span>';
    }
    ticksEl.innerHTML = html;
  }

  // Position the blinking "now" line on today's bar and refresh every 30s
  function placeNowLine() {
    var allBars = document.querySelectorAll('#timelineGrid .timeline-bar');
    for (var i = 0; i < allBars.length; i++) {
      var existing = allBars[i].querySelector('.timeline-now');
      if (existing) existing.remove();
    }
    if (allBars.length === 0) return;
    var todayBar = allBars[allBars.length - 1]; // last row is today
    var nowDate = new Date();
    var msSinceMidnight = (nowDate.getHours() * 3600 + nowDate.getMinutes() * 60 + nowDate.getSeconds()) * 1000;
    var pct = (msSinceMidnight / (24 * 3600 * 1000)) * 100;
    var marker = document.createElement('div');
    marker.className = 'timeline-now';
    marker.style.left = pct + '%';
    marker.title = 'Now: ' + nowDate.toLocaleTimeString();
    todayBar.appendChild(marker);
  }
  placeNowLine();
  if (timelineNowInterval) clearInterval(timelineNowInterval);
  timelineNowInterval = setInterval(placeNowLine, 30000);
}

// ============================================
// Play recording with resume support
// ============================================
async function playRecording(username, filename, recordingId) {
  var modal = document.getElementById('playerModal');
  var video = document.getElementById('recordingPlayer');
  var title = document.getElementById('playerTitle');

  // Track current playing recording for auto-delete
  currentPlayingRecordingId = recordingId;
  currentPlayingUsername = username;
  currentPlayingFilename = filename;

  title.textContent = username + ' - ' + filename;
  modal.style.display = 'flex';
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('player-modal-open');

  var url = '/streams/records/' + encodeURIComponent(username) + '/' + encodeURIComponent(filename);

  // Clean up previous player
  if (currentPlayer) {
    currentPlayer.destroy();
    currentPlayer = null;
  }
  video.removeAttribute('src');

  // TS files are raw MPEG-TS, not HLS streams - use direct playback
  video.src = url;
  video.onloadedmetadata = function() {
    loadAndSeek(video, recordingId, username);
  };
  // Fallback: if native playback fails for TS, try with type hint
  video.onerror = function() {
    if (filename.endsWith('.ts') && !video.dataset.retried) {
      video.dataset.retried = 'true';
      var source = document.createElement('source');
      source.src = url;
      source.type = 'video/mp2t';
      video.removeAttribute('src');
      video.appendChild(source);
      video.load();
      video.onloadedmetadata = function() {
        loadAndSeek(video, recordingId, username);
      };
    }
  };

  // Save position periodically (15s is plenty; was 5s)
  var saveInterval = setInterval(function() {
    if (video.currentTime > 0 && !video.paused && recordingId) {
      savePosition(recordingId, username, video.currentTime, video.duration);
    }
  }, 15000);

  // Save on pause
  video.onpause = function() {
    if (recordingId && video.currentTime > 0) {
      savePosition(recordingId, username, video.currentTime, video.duration);
    }
  };

  // Clean up interval when modal closes
  modal.dataset.saveInterval = saveInterval;
}

async function loadAndSeek(video, recordingId, username) {
  if (!recordingId) { video.play().catch(function(){}); return; }
  try {
    var res = await fetch('/api/playback-position/' + encodeURIComponent(recordingId));
    if (res.ok) {
      var data = await res.json();
      if (data.position > 5) {
        video.currentTime = data.position;
      }
    }
  } catch (e) {}
  video.play().catch(function(){});
}

function savePosition(recordingId, username, position, duration) {
  fetch('/api/playback-position/' + encodeURIComponent(recordingId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ position: position, duration: duration, username: username })
  }).catch(function(){});
}

async function closePlayer() {
  var modal = document.getElementById('playerModal');
  var video = document.getElementById('recordingPlayer');
  if (!modal || !video || modal.style.display === 'none') return;

  var recordingId = currentPlayingRecordingId;
  var username = currentPlayingUsername;
  var filename = currentPlayingFilename;
  var position = video.currentTime || 0;
  var duration = Number.isFinite(video.duration) ? video.duration : 0;

  var interval = modal.dataset.saveInterval;
  if (interval) {
    clearInterval(Number(interval));
    delete modal.dataset.saveInterval;
  }

  modal.style.display = 'none';
  modal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('player-modal-open');

  if (
    document.fullscreenElement &&
    (document.fullscreenElement === video || modal.contains(document.fullscreenElement))
  ) {
    document.exitFullscreen().catch(function(){});
  }

  video.onpause = null;
  video.onloadedmetadata = null;
  video.onerror = null;
  video.pause();

  if (currentPlayer) {
    currentPlayer.destroy();
    currentPlayer = null;
  }
  video.removeAttribute('src');
  delete video.dataset.retried;
  while (video.firstChild) { video.removeChild(video.firstChild); }
  video.load();

  currentPlayingRecordingId = '';
  currentPlayingUsername = '';
  currentPlayingFilename = '';

  // Save final position and check auto-delete
  var shouldAutoDelete = false;
  if (recordingId && position > 0 && duration > 0) {
    try {
      var res = await fetch('/api/playback-position/' + encodeURIComponent(recordingId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          position: position,
          duration: duration,
          username: username
        })
      });
      if (res.ok) {
        var data = await res.json();
        shouldAutoDelete = !!data.autoDelete;
      }
    } catch (e) {}
  }

  // Auto-delete if threshold was reached
  if (shouldAutoDelete && username && filename) {
    showNotification('Auto-deleting watched recording...', 'success');
    try {
      var delRes = await fetch('/api/recordings/' + encodeURIComponent(username) + '/' + encodeURIComponent(filename), {
        method: 'DELETE'
      });
      if (delRes.ok) {
        showNotification('Recording auto-deleted', 'success');
      }
    } catch (e) {}
    // Refresh view
    if (currentDetailUser) {
      showModelRecordings(currentDetailUser);
    }
  }
}

// ============================================
// Retry TS -> MP4 conversion manually
// ============================================
async function retryConversion(recordingId, btn) {
  if (!recordingId) return;
  btn.disabled = true;
  btn.innerHTML = '&#8987;';
  try {
    var res = await fetch('/api/recordings/' + encodeURIComponent(recordingId) + '/retry-conversion', {
      method: 'POST'
    });
    var data = await res.json().catch(function () { return {}; });
    if (res.ok) {
      showNotification(data.message || 'Conversion retry scheduled', 'success');
      if (currentDetailUser) {
        setTimeout(function () { showModelRecordings(currentDetailUser); }, 500);
      }
    } else {
      showNotification(data.detail || 'Failed to retry conversion', 'error');
      btn.disabled = false;
      btn.innerHTML = '&#8635;';
    }
  } catch (e) {
    console.error('Error retrying conversion:', e);
    showNotification('Connection error', 'error');
    btn.disabled = false;
    btn.innerHTML = '&#8635;';
  }
}

// ============================================
// Download recording
// ============================================
function downloadRecording(username, filename) {
  var url = '/streams/records/' + encodeURIComponent(username) + '/' + encodeURIComponent(filename);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ============================================
// Delete recording
// ============================================
async function deleteRecording(username, filename, btn) {
  if (!confirm('Delete recording "' + filename + '"? This cannot be undone.')) return;

  btn.disabled = true;
  btn.textContent = '...';

  try {
    var res = await fetch('/api/recordings/' + encodeURIComponent(username) + '/' + encodeURIComponent(filename), {
      method: 'DELETE'
    });

    if (res.ok) {
      showNotification('Recording deleted', 'success');
      // Reload detail view
      if (currentDetailUser) {
        showModelRecordings(currentDetailUser);
      }
    } else {
      showNotification('Failed to delete recording', 'error');
      btn.disabled = false;
      btn.innerHTML = '&#128465;';
    }
  } catch (e) {
    console.error('Error deleting recording:', e);
    showNotification('Connection error', 'error');
    btn.disabled = false;
    btn.innerHTML = '&#128465;';
  }
}

// ============================================
// Toggle auto-record from detail view
// ============================================
async function toggleDetailAutoRecord() {
  if (!currentDetailUser) return;

  var btn = document.getElementById('detailRecordBtn');
  btn.disabled = true;

  try {
    // Check if model is tracked
    var modelsRes = await fetch('/api/models');
    var modelsData = modelsRes.ok ? await modelsRes.json() : { models: [] };
    var found = null;
    for (var i = 0; i < (modelsData.models || []).length; i++) {
      if (modelsData.models[i].username === currentDetailUser) {
        found = modelsData.models[i];
        break;
      }
    }

    if (!found) {
      // Not tracked yet - add model with auto-record on. We deliberately omit
      // recordQuality so the server applies the global default resolution.
      var addRes = await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: currentDetailUser, autoRecord: true, retentionDays: 30 })
      });
      if (addRes.ok || addRes.status === 409) {
        updateDetailRecordButton(true);
        showNotification('Auto-record enabled for ' + currentDetailUser, 'success');
      } else {
        showNotification('Failed to enable auto-record', 'error');
      }
    } else {
      // Toggle existing
      var newValue = !found.autoRecord;
      var res = await fetch('/api/models/' + encodeURIComponent(currentDetailUser) + '/auto-record', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ autoRecord: newValue })
      });
      if (res.ok) {
        updateDetailRecordButton(newValue);
        showNotification(newValue ? 'Auto-record enabled' : 'Auto-record disabled', 'success');
      } else {
        showNotification('Failed to toggle auto-record', 'error');
      }
    }
  } catch (e) {
    console.error('Error toggling auto-record:', e);
    showNotification('Connection error', 'error');
  } finally {
    btn.disabled = false;
  }
}

function updateDetailRecordButton(isActive) {
  var btn = document.getElementById('detailRecordBtn');
  var icon = document.getElementById('detailRecordIcon');
  var text = document.getElementById('detailRecordText');

  if (isActive) {
    btn.classList.add('active');
    icon.innerHTML = '&#9679;';
    text.textContent = 'Recording On';
  } else {
    btn.classList.remove('active');
    icon.innerHTML = '&#9675;';
    text.textContent = 'Auto-Record';
  }
}

async function loadDetailRecordStatus(username) {
  try {
    var res = await fetch('/api/models');
    if (!res.ok) return;
    var data = await res.json();
    var found = null;
    for (var i = 0; i < (data.models || []).length; i++) {
      if (data.models[i].username === username) {
        found = data.models[i];
        break;
      }
    }
    updateDetailRecordButton(found ? found.autoRecord : false);
  } catch (e) {
    console.error('Error loading record status:', e);
  }
}

// ============================================
// Helpers
// ============================================
function escapeHtml(text) {
  if (!text) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

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
// Initialization
// ============================================
window.addEventListener('DOMContentLoaded', function() {
  var style = document.createElement('style');
  style.textContent = '@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }';
  document.head.appendChild(style);

  var modal = document.getElementById('playerModal');
  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) {
        closePlayer();
      }
    });
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
      closePlayer();
    }
  });

  var loadingState = document.getElementById('loadingState');

  // Load show_ts setting first, then load recordings
  loadShowTsSetting().then(function() {
    return Promise.all([loadRecordingsByModel(), loadAllRecordings()]);
  }).then(function(results) {
    var models = results[0];
    var allData = results[1];

    loadingState.style.display = 'none';

    // Update stats
    document.getElementById('totalRecordings').textContent = allData.total || 0;
    document.getElementById('totalSize').textContent = allData.totalSizeFormatted || formatSize(allData.totalSize || 0);
    document.getElementById('totalModels').textContent = models.length;

    // Render model cards
    renderModelGrid(models);
  }).catch(function(e) {
    console.error('Error initializing recordings page:', e);
    loadingState.innerHTML = '<div class="icon">&#9888;</div><p>Failed to load recordings.</p>';
  });
});
