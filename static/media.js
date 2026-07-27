// ============================================
// Media Page - profile-first media catalogue
// ============================================

(function() {
  'use strict';

  var state = {
    items: [],
    profiles: [],
    kind: 'video',
    selectedProfile: '',
    filterProfile: '',
    autoRecordFilter: 'all',
    search: '',
    sort: 'newest',
    loading: false,
    pendingDelete: null,
    pendingProfileDelete: null,
    currentViewerItem: null,
    profileSettings: null,
    viewerSaveInterval: null,
    viewerNextTimer: null,
    viewerNextCountdownTimer: null,
    loadController: null,
    loadRequestId: 0,
    unwatchedOnly: false,
    creatingProfile: false,
    resolvingProfileImage: false
  };

  var PROFILE_SOURCE_OPTIONS = [
    { value: 'chaturbate', label: 'Chaturbate', domains: ['chaturbate.com'] },
    { value: 'cam4', label: 'CAM4', domains: ['cam4.com'] },
    { value: 'stripchat', label: 'Stripchat', domains: ['stripchat.com'] },
    { value: 'bongacams', label: 'BongaCams', domains: ['bongacams.com'] },
    { value: 'myfreecams', label: 'MyFreeCams', domains: ['myfreecams.com', 'mfc.im'] },
    { value: 'livejasmin', label: 'LiveJasmin', domains: ['livejasmin.com'] },
    { value: 'camsoda', label: 'CamSoda', domains: ['camsoda.com'] },
    { value: 'cams', label: 'Cams.com', domains: ['cams.com'] },
    { value: 'xcams', label: 'Xcams', domains: ['xcams.com'] }
  ];

  var searchTimer = null;
  var mediaVolumeUsername = '';
  var mediaPlaybackVolume = null;
  var mediaVolumeSaveTimeout = null;
  var mediaVolumeLoadRequestId = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatDate(timestamp) {
    if (!timestamp) return '-';
    try {
      return new Date(timestamp * 1000).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return '-';
    }
  }

  function formatType(item) {
    if (item.type === 'image') return 'Photo';
    if (item.type === 'audio') return 'Audio';
    return 'Video';
  }

  function numberOrZero(value) {
    var num = Number(value);
    return Number.isFinite(num) && num > 0 ? num : 0;
  }

  function normalizeVolume(value) {
    if (value === null || value === undefined || value === '') return null;
    var volume = Number(value);
    if (!Number.isFinite(volume)) return null;
    return Math.min(1, Math.max(0, volume));
  }

  function getLocalVolume(key) {
    var saved = localStorage.getItem(key);
    return saved === null ? null : normalizeVolume(saved);
  }

  function persistMediaProfileVolume(username, volume) {
    mediaVolumeSaveTimeout = null;
    if (!username) return;

    fetch('/api/models/' + encodeURIComponent(username) + '/volume', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: volume }),
      keepalive: true
    }).catch(function(e) {
      console.warn('Could not save media profile volume:', e);
    });
  }

  function flushMediaProfileVolume() {
    if (mediaVolumeSaveTimeout && mediaPlaybackVolume !== null) {
      clearTimeout(mediaVolumeSaveTimeout);
      persistMediaProfileVolume(mediaVolumeUsername, mediaPlaybackVolume);
    }
  }

  function saveMediaProfileVolume(username, volume) {
    var normalized = normalizeVolume(volume);
    if (!username || normalized === null) return;

    mediaVolumeUsername = username;
    mediaPlaybackVolume = normalized;
    localStorage.setItem('video_volume_' + username, String(normalized));

    if (mediaVolumeSaveTimeout) {
      clearTimeout(mediaVolumeSaveTimeout);
    }
    mediaVolumeSaveTimeout = setTimeout(function() {
      persistMediaProfileVolume(username, normalized);
    }, 250);
  }

  function getSavedMediaProfileVolume(username) {
    if (mediaVolumeUsername === username && mediaPlaybackVolume !== null) {
      return mediaPlaybackVolume;
    }

    var profileVolume = getLocalVolume('video_volume_' + username);
    if (profileVolume !== null) return profileVolume;

    var legacyGlobalVolume = getLocalVolume('video_volume_global');
    if (legacyGlobalVolume !== null) return legacyGlobalVolume;

    return 0.5;
  }

  function loadMediaProfileVolume(video, item) {
    var username = item && item.username ? item.username : '';
    if (!video || !username) return;

    var pendingVolume = (
      mediaVolumeSaveTimeout &&
      mediaVolumeUsername === username &&
      mediaPlaybackVolume !== null
    ) ? mediaPlaybackVolume : null;
    flushMediaProfileVolume();
    if (pendingVolume !== null) {
      mediaVolumeUsername = username;
      mediaPlaybackVolume = pendingVolume;
      video.volume = pendingVolume;
      return;
    }

    mediaVolumeUsername = username;
    mediaPlaybackVolume = null;

    var requestId = ++mediaVolumeLoadRequestId;
    fetch('/api/models/' + encodeURIComponent(username) + '/volume', { cache: 'no-store' })
      .then(function(res) {
        if (!res.ok) return null;
        return res.json().catch(function() { return null; });
      })
      .then(function(data) {
        if (requestId !== mediaVolumeLoadRequestId || state.currentViewerItem !== item || !video.isConnected) {
          return;
        }

        var saved = normalizeVolume(data && data.volume);
        if (saved !== null) {
          mediaPlaybackVolume = saved;
          localStorage.setItem('video_volume_' + username, String(saved));
          video.volume = saved;
          return;
        }

        var profileVolume = getLocalVolume('video_volume_' + username);
        if (profileVolume !== null) {
          video.volume = profileVolume;
          saveMediaProfileVolume(username, profileVolume);
        }
      })
      .catch(function(e) {
        console.warn('Could not load media profile volume:', e);
      });
  }

  function setupMediaProfileVolume(video, item) {
    var username = item && item.username ? item.username : '';
    if (!video || !username) return;

    video.volume = getSavedMediaProfileVolume(username);
    loadMediaProfileVolume(video, item);

    video.addEventListener('volumechange', function() {
      if (!video.muted || video.volume === 0) {
        saveMediaProfileVolume(username, video.volume);
      }
    });
  }

  function mediaPlaybackDuration(item) {
    return numberOrZero(item && item.playbackDuration) || numberOrZero(item && item.duration);
  }

  function mediaPlaybackProgress(item) {
    if (!item || item.type !== 'video') return 0;
    var explicitProgress = Number(item.playbackProgress);
    if (Number.isFinite(explicitProgress) && explicitProgress > 0) {
      return Math.max(0, Math.min(100, Math.round(explicitProgress)));
    }
    var duration = mediaPlaybackDuration(item);
    var position = numberOrZero(item.playbackPosition);
    if (!duration || !position) return 0;
    return Math.max(0, Math.min(100, Math.round((position / duration) * 100)));
  }

  function mediaWatchedThreshold(item) {
    var threshold = Number(item && item.watchedThreshold);
    if (!Number.isFinite(threshold)) return 90;
    return Math.max(0, Math.min(100, threshold));
  }

  function updateMediaPlaybackState(item, position, duration, data) {
    if (!item || item.type !== 'video') return;
    var savedDuration = numberOrZero(duration) || mediaPlaybackDuration(item);
    var savedPosition = numberOrZero(position);
    item.playbackPosition = savedPosition;
    item.playbackDuration = savedDuration;

    if (data && typeof data.progress === 'number') {
      item.playbackProgress = data.progress;
    } else if (savedDuration > 0 && savedPosition > 0) {
      item.playbackProgress = Math.max(0, Math.min(100, Math.round((savedPosition / savedDuration) * 100)));
    } else {
      item.playbackProgress = 0;
    }

    if (data && typeof data.watchedThreshold === 'number') {
      item.watchedThreshold = data.watchedThreshold;
    }
    if (data && data.watchedAt) {
      item.watchedAt = data.watchedAt;
    }
    if (data && typeof data.isWatched === 'boolean') {
      item.isWatched = data.isWatched;
      return;
    }

    var threshold = mediaWatchedThreshold(item);
    if (savedDuration > 0 && savedPosition > 0 && item.playbackProgress >= threshold) {
      item.isWatched = true;
      if (!item.watchedAt) item.watchedAt = Math.floor(Date.now() / 1000);
    }
  }

  function refreshMediaCard(item) {
    if (!item || !item.id) return;
    var cards = document.querySelectorAll('.media-card');
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].dataset.mediaId === item.id) {
        cards[i].outerHTML = renderCard(item);
        return;
      }
    }
  }

  function itemById(id) {
    for (var i = 0; i < state.items.length; i++) {
      if (state.items[i].id === id) return state.items[i];
    }
    return null;
  }

  function profileByUsername(username) {
    for (var i = 0; i < state.profiles.length; i++) {
      if (state.profiles[i].username === username) return state.profiles[i];
    }
    return null;
  }

  function profileLabel(profile) {
    if (!profile) return state.selectedProfile || state.filterProfile || '';
    return profile.displayName || profile.username || '';
  }

  function profileExists(username) {
    return !!(username && profileByUsername(username));
  }

  function visibleProfiles() {
    if (state.autoRecordFilter === 'enabled') {
      return state.profiles.filter(function(profile) { return !!profile.autoRecord; });
    }
    if (state.autoRecordFilter === 'disabled') {
      return state.profiles.filter(function(profile) { return !profile.autoRecord; });
    }
    return state.profiles;
  }

  function mediaCountLabel(count, singular, plural) {
    count = Number(count) || 0;
    return count + ' ' + (count === 1 ? singular : plural);
  }

  function formatProfileMediaCounts(profile) {
    return mediaCountLabel(profile && profile.videos, 'video', 'videos') +
      ' - ' +
      mediaCountLabel(profile && profile.images, 'image', 'images');
  }

  function profileImageUrl(profile) {
    if (!profile) return '';
    return profile.profileImageUrl || profile.profile_image_url || '';
  }

  function firstLetter(value) {
    value = String(value || '?').trim();
    return (value.charAt(0) || '?').toUpperCase();
  }

  function splitLines(value) {
    return String(value || '')
      .split(/\r?\n/)
      .map(function(line) { return line.trim(); })
      .filter(Boolean);
  }

  function joinLines(value) {
    if (Array.isArray(value)) return value.join('\n');
    return String(value || '');
  }

  function normalizeProfileUsername(value) {
    return String(value || '')
      .trim()
      .replace(/[^A-Za-z0-9_.-]+/g, '-')
      .replace(/^[._-]+|[._-]+$/g, '');
  }

  function channelUsernameFromUrl(value) {
    try {
      var url = new URL(String(value || '').trim());
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
      var ignored = { b: true, chat: true, en: true, fr: true, room: true, rooms: true, videochat: true };
      var parts = url.pathname.split('/').map(function(part) {
        return decodeURIComponent(part || '').trim().replace(/^@+/, '');
      }).filter(Boolean);
      for (var i = 0; i < parts.length; i++) {
        if (!ignored[parts[i].toLowerCase()]) return normalizeProfileUsername(parts[i]);
      }
      return parts.length ? normalizeProfileUsername(parts[parts.length - 1]) : '';
    } catch (e) {
      return '';
    }
  }

  function sourceTypeFromUrl(value) {
    try {
      var url = new URL(String(value || '').trim());
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
      var host = (url.hostname || '').toLowerCase().replace(/\.$/, '');
      for (var i = 0; i < PROFILE_SOURCE_OPTIONS.length; i++) {
        var option = PROFILE_SOURCE_OPTIONS[i];
        for (var j = 0; j < option.domains.length; j++) {
          var domain = option.domains[j].toLowerCase();
          if (host === domain || host.slice(-(domain.length + 1)) === '.' + domain) {
            return option.value;
          }
        }
      }
    } catch (e) {
      return '';
    }
    return '';
  }

  function buildQuery() {
    var params = new URLSearchParams();
    params.set('kind', state.unwatchedOnly ? 'video' : state.kind);
    params.set('sort', state.sort);
    params.set('metadata', 'lazy');
    params.set('limit', '1000');
    if (state.unwatchedOnly) params.set('watched', 'unwatched');
    if (state.filterProfile) params.set('username', state.filterProfile);
    if (state.search) params.set('search', state.search);
    return params.toString();
  }

  async function loadMediaLibrary() {
    var requestId = state.loadRequestId + 1;
    state.loadRequestId = requestId;

    if (state.loadController && typeof state.loadController.abort === 'function') {
      state.loadController.abort();
    }
    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    state.loadController = controller;
    state.loading = true;
    renderLoading();

    try {
      var fetchOptions = { cache: 'no-store' };
      if (controller) fetchOptions.signal = controller.signal;
      var res = await fetch('/api/media-library?' + buildQuery(), fetchOptions);
      if (!res.ok) throw new Error('Failed to load media library');
      var data = await res.json();
      if (requestId !== state.loadRequestId) return;
      state.items = data.items || [];
      state.profiles = data.profiles || [];
      if (state.selectedProfile && !profileExists(state.selectedProfile)) state.selectedProfile = '';
      if (state.filterProfile && !profileExists(state.filterProfile)) state.filterProfile = '';
      renderStats(data.libraryStats || data.stats || {});
      renderProfileFilter();
      renderProfileCarousel();
      renderRecentSection(data.total || state.items.length);
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      if (requestId !== state.loadRequestId) return;
      console.error('Error loading media library:', e);
      renderError();
    } finally {
      if (requestId === state.loadRequestId) {
        state.loading = false;
        state.loadController = null;
      }
    }
  }

  function renderLoading() {
    var grid = $('mediaGrid');
    var meta = $('mediaResultMeta');
    var rail = $('mediaProfileRail');
    if (meta) meta.textContent = 'Loading...';
    if (!state.profiles.length && rail) {
      rail.innerHTML = '<div class="empty-message"><div class="icon">&#9203;</div><p>Loading profiles...</p></div>';
    }
    if (grid) {
      grid.innerHTML = '<div class="empty-message"><div class="icon">&#9203;</div><p>Loading media...</p></div>';
    }
  }

  function renderError() {
    var grid = $('mediaGrid');
    var rail = $('mediaProfileRail');
    var meta = $('mediaResultMeta');
    if (meta) meta.textContent = 'Unable to load media';
    if (rail && !state.profiles.length) {
      rail.innerHTML = '<div class="empty-message"><div class="icon">&#9888;</div><p>Profiles unavailable</p></div>';
    }
    if (grid) {
      grid.innerHTML = '<div class="empty-message"><div class="icon">&#9888;</div><p>Media unavailable</p></div>';
    }
  }

  function renderStats(stats) {
    $('mediaTotalCount').textContent = stats.total || 0;
    $('mediaVideoCount').textContent = stats.videos || 0;
    $('mediaImageCount').textContent = stats.images || 0;
    $('mediaTotalSize').textContent = stats.totalSizeFormatted || '0 B';
  }

  function renderProfileCarousel() {
    var rail = $('mediaProfileRail');
    var meta = $('mediaProfileMeta');
    if (!rail) return;
    var scrollLeft = rail.scrollLeft || 0;
    var profiles = visibleProfiles();

    if (meta) {
      var count = profiles.length;
      var countLabel = count === 1 ? '1 profile' : count + ' profiles';
      meta.textContent = state.autoRecordFilter === 'all'
        ? countLabel
        : countLabel + ' of ' + state.profiles.length;
    }

    if (!state.profiles.length) {
      rail.innerHTML = '<div class="empty-message"><div class="icon">&#128444;</div><p>No profiles found</p></div>';
      return;
    }

    if (!profiles.length) {
      rail.innerHTML = '<div class="empty-message"><div class="icon">&#128444;</div><p>No profiles match this filter</p></div>';
      return;
    }

    rail.innerHTML = profiles.map(renderProfileCard).join('');
    if (scrollLeft) {
      requestAnimationFrame(function() {
        rail.scrollLeft = scrollLeft;
      });
    }
  }

  function renderProfileFilter() {
    var select = $('mediaProfileFilter');
    if (!select) return;

    var current = state.filterProfile;
    var options = ['<option value="">All profiles</option>'];
    state.profiles.forEach(function(profile) {
      var label = profileLabel(profile);
      var suffix = profile.displayName ? ' / ' + profile.username : '';
      options.push(
        '<option value="' + escapeHtml(profile.username) + '">' +
          escapeHtml(label + suffix) +
        '</option>'
      );
    });
    select.innerHTML = options.join('');
    if (current && profileExists(current)) {
      select.value = current;
    } else {
      select.value = '';
    }
  }

  function renderProfileCard(profile) {
    var active = state.selectedProfile === profile.username;
    var name = profileLabel(profile);
    var image = '';
    var profileImage = profileImageUrl(profile);
    if (profileImage) {
      image = '<img src="' + escapeHtml(profileImage) + '" alt="' + escapeHtml(name) + '" loading="lazy" onerror="this.style.display=\'none\'; this.parentElement.classList.add(\'missing-thumb\');">';
    }

    var countLabel = formatProfileMediaCounts(profile);

    return '' +
      '<article class="media-profile-card' + (active ? ' active' : '') + '" role="button" tabindex="0" data-profile="' + escapeHtml(profile.username) + '">' +
        '<div class="media-profile-poster">' +
          image +
          '<div class="media-profile-placeholder"><span>' + escapeHtml(firstLetter(name)) + '</span></div>' +
          '<button class="media-profile-menu-btn" type="button" title="Profile settings" aria-label="Profile settings" data-profile-action="settings" data-profile="' + escapeHtml(profile.username) + '">&#8942;</button>' +
          '<span class="media-profile-total">' + escapeHtml(String(profile.total || 0)) + '</span>' +
        '</div>' +
        '<div class="media-profile-info">' +
          '<div class="media-profile-name">' + escapeHtml(name) + '</div>' +
          (name !== profile.username ? '<div class="media-profile-handle">' + escapeHtml(profile.username) + '</div>' : '') +
          '<div class="media-profile-counts">' + escapeHtml(countLabel) + '</div>' +
        '</div>' +
      '</article>';
  }

  function syncProfileSelectionUI() {
    document.querySelectorAll('.media-profile-card').forEach(function(card) {
      card.classList.toggle('active', card.dataset.profile === state.selectedProfile);
    });
  }

  function renderRecentSection(total) {
    renderRecentTitle();
    renderGrid(total);
    syncFilterControls();
  }

  function renderRecentTitle() {
    var title = $('mediaRecentTitle');
    var meta = $('mediaResultMeta');
    if (title) {
      var base = state.unwatchedOnly ? 'Unwatched videos' : state.kind === 'image' ? 'Recent photos' : state.kind === 'all' ? 'Recent media' : 'Recent videos';
      title.textContent = state.filterProfile ? base + ' / ' + profileLabel(profileByUsername(state.filterProfile)) : base;
    }
    if (meta) {
      var label = state.unwatchedOnly
        ? (state.items.length === 1 ? '1 unwatched video' : state.items.length + ' unwatched videos')
        : (state.items.length === 1 ? '1 media item' : state.items.length + ' media items');
      if (state.search) label += ' matching search';
      meta.textContent = label;
    }
  }

  function renderGrid(total) {
    var grid = $('mediaGrid');
    var meta = $('mediaResultMeta');
    if (!grid) return;

    if (meta) {
      var label = state.unwatchedOnly
        ? (total === 1 ? '1 unwatched video' : total + ' unwatched videos')
        : (total === 1 ? '1 media item' : total + ' media items');
      if (state.filterProfile) label += ' in ' + state.filterProfile;
      if (state.search) label += ' matching search';
      meta.textContent = label;
    }

    if (!state.items.length) {
      grid.innerHTML = '<div class="empty-message"><div class="icon">&#128444;</div><p>No media found</p></div>';
      return;
    }

    grid.innerHTML = state.items.map(renderCard).join('');
  }

  function renderCard(item) {
    var thumb = '';
    if (item.thumbnail) {
      thumb = '<img src="' + escapeHtml(item.thumbnail) + '" alt="' + escapeHtml(item.title || item.filename) + '" loading="lazy" onerror="this.style.display=\'none\'; this.parentElement.classList.add(\'missing-thumb\');">';
    }

    var progress = mediaPlaybackProgress(item);
    var marker = item.type === 'image' ? '&#128247;' : item.type === 'audio' ? '&#9835;' : '&#9654;';
    var badges = [
      '<span>' + formatType(item) + '</span>',
      '<span>' + escapeHtml((item.extension || '').toUpperCase()) + '</span>'
    ];
    if (item.isImported) badges.push('<span>Imported</span>');
    if (item.isRecording) badges.push('<span>Recording</span>');
    if (item.isWatched) {
      badges.push('<span class="watched">Watched</span>');
    } else if (item.type === 'video' && progress > 0) {
      badges.push('<span>' + progress + '% watched</span>');
    }
    if (item.type === 'video' && !item.browserPlayable) badges.push('<span>Original</span>');

    return '' +
      '<article class="media-card' + (item.isWatched ? ' watched' : '') + '" role="button" tabindex="0" data-media-id="' + escapeHtml(item.id) + '">' +
        '<div class="media-card-thumb">' +
          thumb +
          '<div class="media-card-placeholder"><span aria-hidden="true">' + marker + '</span></div>' +
          (item.durationStr ? '<span class="media-duration">' + escapeHtml(item.durationStr) + '</span>' : '') +
          (item.type === 'video' && progress > 0 ? '<div class="media-playback-progress" aria-hidden="true"><div style="width:' + progress + '%"></div></div>' : '') +
        '</div>' +
        '<div class="media-card-body">' +
          '<div class="media-card-title" title="' + escapeHtml(item.filename) + '">' + escapeHtml(item.title || item.filename) + '</div>' +
          '<div class="media-card-subtitle">' + escapeHtml(item.username) + '</div>' +
          '<div class="media-card-meta">' +
            '<span>' + escapeHtml(item.sizeFormatted || '') + '</span>' +
            '<span>' + escapeHtml(formatDate(item.createdAt)) + '</span>' +
          '</div>' +
          '<div class="media-badges">' + badges.join('') + '</div>' +
          '<div class="media-card-actions">' +
            '<button class="media-icon-btn danger" type="button" title="Delete" aria-label="Delete" data-media-action="delete" data-media-id="' + escapeHtml(item.id) + '">&#128465;</button>' +
          '</div>' +
        '</div>' +
      '</article>';
  }

  function clearViewerSaveInterval() {
    if (state.viewerSaveInterval) {
      clearInterval(state.viewerSaveInterval);
      state.viewerSaveInterval = null;
    }
  }

  function clearViewerNextPrompt() {
    if (state.viewerNextTimer) {
      clearTimeout(state.viewerNextTimer);
      state.viewerNextTimer = null;
    }
    if (state.viewerNextCountdownTimer) {
      clearInterval(state.viewerNextCountdownTimer);
      state.viewerNextCountdownTimer = null;
    }
    var stage = $('mediaViewerStage');
    var prompt = stage ? stage.querySelector('.media-next-prompt') : null;
    if (prompt) prompt.remove();
  }

  function currentVideoPlaylist() {
    return state.items.filter(function(item) {
      return item && item.type === 'video';
    });
  }

  function nextVideoItem(item) {
    if (!item) return null;
    var videos = currentVideoPlaylist();
    for (var i = 0; i < videos.length; i++) {
      if (videos[i].id === item.id) {
        return videos[i + 1] || null;
      }
    }
    return null;
  }

  function previousVideoItem(item) {
    if (!item) return null;
    var videos = currentVideoPlaylist();
    for (var i = 0; i < videos.length; i++) {
      if (videos[i].id === item.id) {
        return videos[i - 1] || null;
      }
    }
    return null;
  }

  function playNextVideo(nextItem) {
    if (!nextItem) return;
    clearViewerNextPrompt();
    openViewer(nextItem);
  }

  function updateViewerNav(item) {
    var prev = $('mediaViewerPrev');
    var next = $('mediaViewerNext');
    var previousItem = item && item.type === 'video' ? previousVideoItem(item) : null;
    var nextItem = item && item.type === 'video' ? nextVideoItem(item) : null;
    if (prev) {
      prev.disabled = !previousItem;
      prev.dataset.mediaId = previousItem ? previousItem.id : '';
    }
    if (next) {
      next.disabled = !nextItem;
      next.dataset.mediaId = nextItem ? nextItem.id : '';
    }
  }

  function showNextPrompt(item) {
    if (!item || !state.currentViewerItem || state.currentViewerItem.id !== item.id) return;
    var nextItem = nextVideoItem(item);
    if (!nextItem) return;
    var stage = $('mediaViewerStage');
    if (!stage) return;

    clearViewerNextPrompt();
    var countdown = 5;
    var prompt = document.createElement('div');
    prompt.className = 'media-next-prompt';
    prompt.innerHTML = '' +
      '<div>' +
        '<div class="media-next-kicker">Up next</div>' +
        '<h3>' + escapeHtml(nextItem.title || nextItem.filename) + '</h3>' +
        '<p><span data-next-countdown>' + countdown + '</span>s until next video</p>' +
      '</div>' +
      '<div class="media-next-actions">' +
        '<button type="button" data-next-action="stay">Stay</button>' +
        '<button type="button" data-next-action="next">Next</button>' +
      '</div>';
    stage.appendChild(prompt);

    prompt.addEventListener('click', function(ev) {
      var action = ev.target.closest('[data-next-action]');
      if (!action) return;
      if (action.dataset.nextAction === 'next') {
        playNextVideo(nextItem);
      } else {
        clearViewerNextPrompt();
      }
    });

    state.viewerNextCountdownTimer = setInterval(function() {
      countdown -= 1;
      var countNode = prompt.querySelector('[data-next-countdown]');
      if (countNode) countNode.textContent = String(Math.max(0, countdown));
    }, 1000);
    state.viewerNextTimer = setTimeout(function() {
      playNextVideo(nextItem);
    }, countdown * 1000);
  }

  function videoPlaybackDuration(video, item) {
    return numberOrZero(video && video.duration) || mediaPlaybackDuration(item);
  }

  function videoPlaybackPosition(video, duration) {
    if (!video) return 0;
    if (video.ended && duration > 0) return duration;
    return numberOrZero(video.currentTime);
  }

  function saveMediaPlaybackPosition(video, item, options) {
    options = options || {};
    if (!video || !item || item.type !== 'video' || !item.recordingId) {
      return Promise.resolve(null);
    }

    var duration = videoPlaybackDuration(video, item);
    var position = videoPlaybackPosition(video, duration);
    if (position <= 0 && !options.force) return Promise.resolve(null);

    updateMediaPlaybackState(item, position, duration);
    if (options.updateCard !== false) refreshMediaCard(item);

    var now = Date.now();
    if (!options.force && item._mediaPlaybackSavedAt && now - item._mediaPlaybackSavedAt < 10000) {
      return Promise.resolve(null);
    }
    item._mediaPlaybackSavedAt = now;

    return fetch('/api/playback-position/' + encodeURIComponent(item.recordingId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        position: position,
        duration: duration,
        username: item.username || ''
      })
    }).then(function(res) {
      if (!res.ok) return null;
      return res.json().catch(function() { return null; });
    }).then(function(data) {
      if (data) {
        updateMediaPlaybackState(item, position, duration, data);
        if (options.updateCard !== false) refreshMediaCard(item);
      }
      return data;
    }).catch(function() {
      return null;
    });
  }

  async function loadMediaPlaybackPosition(video, item) {
    if (!video || !item || item.type !== 'video' || !item.recordingId) return;
    var duration = videoPlaybackDuration(video, item);
    try {
      var res = await fetch('/api/playback-position/' + encodeURIComponent(item.recordingId), { cache: 'no-store' });
      if (!res.ok) return;
      var data = await res.json();
      updateMediaPlaybackState(item, data.position, data.duration || duration, data);
      refreshMediaCard(item);

      var seekDuration = videoPlaybackDuration(video, item);
      var position = numberOrZero(data.position);
      if (!item.isWatched && position > 5 && seekDuration > 0 && position < seekDuration - 3) {
        video.currentTime = position;
      }
    } catch (e) {}
  }

  function setupMediaVideoPlayback(video, item) {
    if (!video || !item || item.type !== 'video' || !item.recordingId) return;

    clearViewerSaveInterval();
    video.addEventListener('loadedmetadata', function() {
      loadMediaPlaybackPosition(video, item);
    });
    video.addEventListener('timeupdate', function() {
      var previousProgress = mediaPlaybackProgress(item);
      var duration = videoPlaybackDuration(video, item);
      var position = videoPlaybackPosition(video, duration);
      updateMediaPlaybackState(item, position, duration);
      var nextProgress = mediaPlaybackProgress(item);
      if (nextProgress > 0 && nextProgress !== previousProgress) refreshMediaCard(item);
    });
    video.addEventListener('pause', function() {
      saveMediaPlaybackPosition(video, item, { force: true });
    });
    video.addEventListener('play', function() {
      clearViewerNextPrompt();
    });
    video.addEventListener('ended', function() {
      saveMediaPlaybackPosition(video, item, { force: true }).then(function() {
        showNextPrompt(item);
      });
    });
    state.viewerSaveInterval = setInterval(function() {
      if (!video.paused && !video.ended) {
        saveMediaPlaybackPosition(video, item);
      }
    }, 15000);
  }

  function openViewer(item) {
    if (!item) return;

    var viewer = $('mediaViewer');
    var stage = $('mediaViewerStage');
    var title = $('mediaViewerTitle');
    var meta = $('mediaViewerMeta');
    var deleteBtn = $('mediaViewerDelete');
    if (!viewer || !stage) return;

    clearViewerNextPrompt();
    state.currentViewerItem = item;
    title.textContent = item.title || item.filename;
    meta.textContent = item.username + ' / ' + formatType(item) + ' / ' + (item.sizeFormatted || '') + ' / ' + formatDate(item.createdAt);
    if (deleteBtn) deleteBtn.dataset.mediaId = item.id;
    updateViewerNav(item);

    stage.innerHTML = '';
    var mediaNode;
    if (item.type === 'image') {
      mediaNode = document.createElement('img');
      mediaNode.src = item.url;
      mediaNode.alt = item.title || item.filename;
      stage.appendChild(mediaNode);
    } else if (item.type === 'audio') {
      mediaNode = document.createElement('audio');
      mediaNode.src = item.url;
      mediaNode.controls = true;
      mediaNode.autoplay = true;
      stage.appendChild(mediaNode);
    } else {
      mediaNode = document.createElement('video');
      mediaNode.src = item.url;
      mediaNode.controls = true;
      mediaNode.autoplay = true;
      mediaNode.playsInline = true;
      setupMediaProfileVolume(mediaNode, item);
      stage.appendChild(mediaNode);
      setupMediaVideoPlayback(mediaNode, item);
      if (!item.browserPlayable) {
        var note = document.createElement('div');
        note.className = 'media-viewer-note';
        note.textContent = 'Original format. Your browser may not play it directly.';
        stage.appendChild(note);
      }
    }

    viewer.style.display = 'flex';
    viewer.setAttribute('aria-hidden', 'false');
    document.body.classList.add('media-viewer-open');
  }

  function closeViewer() {
    var viewer = $('mediaViewer');
    var stage = $('mediaViewerStage');
    if (!viewer || !stage) return;

    var active = stage.querySelector('video, audio');
    clearViewerSaveInterval();
    clearViewerNextPrompt();
    if (active && active.tagName && active.tagName.toLowerCase() === 'video') {
      saveMediaPlaybackPosition(active, state.currentViewerItem, { force: true });
      flushMediaProfileVolume();
    }
    if (active) active.pause();
    stage.innerHTML = '';
    state.currentViewerItem = null;
    updateViewerNav(null);
    viewer.style.display = 'none';
    viewer.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('media-viewer-open');
  }

  function showToast(message, type) {
    if (typeof window.showNotification === 'function') {
      window.showNotification(message, type || 'success');
      return;
    }
    var existing = document.querySelector('.media-toast');
    if (existing) existing.remove();
    var toast = document.createElement('div');
    toast.className = 'media-toast ' + (type || 'success');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function() {
      toast.remove();
    }, 2600);
  }

  function openDeleteConfirm(item) {
    if (!item) return;
    state.pendingDelete = item;
    var modal = $('mediaDeleteModal');
    var target = $('mediaDeleteTarget');
    var confirm = $('mediaDeleteConfirm');
    if (target) {
      target.textContent = (item.title || item.filename) + ' / ' + item.username;
    }
    if (confirm) {
      confirm.disabled = false;
      confirm.textContent = 'Delete';
    }
    if (modal) {
      modal.style.display = 'flex';
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('media-delete-open');
    }
  }

  function closeDeleteConfirm() {
    var modal = $('mediaDeleteModal');
    if (modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('media-delete-open');
    }
    state.pendingDelete = null;
  }

  async function confirmDeleteMedia() {
    var item = state.pendingDelete;
    if (!item) return;
    var confirm = $('mediaDeleteConfirm');
    if (confirm) {
      confirm.disabled = true;
      confirm.textContent = 'Deleting...';
    }

    try {
      var res = await fetch(item.deleteUrl, { method: 'DELETE' });
      var data = await res.json().catch(function() { return {}; });
      if (!res.ok || data.success === false) {
        throw new Error(data.detail || data.message || 'Delete failed');
      }

      if (state.currentViewerItem && state.currentViewerItem.id === item.id) {
        closeViewer();
      }
      closeDeleteConfirm();
      showToast('Media deleted', 'success');
      await loadMediaLibrary();
    } catch (e) {
      console.error('Error deleting media:', e);
      showToast(e.message || 'Delete failed', 'error');
      if (confirm) {
        confirm.disabled = false;
        confirm.textContent = 'Delete';
      }
    }
  }

  function ensureSelectOption(select, value) {
    if (!select || !value) return;
    for (var i = 0; i < select.options.length; i++) {
      if (select.options[i].value === value) return;
    }
    var option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }

  function setField(id, value) {
    var field = $(id);
    if (!field) return;
    field.value = value == null ? '' : value;
  }

  function fieldValue(id) {
    var field = $(id);
    return field ? field.value.trim() : '';
  }

  function qualityOptionsHtml(value) {
    var values = ['best', '2160p', '1440p', '1080p', '720p', '480p', '360p'];
    if (value && values.indexOf(value) === -1) values.push(value);
    return values.map(function(option) {
      return '<option value="' + escapeHtml(option) + '"' + (option === value ? ' selected' : '') + '>' + escapeHtml(option === 'best' ? 'Best' : option) + '</option>';
    }).join('');
  }

  function sourceOptionsHtml(value) {
    var options = PROFILE_SOURCE_OPTIONS.map(function(option) {
      return { value: option.value, label: option.label };
    });
    var found = options.some(function(option) { return option.value === value; });
    if (value && !found) options.push({ value: value, label: value });
    return options.map(function(option) {
      return '<option value="' + escapeHtml(option.value) + '"' + (option.value === value ? ' selected' : '') + '>' + escapeHtml(option.label) + '</option>';
    }).join('');
  }

  function normalizeProfileSource(source, fallbackUsername) {
    source = source || {};
    var channelUrl = source.channelUrl || source.channel_url || '';
    var sourceType = (source.sourceType || source.source_type || '').toString().trim().toLowerCase();
    var urlSourceType = sourceTypeFromUrl(channelUrl);
    if (urlSourceType && (!sourceType || sourceType === 'chaturbate')) sourceType = urlSourceType;
    if (!sourceType) sourceType = 'chaturbate';
    var retention = parseInt(source.retentionDays == null ? source.retention_days : source.retentionDays, 10);
    if (Number.isNaN(retention)) retention = 30;
    retention = Math.max(0, Math.min(365, retention));
    return {
      sourceType: sourceType,
      channelUsername: source.channelUsername || source.channel_username || source.username || fallbackUsername || '',
      channelUrl: channelUrl,
      recordQuality: source.recordQuality || source.record_quality || 'best',
      retentionDays: retention,
      autoRecord: !!(source.autoRecord != null ? source.autoRecord : source.auto_record)
    };
  }

  function profileSourcesFromProfile(profile) {
    profile = profile || {};
    var sources = Array.isArray(profile.streamSources) ? profile.streamSources : profile.stream_sources;
    if (Array.isArray(sources) && sources.length) {
      return sources.map(function(source) {
        return normalizeProfileSource(source, profile.username || state.selectedProfile || '');
      });
    }
    if (!profile.username && state.creatingProfile) {
      return [normalizeProfileSource({
        sourceType: 'chaturbate',
        channelUsername: '',
        recordQuality: 'best',
        retentionDays: 30,
        autoRecord: false
      }, '')];
    }
    return [normalizeProfileSource({
      sourceType: profile.sourceType || profile.source_type || 'chaturbate',
      channelUsername: profile.username || state.selectedProfile || '',
      channelUrl: Array.isArray(profile.streamUrls) && profile.streamUrls.length ? profile.streamUrls[0] : '',
      recordQuality: profile.recordQuality || 'best',
      retentionDays: profile.retentionDays == null ? 30 : profile.retentionDays,
      autoRecord: !!profile.autoRecord
    }, profile.username || state.selectedProfile || '')];
  }

  function renderProfileSources(sources) {
    var list = $('profileSourcesList');
    if (!list) return;
    sources = Array.isArray(sources) && sources.length ? sources : [normalizeProfileSource({}, '')];
    list.innerHTML = sources.map(function(source, index) {
      source = normalizeProfileSource(source, '');
      return '' +
        '<div class="media-profile-source-row" data-source-index="' + index + '">' +
          '<input data-source-field="channelUsername" type="hidden" value="' + escapeHtml(source.channelUsername) + '">' +
          '<label>Source<select data-source-field="sourceType">' + sourceOptionsHtml(source.sourceType) + '</select></label>' +
          '<label>URL<input data-source-field="channelUrl" type="url" autocomplete="off" value="' + escapeHtml(source.channelUrl) + '" placeholder="https://..."></label>' +
          '<label>Quality<select data-source-field="recordQuality">' + qualityOptionsHtml(source.recordQuality) + '</select></label>' +
          '<label>Retention<input data-source-field="retentionDays" type="number" min="0" max="365" value="' + escapeHtml(source.retentionDays) + '"></label>' +
          '<label class="media-settings-check"><input data-source-field="autoRecord" type="checkbox"' + (source.autoRecord ? ' checked' : '') + '><span>Auto-record</span></label>' +
          '<button class="media-source-remove-btn" data-source-action="remove" type="button" title="Remove source" aria-label="Remove source">&#215;</button>' +
        '</div>';
    }).join('');
    syncLegacyStreamFields(sources);
  }

  function readProfileSources() {
    var rows = Array.prototype.slice.call(document.querySelectorAll('.media-profile-source-row'));
    return rows.map(function(row) {
      function get(field) {
        var el = row.querySelector('[data-source-field="' + field + '"]');
        if (!el) return '';
        if (el.type === 'checkbox') return !!el.checked;
        return el.value.trim();
      }
      var channelUrl = get('channelUrl');
      var selectedSource = (get('sourceType') || '').toLowerCase();
      var urlSource = sourceTypeFromUrl(channelUrl);
      if (urlSource && (!selectedSource || selectedSource === 'chaturbate')) selectedSource = urlSource;
      var retention = parseInt(get('retentionDays'), 10);
      if (Number.isNaN(retention)) retention = 30;
      return {
        sourceType: selectedSource || 'chaturbate',
        channelUsername: channelUsernameFromUrl(channelUrl) || normalizeProfileUsername(get('channelUsername')),
        channelUrl: channelUrl,
        recordQuality: get('recordQuality') || 'best',
        retentionDays: Math.max(0, Math.min(365, retention)),
        autoRecord: !!get('autoRecord')
      };
    }).filter(function(source) {
      return source.channelUsername || source.channelUrl;
    });
  }

  function syncLegacyStreamFields(sources) {
    sources = Array.isArray(sources) ? sources : [];
    var first = normalizeProfileSource(sources[0] || {}, state.selectedProfile || '');
    var quality = $('profileRecordQuality');
    var retention = $('profileRetentionDays');
    var source = $('profileSourceType');
    var auto = $('profileAutoRecord');
    ensureSelectOption(quality, first.recordQuality || 'best');
    if (quality) quality.value = first.recordQuality || 'best';
    if (retention) retention.value = first.retentionDays == null ? 30 : first.retentionDays;
    ensureSelectOption(source, first.sourceType || 'chaturbate');
    if (source) source.value = first.sourceType || 'chaturbate';
    if (auto) auto.checked = !!first.autoRecord;
  }

  function addProfileSource(source) {
    var sources = readProfileSources();
    sources.push(normalizeProfileSource(source || {
      sourceType: 'chaturbate',
      channelUsername: '',
      recordQuality: 'best',
      retentionDays: 30,
      autoRecord: true
    }, state.selectedProfile || ''));
    renderProfileSources(sources);
  }

  function fillProfileSettings(profile) {
    state.profileSettings = profile;
    state.creatingProfile = !profile || !profile.username;
    profile = profile || {};
    var subtitle = $('mediaProfileSettingsSubtitle');
    var title = $('mediaProfileSettingsTitle');
    if (title) title.textContent = state.creatingProfile ? 'New profile' : 'Profile settings';
    if (subtitle) subtitle.textContent = state.creatingProfile ? 'Create a local media profile' : profile.username;

    var usernameField = $('profileUsernameField');
    var usernameInput = $('profileUsername');
    if (usernameField) usernameField.style.display = state.creatingProfile ? 'grid' : 'none';
    if (usernameInput) {
      usernameInput.value = profile.username || '';
      usernameInput.disabled = !state.creatingProfile;
    }

    setField('profileDisplayName', profile.displayName || '');
    setField('profileFirstName', profile.firstName || '');
    setField('profileLastName', profile.lastName || '');
    setField('profileBirthDate', profile.birthDate || profile.birth_date || '');
    setField('profileImageUrl', profile.profileImageUrl || profile.profile_image_url || '');
    setField('profileImageSourceUrl', profile.profileImageSourceUrl || profile.profile_image_source_url || '');
    setField('profileAge', profile.age == null ? '' : profile.age);
    setField('profileAliases', profile.aliases || '');
    setField('profileTags', profile.tags || '');
    setField('profileAddress', profile.address || '');
    setField('profileCity', profile.city || '');
    setField('profileRegion', profile.region || '');
    setField('profilePostalCode', profile.postalCode || '');
    setField('profileCountry', profile.country || '');
    setField('profileSocialUrls', joinLines(profile.socialUrls));
    setField('profileStreamUrls', joinLines(profile.streamUrls));
    setField('profileProfileUrls', joinLines(profile.profileUrls));
    setField('profileNotes', profile.notes || '');
    var quality = $('profileRecordQuality');
    ensureSelectOption(quality, profile.recordQuality || 'best');
    if (quality) quality.value = profile.recordQuality || 'best';
    setField('profileRetentionDays', profile.retentionDays == null ? 30 : profile.retentionDays);
    var source = $('profileSourceType');
    ensureSelectOption(source, profile.sourceType || profile.source_type || 'chaturbate');
    if (source) source.value = profile.sourceType || profile.source_type || 'chaturbate';
    var auto = $('profileAutoRecord');
    if (auto) auto.checked = !!profile.autoRecord;
    renderProfileSources(profileSourcesFromProfile(profile));

    var deleteBtn = $('mediaProfileDeleteBtn');
    if (deleteBtn) deleteBtn.style.display = state.creatingProfile ? 'none' : '';
  }

  function openNewProfileSettings() {
    var modal = $('mediaProfileSettingsModal');
    fillProfileSettings({
      username: '',
      sourceType: 'chaturbate',
      recordQuality: 'best',
      retentionDays: 30,
      autoRecord: false
    });
    if (modal) {
      modal.style.display = 'flex';
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('media-profile-settings-open');
    }
    var usernameInput = $('profileUsername');
    if (usernameInput) usernameInput.focus();
  }

  async function openProfileSettings(profileUsername) {
    if (profileUsername) {
      state.selectedProfile = profileUsername;
      syncProfileSelectionUI();
    }
    if (!state.selectedProfile) return;
    var modal = $('mediaProfileSettingsModal');
    var save = $('mediaProfileSettingsSave');
    if (save) save.disabled = true;

    try {
      var res = await fetch('/api/media-profiles/' + encodeURIComponent(state.selectedProfile), { cache: 'no-store' });
      var data = await res.json().catch(function() { return {}; });
      if (!res.ok) throw new Error(data.detail || 'Profile unavailable');
      fillProfileSettings(data);
      if (modal) {
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('media-profile-settings-open');
      }
    } catch (e) {
      console.error('Error loading profile settings:', e);
      showToast(e.message || 'Profile unavailable', 'error');
    } finally {
      if (save) save.disabled = false;
    }
  }

  function closeProfileSettings() {
    var modal = $('mediaProfileSettingsModal');
    if (modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('media-profile-settings-open');
    }
    state.creatingProfile = false;
  }

  async function resolveProfileImage() {
    if (state.resolvingProfileImage) return;
    var username = state.creatingProfile ? normalizeProfileUsername(fieldValue('profileUsername')) : state.selectedProfile;
    if (!username) {
      showToast('Username is required', 'error');
      return;
    }

    var button = $('profileResolveImageBtn');
    state.resolvingProfileImage = true;
    if (button) {
      button.disabled = true;
      button.textContent = 'Fetching...';
    }

    var query = fieldValue('profileDisplayName') ||
      [fieldValue('profileFirstName'), fieldValue('profileLastName')].filter(Boolean).join(' ') ||
      username;
    var payload = {
      query: query,
      profileImageUrl: fieldValue('profileImageUrl'),
      sourceUrl: fieldValue('profileImageSourceUrl'),
      profileUrls: splitLines(fieldValue('profileProfileUrls'))
    };

    try {
      var res = await fetch('/api/media-profiles/' + encodeURIComponent(username) + '/profile-image/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      var data = await res.json().catch(function() { return {}; });
      if (!res.ok) throw new Error(data.detail || 'Profile image unavailable');
      var profile = data.profile || {};
      setField('profileImageUrl', profile.profileImageUrl || profile.profile_image_url || '');
      setField('profileImageSourceUrl', profile.profileImageSourceUrl || profile.profile_image_source_url || payload.sourceUrl || '');
      state.profileSettings = profile;
      if (state.creatingProfile) state.selectedProfile = username;
      await loadMediaLibrary();
      showToast('Profile image updated');
    } catch (e) {
      console.error('Error resolving profile image:', e);
      showToast(e.message || 'Profile image unavailable', 'error');
    } finally {
      state.resolvingProfileImage = false;
      if (button) {
        button.disabled = false;
        button.textContent = 'Fetch Babepedia image';
      }
    }
  }

  async function saveProfileSettings(ev) {
    if (ev) ev.preventDefault();
    var username = state.creatingProfile ? normalizeProfileUsername(fieldValue('profileUsername')) : state.selectedProfile;
    if (!username) {
      showToast('Username is required', 'error');
      return;
    }
    var save = $('mediaProfileSettingsSave');
    if (save) {
      save.disabled = true;
      save.textContent = 'Saving...';
    }

    var ageValue = fieldValue('profileAge');
    var age = ageValue ? parseInt(ageValue, 10) : null;
    if (Number.isNaN(age)) age = null;

    var profileSources = readProfileSources();
    syncLegacyStreamFields(profileSources);
    var retention = parseInt(fieldValue('profileRetentionDays'), 10);
    if (Number.isNaN(retention)) retention = 30;
    retention = Math.max(0, Math.min(365, retention));
    var auto = $('profileAutoRecord');
    var source = $('profileSourceType');
    var payload = {
      displayName: fieldValue('profileDisplayName'),
      firstName: fieldValue('profileFirstName'),
      lastName: fieldValue('profileLastName'),
      birthDate: fieldValue('profileBirthDate'),
      profileImageUrl: fieldValue('profileImageUrl'),
      profileImageSourceUrl: fieldValue('profileImageSourceUrl'),
      age: age,
      aliases: fieldValue('profileAliases'),
      tags: fieldValue('profileTags'),
      address: fieldValue('profileAddress'),
      city: fieldValue('profileCity'),
      region: fieldValue('profileRegion'),
      postalCode: fieldValue('profilePostalCode'),
      country: fieldValue('profileCountry'),
      socialUrls: splitLines(fieldValue('profileSocialUrls')),
      streamUrls: splitLines(fieldValue('profileStreamUrls')),
      profileUrls: splitLines(fieldValue('profileProfileUrls')),
      notes: fieldValue('profileNotes'),
      recordQuality: fieldValue('profileRecordQuality') || 'best',
      retentionDays: retention,
      sourceType: source ? source.value : 'chaturbate',
      autoRecord: auto ? auto.checked : false,
      streamSources: profileSources
    };

    try {
      var res = await fetch('/api/media-profiles/' + encodeURIComponent(username), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      var data = await res.json().catch(function() { return {}; });
      if (!res.ok || data.success === false) {
        throw new Error(data.detail || data.message || 'Save failed');
      }
      showToast('Settings saved', 'success');
      closeProfileSettings();
      state.selectedProfile = username;
      await loadMediaLibrary();
    } catch (e) {
      console.error('Error saving profile settings:', e);
      showToast(e.message || 'Save failed', 'error');
    } finally {
      if (save) {
        save.disabled = false;
        save.textContent = 'Save';
      }
    }
  }

  function openProfileDeleteConfirm() {
    if (!state.selectedProfile) return;
    var profile = state.profileSettings || profileByUsername(state.selectedProfile) || { username: state.selectedProfile };
    state.pendingProfileDelete = profile;
    var target = $('mediaProfileDeleteTarget');
    var confirm = $('mediaProfileDeleteConfirm');
    var modal = $('mediaProfileDeleteModal');
    if (target) target.textContent = profileLabel(profile) + ' / ' + profile.username;
    if (confirm) {
      confirm.disabled = false;
      confirm.textContent = 'Delete profile';
    }
    if (modal) {
      modal.style.display = 'flex';
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('media-delete-open');
    }
  }

  function closeProfileDeleteConfirm() {
    var modal = $('mediaProfileDeleteModal');
    if (modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('media-delete-open');
    }
    state.pendingProfileDelete = null;
  }

  async function confirmDeleteProfile() {
    var profile = state.pendingProfileDelete;
    if (!profile || !profile.username) return;
    var confirm = $('mediaProfileDeleteConfirm');
    if (confirm) {
      confirm.disabled = true;
      confirm.textContent = 'Deleting...';
    }

    try {
      var res = await fetch('/api/media-profiles/' + encodeURIComponent(profile.username), { method: 'DELETE' });
      var data = await res.json().catch(function() { return {}; });
      if (!res.ok || data.success === false) {
        throw new Error(data.detail || data.message || 'Delete failed');
      }
      closeProfileDeleteConfirm();
      closeProfileSettings();
      if (state.filterProfile === profile.username) state.filterProfile = '';
      state.selectedProfile = '';
      state.profileSettings = null;
      showToast('Profile deleted', 'success');
      await loadMediaLibrary();
    } catch (e) {
      console.error('Error deleting profile:', e);
      showToast(e.message || 'Delete failed', 'error');
      if (confirm) {
        confirm.disabled = false;
        confirm.textContent = 'Delete profile';
      }
    }
  }

  function syncFilterControls() {
    var buttons = document.querySelectorAll('.media-kind-btn');
    buttons.forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.kind === state.kind);
    });

    var sort = $('mediaSortSelect');
    if (sort) sort.value = state.sort;

    var profileFilter = $('mediaProfileFilter');
    if (profileFilter) profileFilter.value = state.filterProfile || '';

    var autoRecordFilter = $('mediaAutoRecordFilter');
    if (autoRecordFilter) autoRecordFilter.value = state.autoRecordFilter;

    var unwatchedToggle = $('mediaUnwatchedOnlyToggle');
    if (unwatchedToggle) {
      unwatchedToggle.checked = !!state.unwatchedOnly;
      var unwatchedLabel = unwatchedToggle.closest('.media-unwatched-toggle');
      if (unwatchedLabel) unwatchedLabel.classList.toggle('active', !!state.unwatchedOnly);
    }
  }

  function setKind(kind) {
    state.kind = kind || 'all';
    if (state.kind !== 'video') state.unwatchedOnly = false;
    loadMediaLibrary();
  }

  function selectProfile(profile, shouldScroll) {
    state.selectedProfile = profile || '';
    state.filterProfile = profile || '';
    syncProfileSelectionUI();
    if (shouldScroll) {
      var results = document.querySelector('.media-recent-section');
      if (results && results.scrollIntoView) {
        results.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
    }
    loadMediaLibrary();
  }

  function setFilterProfile(profile) {
    state.filterProfile = profile || '';
    state.selectedProfile = profile || '';
    loadMediaLibrary();
  }

  function scrollProfiles(direction) {
    var rail = $('mediaProfileRail');
    if (!rail) return;
    var amount = Math.max(280, Math.floor(rail.clientWidth * 0.8));
    rail.scrollBy({ left: direction * amount, behavior: 'smooth' });
  }

  function bindEvents() {
    var search = $('mediaSearchInput');
    if (search) {
      search.addEventListener('input', function() {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function() {
          state.search = search.value.trim();
          loadMediaLibrary();
        }, 180);
      });
    }

    var sortSelect = $('mediaSortSelect');
    if (sortSelect) {
      sortSelect.addEventListener('change', function() {
        state.sort = sortSelect.value;
        loadMediaLibrary();
      });
    }

    var profileFilter = $('mediaProfileFilter');
    if (profileFilter) {
      profileFilter.addEventListener('change', function() {
        setFilterProfile(profileFilter.value);
      });
    }

    var autoRecordFilter = $('mediaAutoRecordFilter');
    if (autoRecordFilter) {
      autoRecordFilter.addEventListener('change', function() {
        state.autoRecordFilter = autoRecordFilter.value || 'all';
        renderProfileCarousel();
      });
    }

    var unwatchedToggle = $('mediaUnwatchedOnlyToggle');
    if (unwatchedToggle) {
      unwatchedToggle.addEventListener('change', function() {
        state.unwatchedOnly = !!unwatchedToggle.checked;
        if (state.unwatchedOnly) state.kind = 'video';
        loadMediaLibrary();
      });
    }

    document.querySelectorAll('.media-kind-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        setKind(btn.dataset.kind || 'all');
      });
    });

    var prev = $('mediaProfilePrev');
    if (prev) prev.addEventListener('click', function() { scrollProfiles(-1); });

    var next = $('mediaProfileNext');
    if (next) next.addEventListener('click', function() { scrollProfiles(1); });

    var newProfile = $('mediaNewProfileBtn');
    if (newProfile) newProfile.addEventListener('click', openNewProfileSettings);

    var rail = $('mediaProfileRail');
    if (rail) {
      rail.addEventListener('click', function(ev) {
        var settings = ev.target.closest('[data-profile-action="settings"]');
        if (settings) {
          ev.preventDefault();
          ev.stopPropagation();
          openProfileSettings(settings.dataset.profile || '');
          return;
        }
        var card = ev.target.closest('.media-profile-card');
        if (!card) return;
        selectProfile(card.dataset.profile || '', true);
      });
      rail.addEventListener('keydown', function(ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var card = ev.target.closest('.media-profile-card');
        if (!card) return;
        ev.preventDefault();
        selectProfile(card.dataset.profile || '', true);
      });
    }

    var grid = $('mediaGrid');
    if (grid) {
      grid.addEventListener('click', function(ev) {
        var action = ev.target.closest('[data-media-action]');
        if (action) {
          if (action.dataset.mediaAction === 'delete') {
            ev.preventDefault();
            ev.stopPropagation();
            openDeleteConfirm(itemById(action.dataset.mediaId));
          }
          return;
        }
        var card = ev.target.closest('.media-card');
        if (card) openViewer(itemById(card.dataset.mediaId));
      });
      grid.addEventListener('keydown', function(ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var card = ev.target.closest('.media-card');
        if (!card) return;
        ev.preventDefault();
        openViewer(itemById(card.dataset.mediaId));
      });
    }

    var close = $('mediaViewerClose');
    if (close) close.addEventListener('click', closeViewer);

    var viewerDelete = $('mediaViewerDelete');
    if (viewerDelete) {
      viewerDelete.addEventListener('click', function() {
        openDeleteConfirm(state.currentViewerItem);
      });
    }

    var viewerPrev = $('mediaViewerPrev');
    if (viewerPrev) {
      viewerPrev.addEventListener('click', function() {
        var previousItem = previousVideoItem(state.currentViewerItem);
        if (previousItem) openViewer(previousItem);
      });
    }

    var viewerNext = $('mediaViewerNext');
    if (viewerNext) {
      viewerNext.addEventListener('click', function() {
        var nextItem = nextVideoItem(state.currentViewerItem);
        if (nextItem) openViewer(nextItem);
      });
    }

    var deleteCancel = $('mediaDeleteCancel');
    if (deleteCancel) deleteCancel.addEventListener('click', closeDeleteConfirm);

    var deleteConfirm = $('mediaDeleteConfirm');
    if (deleteConfirm) deleteConfirm.addEventListener('click', confirmDeleteMedia);

    var profileSettingsForm = $('mediaProfileSettingsForm');
    if (profileSettingsForm) profileSettingsForm.addEventListener('submit', saveProfileSettings);

    var profileResolveImage = $('profileResolveImageBtn');
    if (profileResolveImage) profileResolveImage.addEventListener('click', resolveProfileImage);

    var profileSettingsClose = $('mediaProfileSettingsClose');
    if (profileSettingsClose) profileSettingsClose.addEventListener('click', closeProfileSettings);

    var profileSettingsCancel = $('mediaProfileSettingsCancel');
    if (profileSettingsCancel) profileSettingsCancel.addEventListener('click', closeProfileSettings);

    var profileDelete = $('mediaProfileDeleteBtn');
    if (profileDelete) profileDelete.addEventListener('click', openProfileDeleteConfirm);

    var profileAddSource = $('profileAddSourceBtn');
    if (profileAddSource) profileAddSource.addEventListener('click', function() {
      addProfileSource();
    });

    var profileSourcesList = $('profileSourcesList');
    if (profileSourcesList) {
      profileSourcesList.addEventListener('click', function(ev) {
        var remove = ev.target.closest('[data-source-action="remove"]');
        if (!remove) return;
        var rows = Array.prototype.slice.call(document.querySelectorAll('.media-profile-source-row'));
        if (rows.length <= 1) {
          rows[0].querySelectorAll('input').forEach(function(input) {
            if (input.type === 'checkbox') input.checked = false;
            else input.value = '';
          });
          return;
        }
        var row = remove.closest('.media-profile-source-row');
        if (row) row.remove();
        syncLegacyStreamFields(readProfileSources());
      });
      profileSourcesList.addEventListener('change', function() {
        syncLegacyStreamFields(readProfileSources());
      });
      profileSourcesList.addEventListener('input', function() {
        syncLegacyStreamFields(readProfileSources());
      });
    }

    var profileDeleteCancel = $('mediaProfileDeleteCancel');
    if (profileDeleteCancel) profileDeleteCancel.addEventListener('click', closeProfileDeleteConfirm);

    var profileDeleteConfirm = $('mediaProfileDeleteConfirm');
    if (profileDeleteConfirm) profileDeleteConfirm.addEventListener('click', confirmDeleteProfile);

    var viewer = $('mediaViewer');
    if (viewer) {
      viewer.addEventListener('click', function(ev) {
        if (ev.target === viewer) closeViewer();
      });
    }

    var deleteModal = $('mediaDeleteModal');
    if (deleteModal) {
      deleteModal.addEventListener('click', function(ev) {
        if (ev.target === deleteModal) closeDeleteConfirm();
      });
    }

    var profileSettingsModal = $('mediaProfileSettingsModal');
    if (profileSettingsModal) {
      profileSettingsModal.addEventListener('click', function(ev) {
        if (ev.target === profileSettingsModal) closeProfileSettings();
      });
    }

    var profileDeleteModal = $('mediaProfileDeleteModal');
    if (profileDeleteModal) {
      profileDeleteModal.addEventListener('click', function(ev) {
        if (ev.target === profileDeleteModal) closeProfileDeleteConfirm();
      });
    }

    document.addEventListener('keydown', function(ev) {
      if (ev.key === 'Escape') {
        if (state.pendingProfileDelete) {
          closeProfileDeleteConfirm();
        } else if (state.pendingDelete) {
          closeDeleteConfirm();
        } else if ($('mediaProfileSettingsModal') && $('mediaProfileSettingsModal').style.display !== 'none') {
          closeProfileSettings();
        } else {
          closeViewer();
        }
      }
    });

    window.addEventListener('beforeunload', flushMediaProfileVolume);
  }

  document.addEventListener('DOMContentLoaded', function() {
    bindEvents();
    syncFilterControls();
    loadMediaLibrary();
  });
})();
