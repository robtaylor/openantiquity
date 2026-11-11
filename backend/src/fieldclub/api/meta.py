"""`GET /meta`: the one place the frontend learns vocabularies and layers."""

from __future__ import annotations

from fastapi import APIRouter

from fieldclub.api.deps import AppSettings, Db, TerrainDep
from fieldclub.schemas.meta import Meta
from fieldclub.services.meta import build_meta

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta)
def get_meta(db: Db, settings: AppSettings, terrain: TerrainDep) -> Meta:
    """Vocabularies, tier definitions, the layer catalogue, sign-in providers and source attributions."""
    return build_meta(db, settings, tile_version=terrain.url_versions())
