import os
import subprocess
import sys

def run():
    print("🚀 Iniciando Setup Local...")
    
    try:
        # 1. Instala dependências
        print("📦 Instalando dependências...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except Exception as e:
        print(f"⚠️ Erro ao instalar dependências: {e}")
        print("Tentando continuar assim mesmo...")

    # 2. Roda o Uvicorn
    print("✅ Tudo pronto! O servidor será iniciado em http://127.0.0.1:8000/dashboard")
    local_env = os.environ.copy()
    local_env["DATABASE_URL"] = "sqlite:///./proxy_local.db"
    local_env["REDIS_URL"] = "" # Desabilita Redis para usar memória local
    
    try:
        subprocess.run(["python3", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"], env=local_env)
    except Exception as e:
        print(f"❌ Erro fatal ao iniciar o servidor: {e}")

if __name__ == "__main__":
    run()
