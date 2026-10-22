"""
Meridian AI harness - FastAPI service that pulls its secrets from OpenBao.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000

The critical property: there is NO api key in this file, in the Dockerfile,
or in the environment. The key arrives from OpenBao at startup and lives
only in process memory.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from openbao_client import OpenBaoClient, OpenBaoError, get_gemini_credentials

logging.basicConfig(
    level=os.getenv("APP_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("meridian.ai-harness")

# Process-wide client and the secrets fetched at startup.
bao_client: OpenBaoClient | None = None
_credentials: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fetch secrets from OpenBao before serving traffic.

    If this fails, the app must NOT start. A degraded AI harness that
    silently lacks an API key is worse than one that refuses to boot.
    """
    global bao_client, _credentials

    bao_client = OpenBaoClient()
    logger.info("Connecting to OpenBao at %s", bao_client.addr)

    try:
        _credentials = get_gemini_credentials(bao_client)
    except OpenBaoError as exc:
        logger.error("FATAL: could not obtain secrets from OpenBao: %s", exc)
        raise

    # Never log the key itself. Log only enough to confirm which version we got.
    logger.info("Loaded Gemini credentials (version from OpenBao metadata)")
    logger.info("Model: %s | Project: %s", _credentials.get("model"),
                _credentials.get("project_id"))
    yield
    if bao_client:
        bao_client.close()


app = FastAPI(
    title="Meridian AI Harness",
    version="1.0.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    status: str
    openbao_initialized: bool
    openbao_sealed: bool
    secrets_loaded: bool
    gemini_model: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + readiness.

    Reports OpenBao's own seal state. If OpenBao is sealed, the harness
    cannot fetch or renew secrets, so it should be pulled from the LB.
    """
    if bao_client is None:
        raise HTTPException(status_code=503, detail="OpenBao client not initialised")

    health_data = bao_client.health()
    return HealthResponse(
        status="ok" if health_data.get("initialized") and not health_data.get("sealed") else "degraded",
        openbao_initialized=bool(health_data.get("initialized")),
        openbao_sealed=bool(health_data.get("sealed")),
        secrets_loaded=bool(_credentials.get("api_key")),
        gemini_model=_credentials.get("model", ""),
    )


class ChatRequest(BaseModel):
    prompt: str
    model: str | None = None


@app.post("/v1/chat")
def chat(req: ChatRequest) -> dict:
    """Stub for the real LangChain call.

    The real implementation would use `google.generativeai` / LangChain's
    ChatGoogleGenerativeAI with `google_api_key=_credentials["api_key"]`.
    We keep the key in a module-global so it never touches a log line.
    """
    if not _credentials.get("api_key"):
        raise HTTPException(status_code=503, detail="Gemini credentials not loaded")

    # ---- The actual LangChain integration would look like: ----
    #
    # from langchain_google_genai import ChatGoogleGenerativeAI
    # llm = ChatGoogleGenerativeAI(
    #     model=req.model or _credentials["model"],
    #     google_api_key=_credentials["api_key"],   # <- from OpenBao
    # )
    # return {"answer": llm.invoke(req.prompt).content}

    return {
        "model": req.model or _credentials.get("model"),
        "answer": (
            "The Gemini key was retrieved from OpenBao and is present in memory. "
            "The real LangChain call is intentionally stubbed in the lab."
        ),
        "key_prefix": _credentials["api_key"][:6] + "...",
    }


def get_bao() -> OpenBaoClient:
    if bao_client is None:
        raise HTTPException(status_code=503, detail="OpenBao client not initialised")
    return bao_client


@app.get("/v1/secrets/gemini")
def read_gemini_secret(client: OpenBaoClient = Depends(get_bao)) -> dict:
    """Read the secret on demand.

    Demonstrates the runtime read path used by rotating credentials.
    In production you would usually NOT expose this endpoint; it exists so
    the course can prove the read works from inside the container.
    """
    lease = client.read_secret("ai/platform", "llm/gemini")
    return {
        "version": lease.version,
        "created_time": lease.created_time,
        "model": lease.value.get("model"),
        "project_id": lease.value.get("project_id"),
        # The key itself is deliberately NOT returned.
        "api_key_present": bool(lease.value.get("api_key")),
    }
