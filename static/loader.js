// Component loader for shared header and footer
(function() {
  // Load header
  fetch('/static/header.html')
    .then(res => res.text())
    .then(html => {
      const placeholder = document.getElementById('header-placeholder');
      if (placeholder) {
        placeholder.outerHTML = html;
        
        // Load version
        (async function loadVersion() {
          try {
            const res = await fetch('/api/version');
            const data = await res.json();
            const versionEl = document.getElementById('appVersion');
            if (versionEl) versionEl.textContent = `v${data.version}`;
          } catch (e) {
            console.error('Error loading version:', e);
          }
        })();
        
        // Check Git status
        (async function checkGitStatus() {
          try {
            const res = await fetch('/api/git/status');
            if (res.ok) {
              const data = await res.json();
              const btn = document.getElementById('gitStatusBtn');
              if (btn && data.isGitRepo) {
                btn.style.display = 'inline-block';
                
                if (data.updateAvailable) {
                  document.getElementById('gitStatusIcon').textContent = '🆕';
                  document.getElementById('gitStatusText').textContent = 'Update!';
                  btn.style.borderColor = 'var(--accent)';
                  btn.style.color = 'var(--accent)';
                }
              }
            }
          } catch (e) {
            console.error('Error checking git status:', e);
          }
        })();
      }
    })
    .catch(err => console.error('Error loading header:', err));

  // Load footer
  fetch('/static/footer.html')
    .then(res => res.text())
    .then(html => {
      const placeholder = document.getElementById('footer-placeholder');
      if (placeholder) {
        placeholder.outerHTML = html;
      }
    })
    .catch(err => console.error('Error loading footer:', err));
})();
