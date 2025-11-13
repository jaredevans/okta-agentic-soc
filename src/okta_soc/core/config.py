import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    okta_org_url: str = os.getenv("OKTA_ORG_URL", "https://example.okta.com")
    okta_api_token: str = os.getenv("OKTA_API_TOKEN", "REPLACE_ME")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://192.168.1.225:1234/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-oss-20b")


def load_settings() -> Settings:
    return Settings()
