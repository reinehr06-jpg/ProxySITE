const API_BASE = '/secure-events/api';
let authToken = localStorage.getItem('events_token');
let refreshToken = localStorage.getItem('events_refresh_token');

// Auth
const auth = {
    async login(email, password) {
        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);
        
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Login failed');
        }
        
        authToken = data.access_token;
        refreshToken = data.refresh_token;
        localStorage.setItem('events_token', authToken);
        localStorage.setItem('events_refresh_token', refreshToken);
        localStorage.setItem('events_user', JSON.stringify(data.user));
        
        return data;
    },
    
    async refresh() {
        if (!refreshToken) return false;
        
        const response = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${refreshToken}`
            }
        });
        
        if (!response.ok) {
            this.logout();
            return false;
        }
        
        const data = await response.json();
        authToken = data.access_token;
        refreshToken = data.refresh_token;
        localStorage.setItem('events_token', authToken);
        localStorage.setItem('events_refresh_token', refreshToken);
        
        return true;
    },
    
    logout() {
        authToken = null;
        refreshToken = null;
        localStorage.removeItem('events_token');
        localStorage.removeItem('events_refresh_token');
        localStorage.removeItem('events_user');
        window.location.href = 'index.html';
    },
    
    getUser() {
        const user = localStorage.getItem('events_user');
        return user ? JSON.parse(user) : null;
    },
    
    isAuthenticated() {
        return !!authToken;
    }
};

// API Helper
async function apiCall(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        const refreshed = await auth.refresh();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${authToken}`;
            return fetch(`${API_BASE}${endpoint}`, {
                ...options,
                headers
            });
        }
    }
    
    return response;
}

// Events API
const eventsApi = {
    async list() {
        const response = await apiCall('/events');
        return response.json();
    },
    
    async get(id) {
        const response = await apiCall(`/events/${id}`);
        return response.json();
    },
    
    async create(data) {
        const response = await apiCall('/events', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async update(id, data) {
        const response = await apiCall(`/events/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async end(id) {
        const response = await apiCall(`/events/${id}/end`, {
            method: 'POST'
        });
        return response.json();
    },
    
    async deleteFace(eventId, ticketId) {
        const response = await apiCall(`/events/${eventId}/faces/${ticketId}`, {
            method: 'DELETE'
        });
        return response.json();
    },
    
    async deleteAllFaces(eventId) {
        const response = await apiCall(`/events/${eventId}/faces`, {
            method: 'DELETE'
        });
        return response.json();
    },
    
    async getStats(id) {
        const response = await apiCall(`/events/${id}/stats`);
        return response.json();
    }
};

// Faces API
const facesApi = {
    async register(eventId, ticketId, imageBase64) {
        const response = await apiCall(`/events/${eventId}/faces`, {
            method: 'POST',
            body: JSON.stringify({ ticket_id: ticketId, image_base64: imageBase64 })
        });
        return response.json();
    },
    
    async list(eventId, status) {
        const params = status ? `?status_filter=${status}` : '';
        const response = await apiCall(`/events/${eventId}/faces${params}`);
        return response.json();
    },
    
    async validate(eventId, imageBase64) {
        const response = await apiCall(`/faces/validate?event_id=${eventId}`, {
            method: 'POST',
            body: JSON.stringify({ image_base64: imageBase64 })
        });
        return response.json();
    },
    
    async count(eventId, status = 'active') {
        const response = await apiCall(`/events/${eventId}/faces/count?status=${status}`);
        return response.json();
    },
    
    async delete(eventId, ticketId) {
        const response = await apiCall(`/events/${eventId}/faces/${ticketId}`, {
            method: 'DELETE'
        });
        return response.json();
    }
};

// Totems API
const totemsApi = {
    async list(eventId) {
        const response = await apiCall(`/totems?event_id=${eventId}`);
        return response.json();
    },
    
    async create(eventId, data) {
        const response = await apiCall(`/totems?event_id=${eventId}`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async get(id) {
        const response = await apiCall(`/totems/${id}`);
        return response.json();
    },
    
    async update(id, data) {
        const response = await apiCall(`/totems/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async delete(id) {
        const response = await apiCall(`/totems/${id}`, {
            method: 'DELETE'
        });
        return response.ok;
    },
    
    async regenerateKey(id) {
        const response = await apiCall(`/totems/${id}/regenerate-key`, {
            method: 'POST'
        });
        return response.json();
    },
    
    async getStatus(eventId) {
        const response = await apiCall(`/totems/status/${eventId}`);
        return response.json();
    }
};

// Logs API
const logsApi = {
    async list(params = {}) {
        const query = new URLSearchParams(params).toString();
        const response = await apiCall(`/logs?${query}`);
        return response.json();
    },
    
    async alerts(eventId) {
        const url = eventId ? `/logs/alerts?event_id=${eventId}` : '/logs/alerts';
        const response = await apiCall(url);
        return response.json();
    },
    
    async stats(eventId) {
        const url = eventId ? `/logs/stats?event_id=${eventId}` : '/logs/stats';
        const response = await apiCall(url);
        return response.json();
    }
};

// UI Helpers
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 4000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

function showModal(content) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            ${content}
        </div>
    `;
    overlay.onclick = (e) => {
        if (e.target === overlay) overlay.remove();
    };
    document.body.appendChild(overlay);
    return overlay;
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('pt-BR');
}

function formatRelativeTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'agora';
    if (minutes < 60) return `${minutes}min`;
    if (hours < 24) return `${hours}h`;
    return `${days}d`;
}

// Check auth on page load
function requireAuth() {
    if (!auth.isAuthenticated()) {
        window.location.href = 'index.html';
    }
}

// Logout handler
function handleLogout() {
    auth.logout();
}