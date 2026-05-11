import json
import threading
from typing import Any, Dict, List, Optional

import requests


class OllamaError(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def is_available(self) -> bool:
        try:
            response = self._session.get(
                f"{self.base_url}/api/tags",
                timeout=3,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> List[str]:
        try:
            response = self._session.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            return [m.get("name", m.get("model", "")) for m in models if m.get("name") or m.get("model")]
        except requests.RequestException as exc:
            raise OllamaError(f"无法连接到 Ollama 服务器: {exc}")
        except (json.JSONDecodeError, KeyError) as exc:
            raise OllamaError(f"解析模型列表失败: {exc}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        try:
            response = self._session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            if "message" in data and "content" in data["message"]:
                return data["message"]["content"]
            if "response" in data:
                return data["response"]
            return ""
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise OllamaError(f"模型 '{self.model}' 不存在，请先拉取该模型")
            raise OllamaError(f"请求失败: {exc}")
        except requests.RequestException as exc:
            raise OllamaError(f"无法连接到 Ollama 服务器: {exc}")
        except (json.JSONDecodeError, KeyError) as exc:
            raise OllamaError(f"解析响应失败: {exc}")

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        try:
            response = self._session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise OllamaError(f"模型 '{self.model}' 不存在，请先拉取该模型")
            raise OllamaError(f"请求失败: {exc}")
        except requests.RequestException as exc:
            raise OllamaError(f"无法连接到 Ollama 服务器: {exc}")
        except (json.JSONDecodeError, KeyError) as exc:
            raise OllamaError(f"解析响应失败: {exc}")


class OllamaWorker(threading.Thread):
    def __init__(
        self,
        client: OllamaClient,
        mode: str,
        callback: callable,
        error_callback: callable,
        messages: Optional[List[Dict[str, str]]] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.7,
    ):
        super().__init__(daemon=True)
        self.client = client
        self.mode = mode
        self.callback = callback
        self.error_callback = error_callback
        self.messages = messages
        self.prompt = prompt
        self.temperature = temperature

    def run(self):
        try:
            if self.mode == "chat" and self.messages is not None:
                result = self.client.chat(self.messages, self.temperature)
            elif self.mode == "generate" and self.prompt is not None:
                result = self.client.generate(self.prompt, self.temperature)
            else:
                raise OllamaError("无效的工作模式或缺少参数")
            self.callback(result)
        except OllamaError as exc:
            self.error_callback(str(exc))
        except Exception as exc:
            self.error_callback(f"未知错误: {exc}")
