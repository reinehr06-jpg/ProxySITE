from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import routes_clients, routes_dispatch
from app.core.database import engine, Base
import threading
import time
from app.jobs.monitor_proxies import run_monitoring_loop

# Initialize database
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Proxy Microservice")

# Routes
app.include_router(routes_clients.router, prefix="/api", tags=["clients"])
app.include_router(routes_dispatch.router, prefix="/api", tags=["dispatch"])

# Static Files (Dashboard)
app.mount("/dashboard", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
async def root():
    return {"message": "Proxy Microservice API is running. Go to /dashboard for UI."}

# Start Background Monitoring Job
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=run_monitoring_loop, daemon=True)
    thread.start()
