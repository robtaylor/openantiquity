"""`GET /meta`: the one place the frontend learns vocabularies and layers."""

from __future__ import annotations

from fastapi import APIRouter

from fieldclub.api.deps import AppSettings, Db
from fieldclub.schemas.meta import Meta
from fieldclub.services.meta import build_meta

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta)
def get_meta(db: Db, settings: AppSettings) -> Meta:
    """Vocabularies, tier definitions, the layer catalogue, sign-in providers and source attributions."""
    return build_meta(db, settings)
