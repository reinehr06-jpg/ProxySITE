# ProxySITE - Demonstração para Apresentação

O sistema já está rodando com dados de demonstração. Acesse: **http://127.0.0.1:8000/dashboard/**

---

## Como Demonstrar Cada Funcionalidade

### 1. 📊 Monitoramento em Tempo Real
- Vá ao **Dashboard** (página inicial)
- Mostra: Clientes Ativos, Offline, Tempo Médio de Resposta
- **Demonstração**: Já populado com 8 igrejas com diferentes status

### 2. 🏛️ Gestão de Multi-Igrejas (Basileia)
- Clique na aba **Clientes**
- Use a **busca** por telefone, CPF/CNPJ, Igreja ou ID
- Filtre por **Estado** e **Cidade**
- **Demonstração**: Liste todas as igrejas cadastradas

### 3. 🔄 Failover Automático
- No Dashboard, veja a seção **Quedas Recentes**
- Quando um proxy cai, o sistema muda automaticamente para outro na mesma cidade/estado
- **Demonstração**:模拟已有 igrejas com status "error" e "disconnected"

### 4. 🗺️ Mapa Geográfico
- Clique na aba **Estados**
- Visualize os proxies no mapa Leaflet
- **Demonstração**: 7 proxies em diferentes estados do Brasil

### 5. 📍 Controle de Endereços/IPs
- Clique na aba **Endereços**
- Veja todos os dispositivos e seus IPs
- Mostra quantidade de clientes por dispositivo
- **Demonstração**: 7 dispositivos cadastrados

### 6. ⚙️ Configurações e Integrações
- Clique na aba **Configurações**
- Configure **UazAPI** (conexão WhatsApp)
- Configure **Basileia API**
- **Demonstração**: Painel estilo Windows 10

### 7. 📈 Histórico de Requisições
- Acesse via **Configurações** > Monitoramento
- Veja logs de rede por IP
- **Demonstração**: Dados de Example simulados

### 8. 🧹 Manutenção de Banco
- Acesse **Configurações** > Limpeza
- Veja estatísticas de dados antigos
- Execute limpeza de registros velhos

---

## API Endpoints Úteis

```bash
# Stats do sistema
curl http://127.0.0.1:8000/api/stats

# Lista clientes
curl http://127.0.0.1:8000/api/clients

# Endereços/IPs
curl http://127.0.0.1:8000/api/addresses

# Configurações de integração
curl http://127.0.0.1:8000/api/integrations
```

---

## Executar Novamente com Dados Frescos

```bash
curl -X POST http://127.0.0.1:8000/api/seed
```

---

**Login**: O sistema pede autenticação. Para pular, edite `main.js` e remova o redirecionamento para login.html.