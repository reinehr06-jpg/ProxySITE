// AUTH CHECK
if (!localStorage.getItem('isAuthenticated') && !window.location.href.includes('login.html')) {
    window.location.href = 'login.html';
}

let activeTab = 'dashboard';
let allClients = [];
let allProxies = [];
let pendingFilter = null;
let currentMap = null;

// TAB NAVIGATION
document.querySelectorAll('.tab-link').forEach(link => {
    link.addEventListener('click', (e) => {
        const tab = link.getAttribute('data-tab');
        switchTab(tab);
    });
});

function switchTab(tabId, filter = null) {
    activeTab = tabId;
    pendingFilter = filter; 

    document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
    const link = document.querySelector(`.tab-link[data-tab="${tabId}"]`);
    if (link) link.classList.add('active');
    
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const target = document.getElementById(tabId);
    if (target) target.classList.add('active');
    
    if (tabId === 'settings') closeSettingsDetail();
    refreshData();
}

async function refreshData() {
    await fetchStats();
    if (activeTab === 'clients') await fetchClients();
    if (activeTab === 'addresses') await fetchAddresses();
    if (activeTab === 'monitoramento') await fetchMonitorData();
}

// GEOLOCATION HELPERS
function getDistance(lat1, lon1, lat2, lon2) {
    if (!lat1 || !lon1 || !lat2 || !lon2) return Infinity;
    const R = 6371; // km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

// DASHBOARD KPI & LISTS
async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        document.getElementById('kpi-active').innerText = data.active_clients_count || 0;
        document.getElementById('kpi-off').innerText = data.fallen_clients ? data.fallen_clients.length : 0;
        document.getElementById('kpi-resp').innerText = `${data.avg_system_response || 0}ms`;
        document.getElementById('kpi-uazapi').innerHTML = data.uazapi_connected ? 
            '<i class="fas fa-check-circle" style="color:var(--success)"></i> ONLINE' : 
            '<i class="fas fa-times-circle" style="color:var(--error)"></i> OFF';

        renderSimpleStateList(data.proxies_by_state);
        renderStateGrid(data.proxies_by_state);
        updateFallenClients(data.fallen_clients);
        updateLogs(data.recent_logs);
    } catch (e) { console.error(e); }
}

function renderSimpleStateList(stateData) {
    const container = document.getElementById('simple-state-list');
    if (!container) return;
    container.innerHTML = '';
    if (!stateData) return;
    Object.entries(stateData).forEach(([state, count]) => {
        const item = document.createElement('div');
        item.className = 'state-list-item';
        item.innerHTML = `<span>${state}</span> <strong>${count}</strong>`;
        item.onclick = () => switchTab('estados');
        container.appendChild(item);
    });
}

function renderStateGrid(stateData) {
    const container = document.getElementById('state-grid-container');
    if (!container) return;
    container.innerHTML = '';
    if (!stateData) return;

    Object.entries(stateData).forEach(([state, count]) => {
        const card = document.createElement('div');
        card.className = 'address-card'; // Use identical class for parity
        card.innerHTML = `
            <div class="card-header">
                <h3><i class="fas fa-map-marker-alt" style="color:var(--apple-purple)"></i> ${state}</h3>
                <span class="status-pill active">${count} IPs</span>
            </div>
            <div class="card-body">
                <p style="color:var(--text-dim); font-size:0.85rem; margin-bottom:15px;">Rede Proxy em ${state}: Monitoramento de latência e disponibilidade regional.</p>
            </div>
            <button class="btn-dispatch" onclick="openAppleMap('${state}')">VER NO MAPA <i class="fas fa-chevron-right"></i></button>
        `;
        container.appendChild(card);
    });
}

