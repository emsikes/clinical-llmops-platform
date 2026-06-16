import os
from fastapi import FastAPI, HTTPException, Depends
import redis
import json
from contextlib import asynccontextmanager
from sqlalchemy import select

from models import ChatRequest, ChatResponse, EncounterRequest
from providers import OllamaProvider, OpenAIProvider
from guardrails import ContentSafetyGuard, GuardrailAction, PIIGuard, JailbreakGuard
from database import engine, get_session
from clinical.db_models import Encounter


@asynccontextmanager
async def lifespan(app):
   yield
   await engine.dispose()

app = FastAPI(title="AI Gateway", lifespan=lifespan)

# Connect to Redis using environment variables (with fallback for local dev)
redis_host = os.getenv("APP_REDIS_HOST", "localhost")
redis_port = "6379"
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

def load_settings():
   try:
      with open("/app/config/settings.json", "r") as f:
         return json.load(f)
   except FileNotFoundError:
      return {"provider_models": {}}
   
def load_guardrail_settings():
   """Load content safety settings from ConfigMap"""
   try:
      with open("/app/config/content_safety.json", "r") as f:
         return json.load(f)
   except FileNotFoundError:
      # Default config if file not found (dev mode)
      return {"enabled": False, "categories": {}}
   
def load_pii_settings():
   """Load PII detection settings from ConfigMap"""
   try:
      with open("/app/config/pii_settings.json", "r") as f:
         return json.load(f)
   except FileNotFoundError:
      return {"enabled": False, "pii_types": {}}

settings = load_settings()
guardrail_config = load_guardrail_settings()
content_guard = ContentSafetyGuard(guardrail_config)
pii_config = load_pii_settings()
pii_guard = PIIGuard(pii_config)


# Load guardrail configs from ConfigMap mounted JSON files
def load_jailbreak_settings():
   try:
      with open("/app/config/jailbreak_settings.json", "r") as f:
         return json.load(f)
   except FileNotFoundError:
      return {"enabled": False}
   
jailbreak_config = load_jailbreak_settings()
jailbreak_guard = JailbreakGuard(jailbreak_config)


# Initialize providers with Redis and model prefixes from config within the api-gateway container
providers = {
   "ollama": OllamaProvider(
      redis_client=redis_client,
      model_prefixes=settings.get("provider_models", {}).get("ollama", [])
   ),
   "openai": OpenAIProvider(
      redis_client=redis_client,
      model_prefixes=settings.get("provider_models", {}).get("openai", [])
   )
}

def rank_providers(request: ChatRequest) -> list:
   """
   Rank available providers for the request, best match first.
    
    Returns a list of providers in priority order based on:
        1. Private flag — Ollama only
        2. Explicit provider request — requested first, then fallbacks
        3. Cost ceiling — filter by max_cost if specified
        4. Model support — providers that support the requested model
        5. Fallback — any remaining available providers
   """

   # Private mode - only local inference
   if request.private:
      return [providers["ollama"]]
   
   # Explicit provider - requested first, then fallback
   if hasattr(request, 'provider') and request.provider:
      if request.provider in providers:
         candidates = [providers[request.provider]]
         for name, provider in providers.items():
            if name != request.provider and provider.is_available():
               candidates.append(provider)
         return candidates
      
   # Cost aware ranking.  Filter by budget, sort cheapest first
   provider_costs = settings.get("provider_costs", {})
   candidates = []

   for name, provider in providers.items():
      if not provider.is_available() or not provider.supports_model(request.model):
         continue
      cost = provider_costs.get(name, {}).get("cost_per_1k_tokens", 0.0)
      if request.max_cost is not None and cost > request.max_cost:
         continue
      candidates.append((cost, name, provider))

   # Sort by cost ascending, lowest cost first
   candidates.sort(key=lambda x: x[0])

   if candidates:
      return [provider for _, _, provider in candidates]
   
   # Fallback - return any available providers
   return [p for p in providers.values() if p.is_available()] or [providers["ollama"]]

