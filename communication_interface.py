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

    def connect(self, host: str, port: int) -> bool:
        self.base_url = f"http://{host}:{port}"
        # Optionally probe health; here we just mark connected
        self._connected = True
        return True

    def is_connected(self) -> bool:
        return self._connected

    def send_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # POST to /normalize; normalizer logs and returns simple text. We ignore body.
        url = f"{self.base_url}/normalize"
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload)
        resp = requests.post(url, headers=headers, data=data, timeout=120)
        resp.raise_for_status()
        # Normalizer doesn't return weights; return a processed to indicate success
        return {"status": "processed"}

    def disconnect(self) -> None:
        self._connected = False


def create_client(protocol: str) -> ICommClient:
    return RestClient()


