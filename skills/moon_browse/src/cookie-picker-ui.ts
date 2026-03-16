/**
 * Cookie picker UI — simplified version for Moon-Stack
 * HTML page for selecting and importing cookies from browsers
 */

export function getCookiePickerHTML(port: number): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cookie Import Picker</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }
    h1 { color: #333; }
    .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }
    button { padding: 8px 16px; margin: 5px; cursor: pointer; }
    .domain-list { max-height: 300px; overflow-y: auto; }
    .domain-item { padding: 8px; margin: 4px 0; background: #f5f5f5; border-radius: 4px; }
    .domain-item.selected { background: #007bff; color: white; }
    #status { margin-top: 20px; padding: 10px; border-radius: 4px; }
    .success { background: #d4edda; color: #155724; }
    .error { background: #f8d7da; color: #721c24; }
  </style>
</head>
<body>
  <h1>🍪 Cookie Import Picker</h1>
  
  <div class="section">
    <h2>1. Select Source Browser</h2>
    <div id="browsers">Loading browsers...</div>
  </div>
  
  <div class="section">
    <h2>2. Select Domains to Import</h2>
    <button id="loadDomains">Load Domains</button>
    <button id="selectAll">Select All</button>
    <button id="clearSelection">Clear Selection</button>
    <div id="domainList" class="domain-list" style="margin-top: 10px;"></div>
  </div>
  
  <div class="section">
    <h2>3. Import</h2>
    <button id="importBtn">Import Selected Cookies</button>
    <button id="closeBtn">Close</button>
  </div>
  
  <div id="status"></div>

  <script>
    const API_BASE = 'http://127.0.0.1:${port}';
    let selectedBrowser = null;
    let selectedDomains = new Set();

    async function loadBrowsers() {
      const res = await fetch(\`\${API_BASE}/cookie-picker/browsers\`);
      const data = await res.json();
      const container = document.getElementById('browsers');
      container.innerHTML = data.browsers.map(b => 
        \`<button onclick="selectBrowser('\${b.name}')">\${b.name}</button>\`
      ).join(' ') || 'No browsers detected';
    }

    function selectBrowser(name) {
      selectedBrowser = name;
      document.getElementById('status').textContent = 'Selected: ' + name;
      document.getElementById('status').className = 'success';
    }

    async function loadDomains() {
      if (!selectedBrowser) {
        showStatus('Please select a browser first', 'error');
        return;
      }
      const res = await fetch(\`\${API_BASE}/cookie-picker/domains?browser=\${encodeURIComponent(selectedBrowser)}\`);
      const data = await res.json();
      const container = document.getElementById('domainList');
      container.innerHTML = data.domains.map(d => 
        \`<div class="domain-item" data-domain="\${d.domain}" onclick="toggleDomain(this)">
          \${d.domain} (\${d.count} cookies)
        </div>\`
      ).join('');
      showStatus('Loaded ' + data.domains.length + ' domains', 'success');
    }

    function toggleDomain(el) {
      const domain = el.dataset.domain;
      if (selectedDomains.has(domain)) {
        selectedDomains.delete(domain);
        el.classList.remove('selected');
      } else {
        selectedDomains.add(domain);
        el.classList.add('selected');
      }
    }

    function selectAll() {
      document.querySelectorAll('.domain-item').forEach(el => {
        selectedDomains.add(el.dataset.domain);
        el.classList.add('selected');
      });
    }

    function clearSelection() {
      selectedDomains.clear();
      document.querySelectorAll('.domain-item').forEach(el => {
        el.classList.remove('selected');
      });
    }

    async function importCookies() {
      if (selectedDomains.size === 0) {
        showStatus('No domains selected', 'error');
        return;
      }
      const res = await fetch(\`\${API_BASE}/cookie-picker/import\`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ browser: selectedBrowser, domains: [...selectedDomains] })
      });
      const data = await res.json();
      if (data.error) {
        showStatus('Error: ' + data.error, 'error');
      } else {
        showStatus('Imported ' + data.imported + ' cookies from ' + Object.keys(data.domainCounts).length + ' domains', 'success');
      }
    }

    function showStatus(msg, type) {
      const el = document.getElementById('status');
      el.textContent = msg;
      el.className = type;
    }

    document.getElementById('loadDomains').onclick = loadDomains;
    document.getElementById('selectAll').onclick = selectAll;
    document.getElementById('clearSelection').onclick = clearSelection;
    document.getElementById('importBtn').onclick = importCookies;
    document.getElementById('closeBtn').onclick = () => window.close();

    loadBrowsers();
  </script>
</body>
</html>`;
}
