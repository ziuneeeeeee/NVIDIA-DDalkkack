from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

try:
    from langsmith import wrappers
    HAS_LANGSMITH = True
except ImportError:
    HAS_LANGSMITH = False


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    load_dotenv()
    client = OpenAI()
    
    if HAS_LANGSMITH:
        # langsmith로 감싸서 모든 OpenAI API 호출을 트레이싱 (환경변수 설정 시 활성화됨)
        client = wrappers.wrap_openai(client)
        
    return client
