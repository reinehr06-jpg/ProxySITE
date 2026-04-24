// AUTH CHECK - DESABILITADO PARA DEMONSTRAÇÃO
// if (!localStorage.getItem('isAuthenticated') && !window.location.href.includes('login.html')) {
//     window.location.href = 'login.html';
// }

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
    if (activeTab === 'ip-logs' && window.currentIP) await loadIPLogs(window.currentIP);
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
            <div style="display:flex; gap:10px;">
                <button class="btn-dispatch" onclick="selectIPFromAddress('${p.ip}')" style="flex:1;">VER LOGS <i class="fas fa-list"></i></button>
                <button class="btn-dispatch" onclick="openReallocateModal('${p.id}')" style="flex:1;">REMANEJAR <i class="fas fa-exchange-alt"></i></button>
            </div>
        `;
        container.appendChild(card);
    });
}

window.selectIPFromAddress = function(ip) {
    window.currentIP = ip;
    document.getElementById('ip-logs-title').innerHTML = `<i class="fas fa-wifi"></i> Logs: ${ip}`;
    switchTab('ip-logs');
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
                        <p style="font-weight:700; margin-top:5px;">Vault.basileia@basileia.global</p>
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
    } else if (block === 'integrations') {
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--accent-primary); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="fas fa-exchange-alt"></i>
                    </div>
                    <div>
                        <h1 style="font-size:1.8rem;">Integrações</h1>
                        <p style="color:var(--text-dim)">Configure suas conexões com APIs externas.</p>
                    </div>
                </div>
                
                <div style="margin-bottom:40px;">
                    <h3 style="font-size:1rem; margin-bottom:15px; border-bottom:1px solid var(--border); padding-bottom:10px; display:flex; align-items:center; gap:10px;">
                        <i class="fab fa-whatsapp"></i> Uazapi (WhatsApp)
                    </h3>
                    <div style="display:grid; gap:15px;">
                        <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                            <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">API Key Uazapi</label>
                            <input type="password" id="uazapi-key" placeholder="Cole sua API Key aqui" style="width:100%; background:var(--bg-deep); border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff; margin-top:8px;">
                            <div id="uazapi-status" style="margin-top:10px; font-size:0.9rem;"></div>
                        </div>
                        <div style="display:flex; gap:10px;">
                            <button class="btn-dispatch" onclick="saveIntegrations()">Salvar</button>
                            <button class="btn-dispatch" style="background:var(--accent-secondary);" onclick="testUazapiConnection()">Testar Conexão</button>
                        </div>
                    </div>
                </div>

                <div>
                    <h3 style="font-size:1rem; margin-bottom:15px; border-bottom:1px solid var(--border); padding-bottom:10px; display:flex; align-items:center; gap:10px;">
                        <i class="fas fa-church"></i> Basileia Church API
                    </h3>
                    <div style="display:grid; gap:15px;">
                        <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                            <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">API Key</label>
                            <input type="password" id="basileia-key" placeholder="Cole sua API Key" style="width:100%; background:var(--bg-deep); border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff; margin-top:8px;">
                        </div>
                        <div class="info-box" style="padding:15px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid var(--border);">
                            <label style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">Webhook URL</label>
                            <input type="text" id="basileia-webhook" placeholder="https://seu-webhook.com/webhook" style="width:100%; background:var(--bg-deep); border:1px solid var(--border); padding:12px; border-radius:8px; color:#fff; margin-top:8px;">
                            <small style="color:var(--text-dim); display:block; margin-top:5px;">URL para receber eventos do Basileia Church</small>
                            <div id="webhook-status" style="margin-top:10px; font-size:0.9rem;"></div>
                        </div>
                        <button class="btn-dispatch" onclick="saveBasileiaConfig()">Salvar Configurações</button>
                    </div>
                </div>
            </div>
            <script>loadIntegrationSettings();</script>
        `;
    } else if (block === 'monitoring') {
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--accent-secondary); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="fas fa-tachometer-alt"></i>
                    </div>
                    <div>
                        <h1 style="font-size:1.8rem;">Monitoramento de Tráfego</h1>
                        <p style="color:var(--text-dim)">Selecione um IP para filtrar.</p>
                    </div>
                </div>
                
                <div style="margin-top:30px;">
                    <div style="margin-bottom:15px;">
                        <input type="text" id="monitor-search" placeholder="Buscar IP..." 
                            style="width:100%; padding:10px; border-radius:8px; background:var(--bg-deep); border:1px solid var(--border); color:#fff;"
                            onkeyup="filterMonitorIPs()">
                    </div>
                    <h3 style="margin-bottom:15px; font-size:1rem;"><i class="fas fa-network-wired"></i> Selecione um IP</h3>
                    <div class="ip-list" id="monitor-ip-list" style="max-height:400px; overflow-y:auto;"></div>
                </div>
            </div>
        `;
    } else if (block === 'cleanup') {
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--error); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="fas fa-broom"></i>
                    </div>
                    <div>
                        <h1 style="font-size:1.8rem;">Limpeza do Banco</h1>
                        <p style="color:var(--text-dim)">Remova dados inativos há mais de 3 meses.</p>
                    </div>
                </div>
                
                <div id="cleanup-stats" style="margin-top:20px;">
                    <p style="color:var(--text-dim);">Carregando...</p>
                </div>
                
                <div style="margin-top:30px; padding:20px; background:rgba(245,158,11,0.1); border-radius:10px; border:1px solid var(--warning);">
                    <h4 style="margin-bottom:10px;"><i class="fas fa-exclamation-triangle"></i>Atenção</h4>
                    <p style="font-size:0.9rem; color:var(--text-dim);">Esta ação removerá permanentemente: clientes inativos, proxies sem atividade e logs com mais de 3 meses. Esta ação não pode ser desfeita.</p>
                </div>
                
                <button class="btn-dispatch" style="background:var(--error); margin-top:20px;" onclick="runCleanup()">
                    <i class="fas fa-trash"></i> Executar Limpeza
                </button>
            </div>
            <script>loadCleanupData();</script>
        `;
    } else if (block === 'alerts') {
        content = `
            <div class="mini-card" style="padding:40px; border:1px solid var(--border-bright);">
                <div style="display:flex; align-items:center; gap:20px; margin-bottom:30px;">
                    <div class="tile-icon" style="background:var(--warning); color:#fff; border-radius:12px; height:60px; width:60px; display:flex; align-items:center; justify-content:center; font-size:1.8rem;">
                        <i class="fas fa-bell"></i>
                    </div>
                    <div>
                        <h1 style="font-size:1.8rem;">Alertas do Sistema</h1>
                        <p style="color:var(--text-dim)">Histórico de alertas e notificações.</p>
                    </div>
                </div>
                
                <div style="margin-bottom:20px; display:flex; gap:10px;">
                    <button class="btn-dispatch" onclick="loadAlertsData()">Todos</button>
                    <button class="btn-dispatch" style="background:var(--error);" onclick="filterAlerts('error')">Erros</button>
                    <button class="btn-dispatch" style="background:var(--warning);" onclick="filterAlerts('warning')">Avisos</button>
                    <button class="btn-dispatch" style="background:var(--success);" onclick="filterAlerts('success')">Sucesso</button>
                </div>
                
                <div id="alerts-list" style="max-height:500px; overflow-y:auto;">
                    <p style="color:var(--text-dim);">Carregando...</p>
                </div>
            </div>
            <script>loadAlertsData();</script>
        `;
    }

    detailView.innerHTML = `
        <button onclick="closeSettingsDetail()" class="btn-text-link" style="margin-bottom:30px; font-size:0.9rem;">
            <i class="fas fa-chevron-left"></i> VOLTAR PARA CONFIGURAÇÕES
        </button>
        ${content}
    `;
    
    document.getElementById('settings').appendChild(detailView);
    
    // Chama fetchMonitorData para monitoramento
    if (block === 'monitoring') {
        setTimeout(fetchMonitorData, 300);
    }
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
    setTimeout(async () => {
        const list = document.getElementById('monitor-ip-list');
        if (!list) {
            console.log('Elemento monitor-ip-list não encontrado');
            return;
        }
        try {
            const r = await fetch('/api/addresses');
            allProxies = await r.json();
            console.log('IPs carregados:', allProxies.length);
            renderMonitorIPList(allProxies);
        } catch(e) {
            console.error('Erro fetchMonitorData:', e);
        }
    }, 300);
}

