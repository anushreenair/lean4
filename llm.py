"""Explanation layer: deterministic by default, optional OpenAI-compatible provider."""

from abc import ABC, abstractmethod
import json
import os
from urllib.request import Request, urlopen

from docs_index import SearchResult
from term_analyzer import QueryAnalysis


class ExplanationProvider(ABC):
    # A shared interface lets local and remote explanation strategies be swapped safely.
    @abstractmethod
    def explain(self, query: str, documents: list[SearchResult], coverage: QueryAnalysis) -> str:
        raise NotImplementedError


class ExtractiveExplanationProvider(ExplanationProvider):
    def explain(self, query: str, documents: list[SearchResult], coverage: QueryAnalysis) -> str:
        # Extractive output is deterministic and keeps the script useful without an API key.
        if not documents:
            return (
                "I could not find a relevant cached passage in the official Lean documentation. "
                "Try refreshing the documentation index and ask again."
            )
        best = documents[0]
        return f"In simple terms: {best.text.strip()}"


class OpenAIExplanationProvider(ExplanationProvider):
    """Minimal optional provider; the agent still falls back if the call fails."""

    def __init__(self, api_key: str, model: str, endpoint: str, timeout: float = 30):
        self.api_key, self.model, self.endpoint, self.timeout = api_key, model, endpoint, timeout

    def explain(self, query: str, documents: list[SearchResult], coverage: QueryAnalysis) -> str:
        # Only retrieved documentation and the user's question are sent to the provider.
        context = "\n\n".join(f"[{doc.title}] {doc.text}" for doc in documents[:5])
        prompt = (
            "Answer the Lean question simply and only from the official documentation context. "
            "If context is insufficient, say so.\n\nQuestion: " + query + "\n\nContext:\n" + context
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode())
        return data["choices"][0]["message"]["content"].strip()


def provider_from_environment() -> ExplanationProvider | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        # Returning None deliberately selects the local fallback in the agent.
        return None
    return OpenAIExplanationProvider(
        key,
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
    )