function updateFallenClients(fallen) {
    const tbody = document.getElementById('fallen-clients-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (!fallen || fallen.length === 0) {
        tbody.innerHTML = '<tr><td style="text-align:center; padding:20px; color:var(--text-dim)">Nenhuma queda detectada.</td></tr>';
        return;
    }

    // Limit to 4 and add "Ver Todos"
    const displayList = fallen.slice(0, 4);
    displayList.forEach(c => {
        tbody.innerHTML += `
            <tr style="animation: fadeIn 0.3s ease forwards;">
                <td><strong>${c.church_name}</strong><br><small>${c.phone}</small></td>
                <td><span class="status-pill error">OFFLINE</span></td>
                <td><button class="btn-dispatch" onclick="dispatchManual('${c.id}')">RECUPERAR</button></td>
            </tr>
        `;
    });

    if (fallen.length > 4) {
        tbody.innerHTML += `
            <tr>
                <td colspan="3" style="text-align:center; padding:15px;">
                    <button class="btn-text-link" style="margin:0 auto;" onclick="switchTab('clients', 'offline')">
                        <i class="fas fa-plus-circle"></i> VER TODAS AS ${fallen.length} QUEDAS
                    </button>
                </td>
            </tr>
        `;
    }
}

// CLIENTS & FILTERING
async function fetchClients() {
    const r = await fetch('/api/clients');
    allClients = await r.json();
    let displayClients = allClients;
    if (pendingFilter === 'offline') displayClients = allClients.filter(c => c.status !== 'active');
    if (pendingFilter === 'active') displayClients = allClients.filter(c => c.status === 'active');
    renderClientsTable(displayClients);
    pendingFilter = null;
}

function renderClientsTable(clients) {
    const tbody = document.getElementById('all-clients-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    clients.forEach(c => {
        tbody.innerHTML += `
            <tr>
                <td><strong>${c.church_name}</strong><br><small>${c.cpf_cnpj}</small></td>
                <td>${c.phone}</td>
                <td>${c.default_ip}</td>
                <td><span class="badge">${c.basileia_id}</span></td>
                <td><span class="status-pill ${c.status}">${c.status}</span></td>
                <td><button class="btn-dispatch" onclick="alert('Configuração Basileia ID: '+c.basileia_id)">INFO</button></td>
            </tr>
        `;
    });
}

// SMART REALLOCATION & GEO
async function fetchAddresses() {
    const r = await fetch('/api/addresses');
    allProxies = await r.json();
    // Cache full proxy objects including coordinates
    const rFull = await fetch('/api/stats');
    const stats = await rFull.json();
    // In a real app we'd have a separate /api/proxies endpoint but here we have data in stats/all_proxies
    // For the demo, let's assume allProxies has basic info and we bridge coordinates from a hidden call if needed
    renderAddresses(allProxies);
}

function renderAddresses(proxies) {
    const container = document.getElementById('address-grid');
    if (!container) return;
    container.innerHTML = '';
    proxies.forEach(p => {
        const card = document.createElement('div');
        card.className = 'address-card';
        card.innerHTML = `
            <div class="card-header">
                <h3><i class="fas fa-mobile-alt"></i> ${p.device}</h3>
                <span class="status-pill active">${p.status}</span>
            </div>
            <div class="card-body">
                <p>IP: <strong>${p.ip}</strong></p>
                <p>Carga: <span class="badge">${p.clients_count}/10</span></p>
            </div>
            <button class="btn-dispatch" onclick="openReallocateModal('${p.id}')">REMANEJAR <i class="fas fa-exchange-alt"></i></button>
        `;
        container.appendChild(card);
    });
}

