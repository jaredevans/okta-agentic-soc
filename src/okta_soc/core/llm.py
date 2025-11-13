from typing import Any, Dict
from openai import OpenAI
import json
import os


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        base_url = base_url or os.getenv("LLM_BASE_URL", "http://192.168.1.225:1234/v1")
        api_key = api_key or os.getenv("LLM_API_KEY", "lm-studio")
        model = model or os.getenv("LLM_MODEL", "gpt-oss-20b")

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        content = self.chat(
            system_prompt,
            user_prompt
            + "\n\nYou MUST respond with ONLY valid JSON. Do not include any explanation.",
            temperature=temperature,
        )
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace != -1:
            content = content[first_brace : last_brace + 1]
        return json.loads(content)
