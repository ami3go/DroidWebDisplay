from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status

from droid_web_display.profiles import (
    ConnectionProfileInput,
    ConnectionProfileStore,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileStoreError,
)


def _store(request: Request) -> ConnectionProfileStore:
    return request.app.state.connection_profile_store


def _profile_json(value) -> dict[str, Any]:
    return value.model_dump(by_alias=True, mode="json")


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProfileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ProfileConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ProfileStoreError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail="Connection profile operation failed")


def install_profiles_api(app: FastAPI) -> FastAPI:
    """Install authenticated named connection-profile persistence endpoints."""

    container = app.state.container
    store = ConnectionProfileStore(container.config.resolved_transfer_data_directory / "connection-profiles.json")
    app.state.connection_profile_store = store

    @app.get("/api/v1/profiles")
    async def list_profiles(request: Request) -> dict[str, Any]:
        try:
            document = _store(request).list()
        except Exception as exc:
            raise _translate_error(exc) from exc
        return {
            "schemaVersion": document.schema_version,
            "defaultProfileId": document.default_profile_id,
            "profiles": [_profile_json(profile) for profile in document.profiles],
        }

    @app.delete("/api/v1/profiles/default", status_code=status.HTTP_204_NO_CONTENT)
    async def clear_default_profile(request: Request) -> Response:
        try:
            _store(request).set_default(None)
        except Exception as exc:
            raise _translate_error(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/profiles/{profile_id}")
    async def get_profile(profile_id: str, request: Request) -> dict[str, Any]:
        try:
            return _profile_json(_store(request).get(profile_id))
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/v1/profiles", status_code=status.HTTP_201_CREATED)
    async def create_profile(body: ConnectionProfileInput, request: Request) -> dict[str, Any]:
        try:
            return _profile_json(_store(request).create(body))
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.put("/api/v1/profiles/{profile_id}")
    async def update_profile(profile_id: str, body: ConnectionProfileInput, request: Request) -> dict[str, Any]:
        try:
            return _profile_json(_store(request).update(profile_id, body))
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.delete("/api/v1/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_profile(profile_id: str, request: Request) -> Response:
        try:
            _store(request).delete(profile_id)
        except Exception as exc:
            raise _translate_error(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.put("/api/v1/profiles/{profile_id}/default")
    async def set_default_profile(profile_id: str, request: Request) -> dict[str, Any]:
        try:
            selected = _store(request).set_default(profile_id)
        except Exception as exc:
            raise _translate_error(exc) from exc
        return {"defaultProfileId": selected}

    @app.post("/api/v1/profiles/{profile_id}/used")
    async def mark_profile_used(profile_id: str, request: Request) -> dict[str, Any]:
        try:
            return _profile_json(_store(request).mark_used(profile_id))
        except Exception as exc:
            raise _translate_error(exc) from exc

    return app
