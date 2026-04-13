import requests
from typing import Optional, Dict, Any

# Instância global do serviço (para compatibilidade)
uazapi_service = None

def get_uazapi_service(token: str = None):
    """Factory function para criar o serviço"""
    return UazapiService(token)

# Mantém compatibilidade com código existente
class UazapiService:
    def __init__(self, token: str = ""):
        self.token = token
        self.base_url = "https://api.uazapi.com/v1"

    def _headers(self):
        return {"token": self.token, "Content-Type": "application/json"}

    def get_me(self):
        """GET /me - Verifica se a API key é válida"""
        url = f"{self.base_url}/me"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error getting user info: {e}")
            return None

    def list_instances(self):
        """GET /instances - Lista todas as instâncias"""
        url = f"{self.base_url}/instances"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error listing instances: {e}")
            return None

    def get_instance(self, instance_id: str):
        """GET /instance/{id} - Detalhes de uma instância"""
        url = f"{self.base_url}/instance/{instance_id}"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error getting instance: {e}")
            return None

    def set_proxy(self, instance_id: str, proxy_host: str, proxy_port: int, proxy_username: str = None, proxy_password: str = None):
        """
        POST /instance/proxy - Define proxy para uma instância
        
        Args:
            instance_id: ID da instância no Uazapi
            proxy_host: IP do proxy
            proxy_port: Porta do proxy
            proxy_username: usuário do proxy (opcional)
            proxy_password: senha do proxy (opcional)
        """
        url = f"{self.base_url}/instance/proxy"
        payload = {
            "instance": instance_id,
            "enable": True,
            "proxy_url": f"{proxy_host}:{proxy_port}",
            "proxy_auth": True if proxy_username else False
        }
        
        if proxy_username and proxy_password:
            payload["proxy_username"] = proxy_username
            payload["proxy_password"] = proxy_password
            
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            return {"success": response.status_code == 200, "data": response.json()} if response.status_code in [200, 201] else {"success": False, "error": response.text}
        except Exception as e:
            print(f"Error setting proxy: {e}")
            return {"success": False, "error": str(e)}

    def remove_proxy(self, instance_id: str):
        """POST /instance/proxy - Remove proxy de uma instância"""
        url = f"{self.base_url}/instance/proxy"
        payload = {
            "instance": instance_id,
            "enable": False
        }
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            return {"success": response.status_code == 200}
        except Exception as e:
            print(f"Error removing proxy: {e}")
            return {"success": False, "error": str(e)}

    def reconnect(self, instance_id: str):
        """POST /instance/connect - Reconecta a instância"""
        url = f"{self.base_url}/instance/connect"
        payload = {"instance": instance_id}
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            return {"success": response.status_code == 200, "data": response.json()} if response.status_code in [200, 201] else {"success": False}
        except Exception as e:
            print(f"Error reconnecting: {e}")
            return {"success": False, "error": str(e)}

    def get_qrcode(self, instance_id: str):
        """GET /instance/connect - Obter QR Code para conexão"""
        url = f"{self.base_url}/instance/connect?instance={instance_id}"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error getting QR code: {e}")
            return None

    def logout_instance(self, instance_id: str):
        """POST /instance/logout - Desconecta a instância"""
        url = f"{self.base_url}/instance/logout"
        payload = {"instance": instance_id}
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            return {"success": response.status_code == 200}
        except Exception as e:
            print(f"Error logging out: {e}")
            return {"success": False, "error": str(e)}

    def update_client_proxy(self, instance_id: str, proxy_ip: str, proxy_port: int = 3128, proxy_user: str = None, proxy_pass: str = None):
        """
        Atualiza o proxy de um cliente no Uazapi
        Este é o método principal para integração
        """
        result = self.set_proxy(instance_id, proxy_ip, proxy_port, proxy_user, proxy_pass)
        
        if result.get("success"):
            # Reconectar para aplicar o proxy
            self.reconnect(instance_id)
            
        return result


# Funções helper para uso direto
def create_uazapi_service(token: str = None):
    """Factory function para criar o serviço"""
    return UazapiService(token)


def update_client_in_uazapi(instance_id: str, new_proxy_ip: str, token: str, proxy_port: int = 3128):
    """
    Atualiza o proxy de um cliente específico no Uazapi
    
    Args:
        instance_id: ID da instância no Uazapi
        new_proxy_ip: Novo IP do proxy
        token: API Key do Uazapi
        proxy_port: Porta do proxy (default 3128)
    
    Returns:
        dict com success e message
    """
    service = UazapiService(token)
    result = service.update_client_proxy(instance_id, new_proxy_ip, proxy_port)
    
    if result.get("success"):
        return {"success": True, "message": f"Proxy atualizado para {new_proxy_ip}"}
    else:
        return {"success": False, "message": result.get("error", "Erro desconhecido")}


def find_instance_by_phone(phone: str, token: str) -> Optional[str]:
    """
    Busca uma instância pelo número de telefone
    
    Args:
        phone: Número de telefone do cliente
        token: API Key do Uazapi
    
    Returns:
        ID da instância ou None se não encontrar
    """
    service = UazapiService(token)
    instances = service.list_instances()
    
    if instances and isinstance(instances, list):
        for inst in instances:
            # Tentar encontrar pelo número no nome ou número
            inst_number = inst.get("name", "")
            if phone.replace("+55", "") in inst_number.replace("+55", ""):
                return inst.get("id")
    
    return None

# Instância global para compatibilidade
uazapi_service = UazapiService("")