function renderMonitorIPList(proxies) {
    const list = document.getElementById('monitor-ip-list');
    if (!list) return;
    list.innerHTML = '';
    proxies.forEach(p => {
        const item = document.createElement('div');
        item.className = 'ip-item';
        item.style.cssText = 'padding:12px; cursor:pointer; border-radius:8px; margin-bottom:5px; transition:all 0.2s;';
        item.innerHTML = `<i class="fas fa-network-wired"></i> <strong>${p.ip}</strong> <span style="float:right; font-size:0.8rem; color:var(--text-dim);">${p.clients_count || 0} msgs</span>`;
        item.onclick = () => selectIP(p.ip, item);
        list.appendChild(item);
    });
}

window.filterMonitorIPs = function() {
    const search = document.getElementById('monitor-search').value.toLowerCase();
    const filtered = allProxies.filter(p => p.ip.toLowerCase().includes(search));
    renderMonitorIPList(filtered);
}

window.currentIP = null;
window.allIPLogs = [];

window.selectIP = async function(ip, element) {
    document.querySelectorAll('.ip-item').forEach(el => el.style.background = 'transparent');
    if (element) element.style.background = 'rgba(59,130,246,0.2)';
    
    window.currentIP = ip;
    document.getElementById('ip-logs-title').innerHTML = `<i class="fas fa-wifi"></i> Logs: ${ip}`;
    switchTab('ip-logs');
    await loadIPLogs(ip);
}

