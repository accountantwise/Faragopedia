import os
import pytest
from unittest.mock import patch
from backend.agent.wiki_manager import WikiManager, _LLMProxy
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

def test_init_llm_openai():
    with patch.dict(os.environ, {"AI_PROVIDER": "openai", "AI_MODEL": "gpt-4o-mini", "OPENAI_API_KEY": "test_key"}):
        wm = WikiManager()
        assert isinstance(wm.llm, _LLMProxy)
        assert isinstance(wm.llm._llm, ChatOpenAI)
        assert wm.llm.model_name == "gpt-4o-mini"

def test_init_llm_anthropic():
    with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "AI_MODEL": "claude-3-5-sonnet-20240620", "ANTHROPIC_API_KEY": "test_key"}):
        wm = WikiManager()
        assert isinstance(wm.llm, _LLMProxy)
        assert isinstance(wm.llm._llm, ChatAnthropic)
        assert wm.llm.model == "claude-3-5-sonnet-20240620"

def test_init_llm_google():
    with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_MODEL": "gemini-1.5-pro", "GOOGLE_API_KEY": "test_key"}):
        wm = WikiManager()
        assert isinstance(wm.llm, _LLMProxy)
        assert isinstance(wm.llm._llm, ChatGoogleGenerativeAI)
        assert wm.llm.model == "gemini-1.5-pro"

def test_init_llm_openrouter():
    with patch.dict(os.environ, {"AI_PROVIDER": "openrouter", "AI_MODEL": "meta-llama/llama-3-70b-instruct", "OPENROUTER_API_KEY": "test_key"}):
        wm = WikiManager()
        assert isinstance(wm.llm, _LLMProxy)
        assert isinstance(wm.llm._llm, ChatOpenAI)
        assert wm.llm.openai_api_base == "https://openrouter.ai/api/v1"
        assert wm.llm.model_name == "meta-llama/llama-3-70b-instruct"

def test_init_llm_invalid():
    with patch.dict(os.environ, {"AI_PROVIDER": "invalid"}):
        with pytest.raises(ValueError, match="Unsupported AI provider: invalid"):
            WikiManager()

def test_init_llm_default():
    # Clear environment variables to test defaults
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}, clear=True):
        wm = WikiManager()
        assert isinstance(wm.llm, _LLMProxy)
        assert isinstance(wm.llm._llm, ChatOpenAI)
        assert wm.llm.model_name == "gpt-4o-mini"
