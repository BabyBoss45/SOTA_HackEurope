"""
Embedding utilities for SOTA Agents.

Uses sentence-transformers (all-MiniLM-L6-v2) for local, free embeddings.
"""

import asyncio
import os
from typing import Iterable, List

_model = None
_model_name = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_model_name)
    return _model


async def embed_text(text: str, model: str | None = None) -> List[float]:
    """Embed a single text string."""
    embeddings = await embed_texts([text], model=model)
    return embeddings[0]


async def embed_texts(texts: Iterable[str], model: str | None = None) -> List[List[float]]:
    """Embed multiple texts and return vectors."""
    text_list = list(texts)
    loop = asyncio.get_event_loop()
    st_model = _get_model()
    vectors = await loop.run_in_executor(None, lambda: st_model.encode(text_list).tolist())
    return vectors