window.openReallocateModal = async function(proxyId) {
    const currentProxy = allProxies.find(p => p.id === proxyId);
    // Fetch full proxy objects to get coordinates
    const rProx = await fetch('/api/addresses');
    const proxies = await rProx.json();
    
    const r = await fetch(`/api/proxies/${proxyId}/clients`);
    const clients = await r.json();
    
    // Custom Geo Logic: Sort potential targets by proximity
    const targets = allProxies.filter(p => p.id !== proxyId && p.status === 'active')
        .map(p => {
            // Simulated coordinates for demo if missing
            const dist = getDistance(currentProxy.lat || -26.3, currentProxy.lng || -48.8, p.lat || -26.5, p.lng || -48.9);
            return { ...p, distance: dist };
        })
        .sort((a, b) => a.distance - b.distance);

    let clientList = clients.length ? clients.map(c => `
        <div style="background:rgba(255,255,255,0.03); padding:15px; border-radius:10px; margin-bottom:15px; border:1px solid rgba(255,255,255,0.05);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <strong>${c.phone}</strong>
                <span class="status-pill active" style="font-size:0.6rem;">CONECTADO</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-dim); margin-bottom:10px;">SELECIONE O DESTINO PRÓXIMO:</div>
            <div style="display:grid; gap:8px;">
                ${targets.slice(0, 3).map(t => `
                    <button onclick="performReallocate('${c.id}', '${t.id}')" class="btn-dispatch" style="background:rgba(0,122,255,0.1); border:1px solid var(--apple-blue); font-size:0.7rem; display:flex; justify-content:space-between;">
                        <span>Mover para ${t.device}</span>
                        <span style="color:var(--apple-purple)">${t.distance < 1000 ? t.distance.toFixed(1) + 'km' : (t.distance/1000).toFixed(1) + 'k km'}</span>
                    </button>
                `).join('')}
            </div>
        </div>
    `).join('') : '<p style="text-align:center; padding:20px; color:var(--text-dim)">Nenhum cliente ativo neste dispositivo.</p>';

    const modal = document.createElement('div');
    modal.id = "custom-modal";
    modal.className = "fade-in";
    modal.style = "position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); backdrop-filter:blur(10px); z-index:9999; display:flex; align-items:center; justify-content:center; padding:20px;";
    modal.innerHTML = `<div style="background:var(--bg-sidebar); padding:35px; border-radius:20px; width:100%; max-width:500px; border:1px solid var(--border-bright); box-shadow:0 25px 50px rgba(0,0,0,0.5);">
        <header style="margin-bottom:25px;">
            <h2 style="font-size:1.5rem;">Inteligência de Remanejamento</h2>
            <p style="color:var(--text-dim); font-size:0.9rem;">Otimizando conexões por proximidade geográfica.</p>
        </header>
        <div style="max-height:400px; overflow-y:auto; padding-right:10px;">${clientList}</div>
        <button onclick="document.getElementById('custom-modal').remove()" style="margin-top:25px; width:100%; background:rgba(255,255,255,0.05); border:1px solid var(--border);" class="btn-logout">CANCELAR</button>
    </div>`;
    document.body.appendChild(modal);
}

window.performReallocate = async function(clientId, targetProxyId) {
    const r = await fetch('/api/reallocate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ client_id: clientId, new_proxy_id: targetProxyId })
    });
    const res = await r.json();
    showToast("Sucesso no remanejamento!", "info");
    document.getElementById('custom-modal').remove();
    refreshData();
}

