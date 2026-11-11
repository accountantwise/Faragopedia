# Multi-Provider LLM Integration - Architecture Design

## 1. Background & Motivation
The current `WikiManager` is hardcoded to use OpenAI's `gpt-4o-mini`. To provide flexibility and avoid vendor lock-in, the application needs to support multiple LLM providers (Anthropic, Google/Gemini, OpenAI, and OpenRouter). A configuration-driven approach using environment variables allows users to swap the "brain" of the application without code changes.

## 2. Architecture: LLM Factory Pattern
We will refactor the initialization logic in `backend/agent/wiki_manager.py` to use a factory pattern that instantiates the appropriate LangChain chat model based on environment configuration.

### Configuration Variables (.env)
*   `AI_PROVIDER`: The provider name (choices: `openai`, `anthropic`, `google`, `openrouter`). Default: `openai`.
*   `AI_MODEL`: The specific model ID (e.g., `gpt-4o-mini`, `claude-3-5-sonnet-20240620`, `gemini-1.5-flash`). Default: `gpt-4o-mini`.
*   `OPENAI_API_KEY`: Required for `openai`.
*   `ANTHROPIC_API_KEY`: Required for `anthropic`.
*   `GOOGLE_API_KEY`: Required for `google` (Gemini).
*   `OPENROUTER_API_KEY`: Required for `openrouter`.

## 3. Implementation Details

### Dependency Updates (backend/requirements.txt)
We need to add the provider-specific LangChain packages:
*   `langchain-anthropic`
*   `langchain-google-genai`

### WikiManager Refactoring (backend/agent/wiki_manager.py)
*   Modify `WikiManager.__init__` to call a private `_init_llm()` method.
*   `_init_llm()` will read `AI_PROVIDER` and `AI_MODEL` and return the correctly configured Chat Model instance.
*   **OpenRouter Integration**: Since OpenRouter is OpenAI-compatible, we will use `ChatOpenAI` with a custom `openai_api_base="https://openrouter.ai/api/v1"`.

### Error Handling
*   If `AI_PROVIDER` is set to an unsupported value, the application should raise a clear `ValueError` at startup.
*   Missing API keys for the selected provider will naturally result in errors from the LangChain classes; we will rely on their built-in validation.

## 4. User Experience (Setup)
*   ` .env.example` will be updated to include all new variables with helpful comments.
*   Users switch models by updating `.env` and restarting the Docker stack.

## 5. Deployment
*   The `docker-compose.yml` already passes `env_file: .env` to the backend, so no changes are needed there.
*   The persistence of the Wiki is unaffected by the choice of LLM provider.