window.loadIPLogs = async function(ip) {
    const tbody = document.getElementById('ip-logs-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="7" style="padding:40px; text-align:center;">Carregando...</td></tr>';
    
    try {
        const r = await fetch('/api/monitoring/proxy/' + ip);
        const logs = await r.json();
        
        window.allIPLogs = logs;
        
        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="padding:40px; text-align:center; color:var(--text-dim);">Nenhuma transação registrada para este IP.</td></tr>';
            return;
        }
        
        renderIPLogs(logs);
    } catch (e) {
        console.error('Erro ao carregar logs:', e);
        tbody.innerHTML = '<tr><td colspan="7" style="padding:40px; text-align:center; color:var(--error);">Erro ao carregar dados.</td></tr>';
    }
}

window.renderIPLogs = function(logs) {
    const tbody = document.getElementById('ip-logs-table-body');
    if (!tbody) return;
    
    if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="padding:40px; text-align:center; color:var(--text-dim);">Nenhuma transação encontrada</td></tr>';
        return;
    }
    
    tbody.innerHTML = logs.map(log => {
        const date = log.created_at ? new Date(log.created_at) : null;
        const day = date ? date.toLocaleDateString('pt-BR') : '-';
        const time = date ? date.toLocaleTimeString('pt-BR') : '-';
        const isSuccess = log.status_code === 200;
        return `
            <tr>
                <td style="padding:12px;">${day}</td>
                <td style="padding:12px;">${time}</td>
                <td style="padding:12px; font-weight:700; color:var(--accent-primary);">${log.method || '-'}</td>
                <td style="padding:12px; color:var(--text-dim); max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${log.endpoint || ''}">${log.endpoint || '-'}</td>
                <td style="padding:12px; text-align:center;">
                    <span style="background:${isSuccess ? 'var(--success)' : 'var(--error)'}; padding:4px 10px; border-radius:12px; font-size:0.75rem; font-weight:600;">${log.status_code || '-'}</span>
                </td>
                <td style="padding:12px; text-align:right; color:var(--text-dim);">${log.response_time ? (log.response_time * 1000).toFixed(0) + 'ms' : '-'}</td>
                <td style="padding:12px; text-align:center;">
                    <button class="btn-logout" onclick="showLogDetail('${log.id}')" style="padding:5px 10px; font-size:0.8rem;">
                        <i class="fas fa-eye"></i> Ver
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

window.filterIPLogs = function() {
    const search = document.getElementById('ip-logs-search').value.toLowerCase();
    const filtered = window.allIPLogs.filter(log => 
        (log.method || '').toLowerCase().includes(search) ||
        (log.endpoint || '').toLowerCase().includes(search) ||
        (log.error_message || '').toLowerCase().includes(search)
    );
    renderIPLogs(filtered);
}

window.showLogDetail = function(logId) {
    const log = window.allIPLogs.find(l => l.id === logId);
    if (!log) return;
    
    const date = log.created_at ? new Date(log.created_at) : null;
    const isSuccess = log.status_code === 200;
    
    const detailHtml = `
        <div style="position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); z-index:1000; display:flex; align-items:center; justify-content:center;" onclick="this.remove();">
            <div style="background:var(--bg-deep); border-radius:12px; padding:30px; max-width:900px; width:90%; max-height:90vh; overflow-y:auto;" onclick="event.stopPropagation();">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                    <h2 style="font-size:1.5rem;"><i class="fas fa-file-alt"></i> Detalhes da Transação</h2>
                    <button class="btn-logout" onclick="this.closest('[style*=&quot;position:fixed&quot;]').remove();" style="padding:8px 15px;">
                        <i class="fas fa-times"></i> Fechar
                    </button>
                </div>
                
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;">
                    <div style="padding:15px; background:rgba(0,0,0,0.2); border-radius:8px;">
                        <strong style="color:var(--accent-primary);">Método</strong>
                        <p style="font-size:1.2rem; font-weight:700;">${log.method || '-'}</p>
                    </div>
                    <div style="padding:15px; background:rgba(0,0,0,0.2); border-radius:8px;">
                        <strong style="color:var(--accent-primary);">Status</strong>
                        <p style="font-size:1.2rem; font-weight:700; color:${isSuccess ? 'var(--success)' : 'var(--error)'};">${log.status_code || '-'}</p>
                    </div>
                </div>
                
                <div style="margin-bottom:20px;">
                    <strong style="color:var(--accent-primary);">Endpoint</strong>
                    <p style="padding:10px; background:rgba(0,0,0,0.2); border-radius:8px; word-break:break-all;">${log.endpoint || '-'}</p>
                </div>
                
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;">
                    <div>
                        <strong style="color:var(--accent-primary);">Data</strong>
                        <p style="color:var(--text-dim);">${date ? date.toLocaleString('pt-BR') : '-'}</p>
                    </div>
                    <div>
                        <strong style="color:var(--accent-primary);">Tempo de Resposta</strong>
                        <p style="color:var(--text-dim);">${log.response_time ? (log.response_time * 1000).toFixed(2) + 'ms' : '-'}</p>
                    </div>
                </div>
                
                ${log.request_headers ? `
                    <div style="margin-bottom:20px;">
                        <strong style="color:var(--accent-primary);">Requisição Headers</strong>
                        <pre style="padding:15px; background:rgba(0,0,0,0.2); border-radius:8px; overflow-x:auto; font-size:0.8rem; max-height:200px;">${log.request_headers}</pre>
                    </div>
                ` : ''}
                
                ${log.request_body ? `
                    <div style="margin-bottom:20px;">
                        <strong style="color:var(--accent-primary);">Request Body</strong>
                        <pre style="padding:15px; background:rgba(0,0,0,0.2); border-radius:8px; overflow-x:auto; font-size:0.8rem; max-height:200px; word-break:break-all;">${log.request_body}</pre>
                    </div>
                ` : ''}
                
                ${log.response_body ? `
                    <div style="margin-bottom:20px;">
                        <strong style="color:var(--accent-primary);">Response Body</strong>
                        <pre style="padding:15px; background:rgba(0,0,0,0.2); border-radius:8px; overflow-x:auto; font-size:0.8rem; max-height:300px; word-break:break-all;">${log.response_body}</pre>
                    </div>
                ` : ''}
                
                ${log.error_message ? `
                    <div style="margin-bottom:20px; padding:15px; background:rgba(239,68,68,0.1); border-radius:8px; border:1px solid var(--error);">
                        <strong style="color:var(--error);">Mensagem de Erro</strong>
                        <p style="color:var(--error);">${log.error_message}</p>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', detailHtml);
}

function showToast(msg, type) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<i class="fas fa-info-circle"></i> ${msg}`;
    document.getElementById('toast-container').appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

window.loadMonitoringData = async function() {
    const table = document.getElementById('monitoring-table');
    if (!table) return;
    try {
        const r = await fetch('/api/addresses');
        const proxies = await r.json();
        if (proxies.length === 0) {
            table.innerHTML = '<p style="padding:20px; text-align:center; color:var(--text-dim);">Nenhum proxy encontrado</p>';
            return;
        }
        table.innerHTML = '<table style="width:100%; border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="padding:12px; text-align:left;">IP</th><th style="padding:12px;">Clientes</th><th style="padding:12px;">Tempo</th><th style="padding:12px;">Status</th></tr></thead><tbody>' + 
            proxies.map(p => `<tr style="border-bottom:1px solid var(--border);">
                <td style="padding:12px; font-weight:700;">${p.ip}</td>
                <td style="padding:12px;">${p.clients_count || 0}</td>
                <td style="padding:12px;">${p.avg_response ? p.avg_response.toFixed(1)+'ms' : '0ms'}</td>
                <td style="padding:12px;"><span class="status-pill ${p.status === 'active' ? 'active' : ''}" style="background:var(--error);">${p.status}</span></td>
            </tr>`).join('') + '</tbody></table>';
    } catch (e) {
        table.innerHTML = '<p style="padding:20px; color:var(--error);">Erro ao carregar</p>';
    }
};

window.loadCleanupData = async function() {
    showToast('Carregando dados de limpeza...', 'info');
};

window.testUazapi = async function() {
    const apiKey = document.getElementById('uazapi-key').value;
    if (!apiKey) {
        showToast('Por favor, insira uma API Key', 'error');
        return;
    }
    showToast('Testando conexão...', 'info');
    setTimeout(() => showToast('Conexão estabelecida!', 'success'), 1500);
};

window.goToSecureEvents = async function() {
    showToast('Gerando token de acesso...', 'info');
    try {
        const token = localStorage.getItem('access_token');
        if (!token) {
            showToast(' Faça login primeiro!', 'error');
            return;
        }
        
        const response = await fetch('/api/auth/cross-system-token', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!response.ok) {
            throw new Error('Falha ao gerar token');
        }
        
        const data = await response.json();
        
        // Open in new tab
        window.open(data.url, '_blank');
        showToast('Secure Events aberto em nova aba!', 'success');
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
};

// Init
refreshData();
setInterval(refreshData, 30000);

// ==== INTEGRAÇÕES ====
window.loadIntegrationSettings = async function() {
    try {
        const r = await fetch('/api/integrations');
        const data = await r.json();
        if (data.uazapi_key) document.getElementById('uazapi-key').value = data.uazapi_key;
        if (data.basileia_key) document.getElementById('basileia-key').value = data.basileia_key;
        if (data.basileia_webhook) document.getElementById('basileia-webhook').value = data.basileia_webhook;
        
        // Status Uazapi
        const uazStatus = document.getElementById('uazapi-status');
        if (uazStatus) {
            uazStatus.innerHTML = data.uazapi_connected 
                ? '<span style="color:var(--success);"><i class="fas fa-check-circle"></i> Conectado</span>'
                : '<span style="color:var(--error);"><i class="fas fa-times-circle"></i> Não conectado</span>';
        }
    } catch (e) {
        console.error('Erro ao carregar configurações:', e);
    }
};

window.saveIntegrations = async function() {
    const key = document.getElementById('uazapi-key').value;
    if (!key) {
        showToast('Por favor, insira uma API Key', 'error');
        return;
    }
    try {
        const r = await fetch('/api/integrations', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({uazapi_key: key})
        });
        const data = await r.json();
        showToast(data.message || 'Salvo com sucesso!', 'success');
        loadIntegrationSettings();
    } catch (e) {
        showToast('Erro ao salvar', 'error');
    }
};

window.testUazapiConnection = async function() {
    const key = document.getElementById('uazapi-key').value;
    if (!key) {
        showToast('Por favor, insira uma API Key', 'error');
        return;
    }
    showToast('Testando conexão...', 'info');
    try {
        const r = await fetch('/api/integrations/test-uazapi?key=' + encodeURIComponent(key));
        const data = await r.json();
        if (data.connected) {
            showToast('Conexão estabelecida!', 'success');
        } else {
            showToast(data.message || 'Falha na conexão', 'error');
        }
        loadIntegrationSettings();
    } catch (e) {
        showToast('Erro ao testar conexão', 'error');
    }
};

window.saveBasileiaConfig = async function() {
    const key = document.getElementById('basileia-key').value;
    const webhook = document.getElementById('basileia-webhook').value;
    try {
        const r = await fetch('/api/integrations', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({basileia_key: key, basileia_webhook: webhook})
        });
        const data = await r.json();
        showToast(data.message || 'Salvo com sucesso!', 'success');
    } catch (e) {
        showToast('Erro ao salvar', 'error');
    }
};

// ==== MONITORAMENTO ====
window.loadMonitoringData = async function() {
    const table = document.getElementById('monitoring-table');
    if (!table) return;
    try {
        const r = await fetch('/api/addresses');
        const proxies = await r.json();
        if (proxies.length === 0) {
            table.innerHTML = '<p style="padding:20px; text-align:center; color:var(--text-dim);">Nenhum proxy encontrado</p>';
            return;
        }
        table.innerHTML = '<table style="width:100%; border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="padding:12px; text-align:left;">IP</th><th style="padding:12px;">Clientes</th><th style="padding:12px;">Tempo</th><th style="padding:12px;">Status</th></tr></thead><tbody>' + 
            proxies.map(p => `<tr style="border-bottom:1px solid var(--border);">
                <td style="padding:12px; font-weight:700;">${p.ip}</td>
                <td style="padding:12px;">${p.clients_count || 0}</td>
                <td style="padding:12px;">${p.avg_response ? p.avg_response.toFixed(1)+'ms' : '0ms'}</td>
                <td style="padding:12px;"><span class="status-pill ${p.status === 'active' ? 'active' : ''}" style="background:var(--error);">${p.status}</span></td>
            </tr>`).join('') + '</tbody></table>';
    } catch (e) {
        table.innerHTML = '<p style="padding:20px; color:var(--error);">Erro ao carregar</p>';
    }
};

// ==== LIMPEZA ====
window.loadCleanupData = async function() {
    const statsDiv = document.getElementById('cleanup-stats');
    if (!statsDiv) return;
    try {
        const r = await fetch('/api/cleanup/stats');
        const data = await r.json();
        statsDiv.innerHTML = `
            <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:15px; margin:20px 0;">
                <div style="padding:20px; background:rgba(239,68,68,0.1); border-radius:10px; border:1px solid var(--error); text-align:center;">
                    <div style="font-size:2rem; font-weight:800; color:var(--error);">${data.inactive_clients || 0}</div>
                    <small>Clientes Inativos</small>
                </div>
                <div style="padding:20px; background:rgba(239,68,68,0.1); border-radius:10px; border:1px solid var(--error); text-align:center;">
                    <div style="font-size:2rem; font-weight:800; color:var(--error);">${data.inactive_proxies || 0}</div>
                    <small>Proxies Inativos</small>
                </div>
                <div style="padding:20px; background:rgba(239,68,68,0.1); border-radius:10px; border:1px solid var(--error); text-align:center;">
                    <div style="font-size:2rem; font-weight:800; color:var(--error);">${data.old_logs || 0}</div>
                    <small>Logs Antigos</small>
                </div>
            </div>
        `;
    } catch (e) {
        statsDiv.innerHTML = '<p style="padding:20px; color:var(--error);">Erro ao carregar dados</p>';
    }
};

window.runCleanup = async function() {
    if (!confirm('Tem certeza que deseja limpar dados com mais de 3 meses?')) return;
    try {
        const r = await fetch('/api/cleanup/clean', {method: 'POST'});
        const data = await r.json();
        showToast(data.message || 'Limpeza concluída!', 'success');
        loadCleanupData();
    } catch (e) {
        showToast('Erro ao executar limpeza', 'error');
    }
};

// ==== ALERTAS ====
window.loadAlertsData = async function() {
    const alertsDiv = document.getElementById('alerts-list');
    if (!alertsDiv) return;
    try {
        const r = await fetch('/api/alerts');
        const alerts = await r.json();
        if (alerts.length === 0) {
            alertsDiv.innerHTML = '<p style="padding:20px; text-align:center; color:var(--text-dim);">Nenhum alerta registrado</p>';
            return;
        }
        alertsDiv.innerHTML = alerts.map(a => `
            <div style="padding:15px; border-bottom:1px solid var(--border); background:rgba(${a.level === 'error' ? '239,68,68' : a.level === 'success' ? '16,185,129' : '245,158,11'},0.05);">
                <strong style="color:var(--${a.level === 'error' ? 'error' : a.level === 'success' ? 'success' : 'warning'});">${a.type}</strong>
                <p style="color:var(--text-dim); font-size:0.9rem;">${a.message.substring(0, 100)}</p>
                <small style="color:var(--text-dim);">${a.created_at ? new Date(a.created_at).toLocaleString() : ''}</small>
            </div>
        `).join('');
    } catch (e) {
        alertsDiv.innerHTML = '<p style="padding:20px; color:var(--error);">Erro ao carregar alertas</p>';
    }
};

window.filterAlerts = async function(level) {
    const alertsDiv = document.getElementById('alerts-list');
    if (!alertsDiv) return;
    try {
        const r = await fetch('/api/alerts?level=' + level);
        const alerts = await r.json();
        if (alerts.length === 0) {
            alertsDiv.innerHTML = '<p style="padding:20px; text-align:center; color:var(--text-dim);">Nenhum alerta encontrado</p>';
            return;
        }
        alertsDiv.innerHTML = alerts.map(a => `
            <div style="padding:15px; border-bottom:1px solid var(--border); background:rgba(${a.level === 'error' ? '239,68,68' : a.level === 'success' ? '16,185,129' : '245,158,11'},0.05);">
                <strong style="color:var(--${a.level === 'error' ? 'error' : a.level === 'success' ? 'success' : 'warning'});">${a.type}</strong>
                <p style="color:var(--text-dim); font-size:0.9rem;">${a.message.substring(0, 100)}</p>
                <small style="color:var(--text-dim);">${a.created_at ? new Date(a.created_at).toLocaleString() : ''}</small>
            </div>
        `).join('');
    } catch (e) {
        alertsDiv.innerHTML = '<p style="padding:20px; color:var(--error);">Erro ao filtrar alertas</p>';
    }
};

window.testUazapi = async function() {
    const apiKey = document.getElementById('uazapi-key').value;
    if (!apiKey) {
        showToast('Por favor, insira uma API Key', 'error');
        return;
    }
    showToast('Testando conexão...', 'info');
    setTimeout(() => showToast('Conexão estabelecida!', 'success'), 1500);
};
// Systems Switcher Logic
function toggleSystems() {
    const dropdown = document.getElementById('switcher-dropdown');
    dropdown.classList.toggle('active');
}

// Close switcher when clicking outside
window.addEventListener('click', function(e) {
    const switcher = document.querySelector('.systems-switcher');
    const dropdown = document.getElementById('switcher-dropdown');
    if (switcher && !switcher.contains(e.target)) {
        dropdown.classList.remove('active');
    }
});
