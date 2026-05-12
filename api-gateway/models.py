from pydantic import BaseModel
from typing import Optional, Literal


# OpenAI compatible request format
class ChatMessage(BaseModel):
   role: str
   content: str


class ChatRequest(BaseModel):
   model: str
   messages: list[ChatMessage]
   temperature: Optional[float] = 0.7
   max_tokens: Optional[int] = 1000
   private: Optional[bool] = False
   max_cost: Optional[float] = None
   provider: Optional[str] = None


class ChatChoice(BaseModel):
   index: int
   message: ChatMessage
   finish_reason: str # "stop", "length", or "error"


class Usage(BaseModel):
   prompt_tokens: int
   completion_tokens: int
   total_tokens: int


class ChatResponse(BaseModel):
   id: str                                   # Unique response ID
   object: Literal["chat.completion"]        # Always use this value (OpenAI chat completion convention)
   created: int                              # Unix timestamp
   model: str                                # Which model actually responded
   provider: str                             # Custom field: "ollama", "openai", "bedrock", etc.
   choices: list[ChatChoice]                 # List of responses
   usage: Optional[Usage] = None             # Token count for cost tracking

