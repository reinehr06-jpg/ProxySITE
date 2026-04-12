import requests
from app.core.config import settings

class UazapiService:
    def __init__(self, token: str = None):
        self.token = token or settings.UAZAPI_TOKEN
        self.base_url = "https://api.uazapi.com" # Updated based on docs research

    def set_proxy(self, instance_id: str, proxy_url: str):
        """
        POST /instance/proxy
        """
        url = f"{self.base_url}/instance/proxy"
        headers = {"token": self.token}
        payload = {
            "instance": instance_id,
            "enable": True,
            "proxy_url": proxy_url
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error setting proxy on Uazapi: {e}")
            return None

    def get_status(self, instance_id: str):
        """
        GET /instance/status
        """
        url = f"{self.base_url}/instance/status?instance={instance_id}"
        headers = {"token": self.token}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting status from Uazapi: {e}")
            return None

    def reconnect(self, instance_id: str):
        """
        POST /instance/connect or /instance/restart
        """
        url = f"{self.base_url}/instance/connect"
        headers = {"token": self.token}
        payload = {"instance": instance_id}
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error reconnecting on Uazapi: {e}")
            return None

uazapi_service = UazapiService()
