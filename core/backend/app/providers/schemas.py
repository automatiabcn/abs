"""Provider yanıt şemaları."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProviderResponse(BaseModel):
    """Bir provider çağrısının normalize yanıtı."""

    text: str = Field(default="", description="Modelin döndürdüğü metin")
    model: str = Field(default="", description="Kullanılan model adı")
    provider: str = Field(default="", description="Provider adı (groq, gemini, …)")
    elapsed_ms: int = Field(default=0, description="İsteğin bitiş süresi (ms)")
    tokens_in: Optional[int] = Field(default=None, description="Prompt token sayısı")
    tokens_out: Optional[int] = Field(default=None, description="Yanıt token sayısı")
    cached: bool = Field(default=False, description="Semantic cache'ten mi döndü")
    error: Optional[str] = Field(default=None, description="Hata mesajı (varsa)")


class ProviderError(Exception):
    """Provider çağrısı başarısız — caller cascade için yakalar."""

    def __init__(self, message: str, provider: str = "", transient: bool = True):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.transient = transient
