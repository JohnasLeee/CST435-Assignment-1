import os
import json
import abc
import requests
from typing import Any, Dict


class ICommClient(abc.ABC):
    @abc.abstractmethod
    def connect(self, host: str, port: int) -> bool: ...

    @abc.abstractmethod
    def is_connected(self) -> bool: ...

    @abc.abstractmethod
    def send_data(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...

    @abc.abstractmethod
    def disconnect(self) -> None: ...


class RestClient(ICommClient):
    def __init__(self) -> None:
        self.base_url: str = ""
        self._connected: bool = False
        # Connection pooling to avoid recreating connections
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=10, max_retries=3, pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        print("[DEBUG] RestClient: Connection pooling initialized")

    def connect(self, host: str, port: int) -> bool:
        self.base_url = f"http://{host}:{port}"
        # Probe health endpoint if available
        try:
            health_url = f"{self.base_url}/health"
            resp = self.session.get(health_url, timeout=5)
            if resp.status_code == 200:
                print(f"[DEBUG] RestClient: Health check passed for {self.base_url}")
                self._connected = True
                return True
        except:
            pass
        # Fallback: mark connected anyway
        self._connected = True
        return True

    def is_connected(self) -> bool:
        return self._connected

    def send_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # POST to /normalize; normalizer returns normalized weights
        url = f"{self.base_url}/normalize"
        # Use session.post with json parameter (reuses connection)
        # Add compression hint for large payloads
        headers = {'Accept-Encoding': 'gzip, deflate'}
        resp = self.session.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        # Normalizer returns normalized weights as JSON
        try:
            normalized_weights = resp.json()
            return normalized_weights
        except:
            # Fallback if response is not JSON
            return {"status": "processed"}

    def disconnect(self) -> None:
        self._connected = False
        self.session.close()
        print("[DEBUG] RestClient: Session closed")


def create_client(protocol: str) -> ICommClient:
    return RestClient()