// APPLE STYLE MAP
window.openAppleMap = function(state) {
    document.getElementById('map-overlay').style.display = 'flex';
    document.getElementById('map-title-state').innerText = `Rede Basileia: ${state}`;
    
    if (currentMap) currentMap.remove();
    
    // Initialize Leaflet with dark high-fidelity layer
    currentMap = L.map('map-canvas', {
        zoomControl: false,
        attributionControl: false
    }).setView([-23.55, -46.63], 6); // Default BR center
    
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19
    }).addTo(currentMap);

    // Custom Purple Ping Icon
    const pingIcon = L.divIcon({
        className: 'apple-ping-wrapper',
        html: '<div class="apple-ping-container"><div class="apple-ping-ripple"></div></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    const stateMarkers = [];

    // Add markers from allProxies
    allProxies.forEach(p => {
        // Only show if in selected state or global
        if (state && p.estado !== state && state !== 'Basileia Proxy') return;
        
        // Use coordinates or simulation
        const lat = p.lat || -23.55 + (Math.random() - 0.5) * 5;
        const lng = p.lng || -46.63 + (Math.random() - 0.5) * 5;
        
        const marker = L.marker([lat, lng], {icon: pingIcon}).addTo(currentMap)
            .bindPopup(`<div style="background:var(--bg-surface); color:#fff; border-radius:10px; padding:10px; min-width:180px;">
                <h4 style="margin-bottom:5px;">${p.device}</h4>
                <p style="font-size:0.75rem; color:var(--text-dim);">IP: ${p.ip}<br>Cidade: ${p.cidade || 'Não informada'}</p>
                <div style="margin-top:8px; padding-top:8px; border-top:1px solid #333; display:flex; justify-content:space-between; align-items:center;">
                    <span class="status-pill active" style="font-size:0.6rem;">ESTÁVEL</span>
                    <button class="btn-dispatch" style="padding:4px 8px; font-size:0.6rem;">REINICIAR</button>
                </div>
            </div>`, {
                className: 'apple-popup'
            });
            
        if (state && p.estado === state) stateMarkers.push([lat, lng]);
    });

    // Smart Focus: Zoom directly into the state (EXTREME Zoom Edition)
    if (stateMarkers.length > 0) {
        const bounds = L.latLngBounds(stateMarkers);
        currentMap.fitBounds(bounds, { padding: [2, 2], maxZoom: 18 });
    } else if (state && state !== 'Basileia Proxy') {
        // Fallback for states with no proxies yet
        const stateCenters = {
            'SC': [-27.24, -50.21], 'SP': [-23.55, -46.63], 'RJ': [-22.90, -43.17],
            'PR': [-25.42, -49.27], 'MG': [-19.91, -43.93], 'RS': [-30.03, -51.21],
            'BA': [-12.97, -38.50]
        };
        const center = stateCenters[state] || [-15.78, -47.93];
        currentMap.setView(center, 14);
    }
}

window.closeAppleMap = function() {
    document.getElementById('map-overlay').style.display = 'none';
}

// SETTINGS FIX & DETAIL VIEW
window.openSettingBlock = function(block) {
    if (activeTab !== 'settings') {
        switchTab('settings');
        setTimeout(() => showSettingDetail(block), 150);
    } else {
        showSettingDetail(block);
    }
}

function showSettingDetail(block) {
    const grid = document.querySelector('.win-tiles-grid');
    if (grid) grid.style.display = 'none';

    let detailView = document.getElementById('settings-detail');
    if (detailView) detailView.remove();
    
    detailView = document.createElement('div');
    detailView.id = "settings-detail";
    detailView.className = "fade-in";

    let content = '';
    
    if (block === 'account') {
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--accent-secondary); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="fas fa-id-card"></i>
                    </div>
                    <div>
                        <h1 style="font-size:1.8rem;">Minha Conta</h1>
                        <p style="color:var(--text-dim)">Gerenciamento de perfil e credenciais do ecossistema.</p>
                    </div>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
                    <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                        <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">Nome do Sistema</label>
                        <p style="font-weight:700; margin-top:5px;">Basileia Proxy</p>
                    </div>
                    <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                        <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">E-mail Administrativo</label>
                        <p style="font-weight:700; margin-top:5px;">Adm@Proxy.Basileia</p>
                    </div>
                    <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                        <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">IP da Sessão Atual</label>
                        <p style="font-weight:700; margin-top:5px; color:var(--accent-secondary);">192.168.1.15 (Localhost)</p>
                    </div>
                    <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                        <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">Situação</label>
                        <p style="font-weight:700; margin-top:5px;"><span class="status-pill active">ATIVO</span></p>
                    </div>
                </div>
            </div>
        `;
    } else if (block === 'security') {
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--error); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="fas fa-shield-alt"></i>
                    </div>
                    <div>
                        <h1 style="font-size:1.8rem;">Segurança e Privacidade</h1>
                        <p style="color:var(--text-dim)">Autenticação multifator e política de senhas.</p>
                    </div>
                </div>
                
                <div style="margin-bottom:30px;">
                    <h3 style="font-size:1rem; margin-bottom:15px; border-bottom:1px solid var(--border); padding-bottom:10px;">Alterar Senha</h3>
                    <div style="display:grid; gap:15px; max-width:400px;">
                        <input type="password" placeholder="Senha Atual" class="win-input" style="width:100%; background:var(--bg-deep); border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff;">
                        <input type="password" placeholder="Nova Senha" class="win-input" style="width:100%; background:var(--bg-deep); border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff;">
                        <input type="password" placeholder="Confirmar Nova Senha" class="win-input" style="width:100%; background:var(--bg-deep); border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff;">
                        <button class="btn-dispatch" onclick="showToast('Senha alterada com sucesso!', 'info')">Atualizar Senha</button>
                    </div>
                </div>

                <div>
                    <h3 style="font-size:1rem; margin-bottom:15px; border-bottom:1px solid var(--border); padding-bottom:10px;">Configurações Avançadas</h3>
                    <div style="display:grid; gap:15px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.1); border-radius:10px;">
                            <div>
                                <strong>Autenticação de 2 Fatores</strong><br>
                                <small style="color:var(--text-dim)">Exigir código via App ou E-mail no login.</small>
                            </div>
                            <input type="checkbox" checked style="width:20px; height:20px; accent-color:var(--accent-primary);">
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.1); border-radius:10px;">
                            <div>
                                <strong>Método de Captcha</strong><br>
                                <small style="color:var(--text-dim)">Escolha entre o Captcha Simples ou o Puzzle Slider.</small>
                            </div>
                            <select style="background:var(--bg-deep); color:#fff; border:1px solid var(--border); padding:8px; border-radius:8px;">
                                <option value="puzzle">Puzzle Slider (Shopee Style)</option>
                                <option value="simple">Captcha Simples</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } else {
        // Fallback for other tiles
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--apple-purple); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="${getIconForBlock(block)}"></i>
                    </div>
                    <div>
                        <h1 style="font-size:2rem; font-weight:800;">Setor de ${block.charAt(0).toUpperCase() + block.slice(1)}</h1>
                        <p style="color:var(--text-dim)">Gerencie as preferências de ${block} do Basileia Proxy.</p>
                    </div>
                </div>
                <button class="btn-dispatch" onclick="showToast('Setor em desenvolvimento.', 'info')">Acessar Ferramentas</button>
            </div>
        `;
    }

    detailView.innerHTML = `
        <button onclick="closeSettingsDetail()" class="btn-text-link" style="margin-bottom:30px; font-size:0.9rem;">
            <i class="fas fa-chevron-left"></i> VOLTAR PARA CONFIGURAÇÕES
        </button>
        ${content}
    `;
    
    document.getElementById('settings').appendChild(detailView);
}

