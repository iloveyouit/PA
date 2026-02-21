"""
Shared configuration loader for the PA agent stack.
Loads environment variables from .env and provides typed access.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


def get_required(key: str) -> str:
    """Get a required env var or raise with a helpful message."""
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Copy .env.example to .env and fill it in."
        )
    return val


def get_optional(key: str, default: str = "") -> str:
    """Get an optional env var with a fallback."""
    return os.getenv(key, default).strip() or default


# --- Pre-loaded config accessors ---

def anthropic_key() -> str:
    return get_required("ANTHROPIC_API_KEY")

def openai_key() -> str:
    return get_required("OPENAI_API_KEY")

def openrouter_key() -> str:
    return get_required("OPENROUTER_API_KEY")

def perplexity_key() -> str:
    return get_required("PERPLEXITY_API_KEY")

def pinecone_key() -> str:
    return get_required("PINECONE_API_KEY")

def pinecone_index() -> str:
    return get_optional("PINECONE_INDEX_NAME", "pa-memory")

def e2b_key() -> str:
    return get_required("E2B_API_KEY")

def langfuse_public_key() -> str:
    return get_optional("LANGFUSE_PUBLIC_KEY")

def langfuse_secret_key() -> str:
    return get_optional("LANGFUSE_SECRET_KEY")

def langfuse_host() -> str:
    return get_optional("LANGFUSE_HOST", "https://cloud.langfuse.com")

def embedding_model() -> str:
    return get_optional("EMBEDDING_MODEL", "text-embedding-3-small")