@app.get("/health")
def health_check():
   return {"status": "healthy", "version": "2.0"}

@app.get("/redis-test")
def redis_test():
   # Send and get value to confirm connectivity
   redis_client.set("test_key", "hello from k8s")
   value = redis_client.get("test_key")
   return {"redis_value": value}   

@app.get("/config")
def get_config():
   return {
      "app_name": os.getenv("APP_NAME", "Unkown"),
      "log_level": os.getenv("LOG_LEVEL", "INFO"),
      "rate_limit_per_minute": os.getenv("RATE_LIMIT_PER_MINUTE", "60")
    } 

@app.get("/providers")
def list_providers():
   """Show which LLM providers and configured"""
   providers = {}

   openai_key = os.getenv("OPENAI_API_KEY", "")
   anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

   providers["openai"] = {
      "configured": len(openai_key) > 0,
      "key_preview": f"{openai_key[:7]}..." if len(openai_key) > 7 else "not set"
   }
   providers["anthropic"] = {
      "configured": len(anthropic_key) > 0,
      "key_preview": f"{anthropic_key[:7]}..." if len(anthropic_key) > 7 else "not set"
   }
   providers["ollama"] = {
      "configured": True,
      "key_preview": "no key required (local)"
   }

   return providers

@app.get("/settings")
def get_settings():
   try:
      with open("/app/config/settings.json", "r") as f:
         settings = json.load(f)
      return settings
   except FileNotFoundError:
      return {"error": "Settings file not found"}
   
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest) -> ChatResponse:
   """OpenAI compatible chat endpoint with intelligent routing"""

   # Guard 1: Content safety check BEFORE sending to a provider
   guard_result = content_guard.evaluate(request)

   if not guard_result.passed:
      if guard_result.action == GuardrailAction.BLOCK:
         raise HTTPException(
            status_code=400,
            detail={
               "error": "Content policy violation",
               "category": guard_result.category.value,
               "message": guard_result.message
            }
         )
      # For WARN / LOG actions, continue but log here

   # Guard 2: PII detection
   pii_result = pii_guard.evaluate(request)
   if not pii_result.passed:
      if pii_result.action == GuardrailAction.BLOCK:
         raise HTTPException(
            status_code=400,
            detail={
               "error": "PII detected",
               "message": pii_result.message
            }
         )
      
   # Handle REDACT - awap in masked text before sending to provider
   if pii_result.action == GuardrailAction.REDACT and pii_result.masked_text:
      for message in reversed(request.messages):
         if message.role == "user" and message.content:
            message.content = pii_result.masked_text
            break

   # Jailbreak detection
   jailbreak_result = jailbreak_guard.evaluate(request)
   if not jailbreak_result.passed:
      if jailbreak_result.action == GuardrailAction.BLOCK:
         raise HTTPException(
            status_code=400,
            detail={
               "error": "Jailbreak attempt detected",
               "message": jailbreak_result.message
            }
         )

   # Try providers in ranked order, fallback on failure
   candidates = rank_providers(request)

   if not candidates:
      raise HTTPException(status_code=503, detail="No provider available")
   
   last_error = None
   for provider in candidates:
      try:
         response = await provider.chat(request)
         return response
      except Exception as e:
         last_error = e
         continue

   raise HTTPException(
      status_code=503,
      detail=f"All providers failed.  Last error: {str(last_error)}"
   )

@app.post("/v1/encounters")
async def create_encounter(request: EncounterRequest, session=Depends(get_session)):
      encounter = Encounter(
         patient_id=request.patient_id,
         specialty=request.specialty,
         provider_npi=request.provider_npi,
         encounter_type=request.encounter_type
      )
      session.add(encounter)
      await session.commit()
      return {"id": str(encounter.id), "status": encounter.status}