function getIconForBlock(block) {
    const icons = {
        account: 'fas fa-user-circle',
        security: 'fas fa-shield-alt',
        integrations: 'fas fa-exchange-alt',
        monitoring: 'fas fa-tachometer-alt',
        cleanup: 'fas fa-broom',
        alerts: 'fas fa-bell'
    };
    return icons[block] || 'fas fa-cog';
}

window.closeSettingsDetail = function() {
    const detail = document.getElementById('settings-detail');
    if (detail) detail.remove();
    const grid = document.querySelector('.win-tiles-grid');
    if (grid) grid.style.display = 'grid';
}

// LOGS & DISPATCH
window.dispatchManual = async function(clientId) {
    const r = await fetch(`/api/dispatch/${clientId}`, { method: 'POST' });
    const res = await r.json();
    showToast(res.message, "info");
    refreshData();
}

function updateLogs(logs) {
    const container = document.getElementById('logs-container');
    if (!container) return;
    container.innerHTML = '';
    if (!logs) return;
    logs.slice(0, 10).forEach(log => {
        container.innerHTML += `<div class="log-item" style="padding:12px; border-bottom:1px solid rgba(255,255,255,0.05); animation: fadeIn 0.3s ease;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <small style="color:var(--apple-purple); font-weight:800;">${new Date(log.created_at).toLocaleTimeString()}</small>
                <i class="fas fa-check-circle" style="color:var(--success); font-size:0.7rem;"></i>
            </div>
            <strong style="font-size:0.85rem;">Sistema: ${log.reason}</strong>
        </div>`;
    });
}

async function fetchMonitorData() {
    const r = await fetch('/api/addresses');
    allProxies = await r.json();
    const list = document.getElementById('monitor-ip-list');
    list.innerHTML = '';
    allProxies.forEach(p => {
        const item = document.createElement('div');
        item.className = 'ip-item';
        item.innerHTML = `<i class="fas fa-network-wired"></i> ${p.ip}`;
        item.onclick = () => loadIPFlow(p.ip, item);
        list.appendChild(item);
    });
}

function showToast(msg, type) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<i class="fas fa-info-circle"></i> ${msg}`;
    document.getElementById('toast-container').appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// Init
refreshData();
setInterval(refreshData, 30000);
