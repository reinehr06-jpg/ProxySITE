# ProxySITE - Documentação para Desenvolvedores

## Visão Geral

Projeto com dois subsistemas no mesmo backend:
1. **ProxySITE** - Gerenciamento de proxies para automação WhatsApp
2. **Secure Events** - Biometria facial + QR Check-in + Gestão de Totens

## Estrutura

```
ProxySITE/
├── app/
│   ├── api/                    # Rotas API
│   │   ├── routes_*.py         # Rotas do ProxySITE
│   │   └── events/             # Rotas do Secure Events
│   ├── core/                   # Configurações centrais
│   │   ├── config.py           # Variáveis de ambiente
│   │   ├── auth.py             # Autenticação JWT do Proxy
│   │   ├── events_security.py  # Autenticação JWT do Secure Events
│   │   ├── database.py         # Conexão DB
│   │   └── security.py         # Middleware segurança
│   ├── models/
│   │   ├── all_models.py       # Models do Proxy
│   │   └── events/             # Models do Secure Events
│   ├── services/
│   │   └── events/             # Serviços do Secure Events
│   └── jobs/                   # Jobs agendados
├── engines/                    # Engines de reconhecimento facial
│   ├── rekognition_engine.py   # AWS Rekognition
│   └── compreface_engine.py    # CompreFace
├── static/
│   ├── secure-events/          # Frontend Admin
│   └── secure-events/portaria/ # App Portaria/Totem
├── .env                        # Variáveis locais (NÃO COMMITAR)
└── seed_events_admin.py        # Script para criar admin inicial
```

## Variáveis de Ambiente

### ProxySITE
- `DATABASE_URL` - Conexão PostgreSQL
- `SECRET_KEY` - Chave JWT do proxy

### Secure Events
- `EVENTS_JWT_SECRET` - Chave JWT própria (NUNCA usar a mesma do proxy)
- `FACE_ENGINE` - aws_rekognition ou compreface
- `EVENTS_WEBHOOK_SECRET` - Para assinar webhooks de saída
- `FACE_RETENTION_DAYS` - Dias para auto-delete (LGPD)

## Como Rodar

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar .env com PostgreSQL

# 3. Criar tabelas (automático ao iniciar)

# 4. Criar admin do Secure Events
python seed_events_admin.py

# 5. Rodar servidor
uvicorn app.main:app --reload
```

## Endpoints Secure Events

```
# Auth
POST /secure-events/api/auth/login
POST /secure-events/api/auth/refresh

# Eventos
POST   /secure-events/api/events
GET    /secure-events/api/events
GET    /secure-events/api/events/{id}
PATCH  /secure-events/api/events/{id}/end
DELETE /secure-events/api/events/{id}/faces

# Faces
POST /secure-events/api/events/{id}/faces
GET  /secure-events/api/events/{id}/faces

# Check-in QR
POST /secure-events/api/checkin/validate

# Reconhecimento Facial
POST /secure-events/api/recognize/events/{id}/recognize

# Totens
POST   /secure-events/api/totems
GET    /secure-events/api/totems?event_id={id}
POST   /secure-events/api/totems/{id}/heartbeat
POST   /secure-events/api/totems/{id}/regenerate-key

# Webhooks (entrada do BasileaEvents)
POST /secure-events/api/webhooks/events
POST /secure-events/api/webhooks/events/{id}/faces
```

## Testando

```bash
# Login
curl -X POST http://localhost:8000/secure-events/api/auth/login \
  -d "username=admin@basileia.app&password=TrocarNaPrimeiraVez@2026"

# Listar eventos (com token)
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8000/secure-events/api/events
```

## Deploy

1. Configurar PostgreSQL em produção
2. Configurar AWS Rekognition ou CompreFace
3. Configurar variáveis de ambiente
4. Usar gunicorn + uvicorn workers
5. Configurar nginx com SSL
6. Configurar rate limiting adequado

## Segurança

- JWT separado para cada subsistema
- Rate limiting em todas as rotas sensíveis
- Webhooks assinados com HMAC-SHA256
- Audit log append-only
- Auto-delete de rostos após período de retenção