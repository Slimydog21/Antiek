"""Normal-account audio settings. Registration and HTTP never grant a paid send."""

from __future__ import annotations

import json
import os
import stat
import threading
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from interfaces.research.api.settings_audio_models import (
    AudioModelService,
    AudioModelUnavailable,
    AudioPublicationError,
    _owner,
)
from runtime.byok import store
from runtime.research_runner.audio_provider_catalog import AUDIO_MODEL_CATALOG
from substrate.byot_usage.actions import checked_int

_PREFIX = "/settings/audio-models"
_BODY_LIMIT = 8192
_ARTIFACT_LIMIT = 1_048_576
_CACHE_HEADERS = {"Cache-Control": "private, no-store"}


@dataclass(frozen=True, repr=False)
class AudioBindingPaths:
    """Server-owned injection; never read from request fields or headers."""

    state_root: Path
    artifact: Path
    key_file: Path


def _server_paths() -> AudioBindingPaths:
    configured = os.environ.get("ANTIEK_HOME")
    root = Path(configured).expanduser() if configured else Path.home() / ".antiek"
    return AudioBindingPaths(
        root,
        Path(store._default_artifact_path()),
        Path(store._default_key_file()),
    )


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


@contextmanager
def _private_directory(path: Path) -> Iterator[int]:
    if not path.is_absolute() or ".." in path.parts:
        raise AudioModelUnavailable("audio binding unavailable")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise AudioModelUnavailable("audio binding unavailable")
        yield fd
    finally:
        os.close(fd)


def _private_file(info: os.stat_result) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise AudioModelUnavailable("audio binding unavailable")


def _file_identity(path: Path, *, key: bool = False) -> tuple[int, ...]:
    with _private_directory(path.parent) as directory:
        info = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        _private_file(info)
        if key and info.st_size != 32:
            raise AudioModelUnavailable("audio binding unavailable")
        return _identity(info)


def _admit_lock(path: Path) -> None:
    lock = path.with_name(path.name + ".lock")
    with suppress(FileNotFoundError):
        _file_identity(lock)
    # The existing store owns lock creation in the admitted private parent.


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _constant(_value: str) -> object:
    raise ValueError("nonfinite value")


def _admit_artifact(path: Path) -> None:
    with _private_directory(path.parent) as directory:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            _private_file(before)
            if before.st_size > _ARTIFACT_LIMIT:
                raise AudioModelUnavailable("audio binding unavailable")
            remaining = before.st_size
            raw = bytearray()
            while remaining:
                chunk = os.read(fd, min(remaining, 65_536))
                if not chunk:
                    raise AudioModelUnavailable("audio binding unavailable")
                raw.extend(chunk)
                remaining -= len(chunk)
            if (
                os.read(fd, 1)
                or _identity(before) != _identity(os.fstat(fd))
                or _identity(before)
                != _identity(os.stat(path.name, dir_fd=directory, follow_symlinks=False))
            ):
                raise AudioModelUnavailable("audio binding unavailable")
        finally:
            os.close(fd)
    data: object = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(data, dict):
        raise AudioModelUnavailable("audio binding unavailable")
    for credential_id, row in data.items():
        if (
            not isinstance(row, dict)
            or row.get("cred_id") != credential_id
            or not isinstance(row.get("account_handle"), str)
            or not isinstance(row.get("ciphertext_hex"), str)
            or type(row.get("binding_version", 1)) is not int
            or row.get("binding_version", 1) not in (1, 2, 3)
            or (row.get("pipeline_kind") is not None and not isinstance(row["pipeline_kind"], str))
            or (row.get("owner_user_id") is not None and not isinstance(row["owner_user_id"], str))
        ):
            raise AudioModelUnavailable("audio binding unavailable")
        if len(bytes.fromhex(row["ciphertext_hex"])) < 40:
            raise AudioModelUnavailable("audio binding unavailable")


def _admit_account(request: Request) -> str:
    owner = _owner(request)
    if "operator" in getattr(request.state, "scopes", ()):
        raise HTTPException(401, "canonical normal account required")
    return owner


class _AppAudioBinding:
    def __init__(self, paths: AudioBindingPaths | None) -> None:
        self._paths = paths
        self._lock = threading.RLock()
        self._service: AudioModelService | None = None
        self._artifact_identity: tuple[int, ...] | None = None
        self._invalidated = False
        self._stamp: (
            tuple[AudioBindingPaths, tuple[int, ...], tuple[int, ...], tuple[int, ...], bytes]
            | None
        ) = None

    def _retire(self) -> None:
        if self._service is not None:
            self._invalidated = True
            with self._service._registration_lock:
                self._service._registrations.clear()
        self._service = None
        self._stamp = None
        self._artifact_identity = None

    def perform[T](self, request: Request, action: Callable[[AudioModelService], T]) -> T:
        _admit_account(request)
        with self._lock:
            if self._invalidated:
                raise AudioModelUnavailable("audio binding unavailable")
            try:
                paths = self._paths or _server_paths()
                with _private_directory(paths.state_root) as directory:
                    root = os.fstat(directory)
                    root_identity = (root.st_dev, root.st_ino)
                _admit_artifact(paths.artifact)
                artifact_file = _file_identity(paths.artifact)
                if self._service is not None and artifact_file != self._artifact_identity:
                    raise AudioModelUnavailable("audio binding unavailable")
                with _private_directory(paths.artifact.parent) as directory:
                    artifact_parent = os.fstat(directory)
                    artifact_identity = (artifact_parent.st_dev, artifact_parent.st_ino)
                _admit_lock(paths.artifact)
                key_identity = _file_identity(paths.key_file, key=True)
                _admit_lock(paths.key_file)
                key = store.prepare_current_master_key(key_file=str(paths.key_file))
                if key_identity != _file_identity(paths.key_file, key=True):
                    raise AudioModelUnavailable("audio binding unavailable")
                stamp = (paths, root_identity, artifact_identity, key_identity, key)
                if stamp != self._stamp:
                    if self._stamp is not None:
                        self._retire()
                        raise AudioModelUnavailable("audio binding unavailable")
                    self._retire()
                    self._service = AudioModelService(
                        state_root=paths.state_root,
                        prepared_master_key=key,
                        artifact_path=paths.artifact,
                    )
                    self._stamp = stamp
                    self._artifact_identity = artifact_file
                assert self._service is not None
            except Exception:
                self._retire()
                raise
            try:
                result = action(self._service)
            except Exception:
                # Preserve the primary service refusal/publication failure.
                # A failed mutation cannot refresh authority to a changed vault.
                try:
                    if artifact_file != _file_identity(paths.artifact):
                        self._retire()
                except Exception:
                    self._retire()
                raise
            try:
                _admit_artifact(paths.artifact)
                if key_identity != _file_identity(paths.key_file, key=True):
                    raise AudioModelUnavailable("audio binding unavailable")
                self._artifact_identity = _file_identity(paths.artifact)
            except Exception:
                self._retire()
                raise
            return result


async def _body(request: Request) -> dict[str, object]:
    raw = bytearray()
    async for chunk in request.stream():
        if len(chunk) > _BODY_LIMIT - len(raw):
            raise HTTPException(413, "audio settings request too large")
        raw.extend(chunk)
    try:
        data: object = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(data, dict):
            raise ValueError("object required")
    except ValueError:
        raise HTTPException(422, "invalid audio settings request") from None
    return data


def _create_payload(payload: dict[str, object]) -> None:
    key, display = payload.get("api_key"), payload.get("display_name")
    if (
        set(payload) != {"catalog_id", "model_id", "endpoint", "display_name", "api_key"}
        or payload.get("catalog_id") != "openai"
        or payload.get("model_id") != "whisper-1"
        or payload.get("endpoint") != "https://api.openai.com"
        or not isinstance(key, str)
        or not 8 <= len(key) <= 512
        or not isinstance(display, str)
        or not 1 <= len(display) <= 64
        or key in display
        or key in "https://api.openai.com whisper-1 openai"
    ):
        raise HTTPException(422, "invalid audio settings request")


async def _operation(
    binding: _AppAudioBinding,
    request: Request,
    action: Callable[[AudioModelService], object],
    *,
    status_code: int = 200,
) -> Response:
    try:
        result = await run_in_threadpool(binding.perform, request, action)
    except AudioPublicationError as exc:
        return JSONResponse(
            {
                "detail": "audio publication unconfirmed",
                "credential_cleanup_confirmed": exc.cleanup_confirmed,
            },
            status_code=409,
            headers=_CACHE_HEADERS,
        )
    except AudioModelUnavailable as exc:
        code = 404 if exc.args == ("audio record unavailable",) else 503
        return JSONResponse(
            {"detail": "audio model unavailable"}, status_code=code, headers=_CACHE_HEADERS
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
    ):
        return JSONResponse(
            {"detail": "audio models unavailable"}, status_code=503, headers=_CACHE_HEADERS
        )
    if status_code == 204:
        return Response(status_code=204, headers=_CACHE_HEADERS)
    return JSONResponse(result, status_code=status_code, headers=_CACHE_HEADERS)


def _budget_limit(payload: dict[str, object]) -> int:
    try:
        if set(payload) != {"limit_cents"}:
            raise ValueError("exact budget required")
        return checked_int(payload["limit_cents"])
    except ValueError:
        raise HTTPException(422, "invalid audio budget request") from None


async def _budget_operation(
    binding: _AppAudioBinding,
    request: Request,
    record_id: str,
    *,
    limit_cents: int | None = None,
) -> Response:
    mutation_started = False

    def action(service: AudioModelService) -> dict[str, object]:
        def started() -> None:
            nonlocal mutation_started
            mutation_started = True

        if limit_cents is None:
            return service.get_budget(request, record_id)
        return service.set_budget(request, record_id, limit_cents, on_mutation_started=started)

    try:
        result = await run_in_threadpool(binding.perform, request, action)
    except Exception as exc:
        if mutation_started:
            return JSONResponse(
                {"detail": "audio budget mutation unconfirmed", "mutation_confirmed": False},
                status_code=503,
                headers=_CACHE_HEADERS,
            )
        code = (
            404
            if isinstance(exc, AudioModelUnavailable) and exc.args == ("audio record unavailable",)
            else 503
        )
        return JSONResponse(
            {"detail": "audio budget unavailable"}, status_code=code, headers=_CACHE_HEADERS
        )
    return JSONResponse(result, headers=_CACHE_HEADERS)


def register_settings_audio_model_routes(
    app: FastAPI, *, binding_paths: AudioBindingPaths | None = None
) -> None:
    """Mount without private I/O. Only trusted server code can inject paths."""
    binding = _AppAudioBinding(binding_paths)
    app.state.audio_model_binding = binding
    router = APIRouter(prefix=_PREFIX, tags=["settings"])

    @app.middleware("http")
    async def _private_cache(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path == _PREFIX or request.url.path.startswith(_PREFIX + "/"):
            response.headers.update(_CACHE_HEADERS)
        return response

    @router.get("/catalog")
    def catalog(request: Request) -> Response:
        _admit_account(request)
        return JSONResponse(
            {"models": [asdict(row) for row in AUDIO_MODEL_CATALOG]}, headers=_CACHE_HEADERS
        )

    @router.get("/user")
    async def user_models(request: Request) -> Response:
        _admit_account(request)
        return await _operation(binding, request, lambda service: {"models": service.list(request)})

    @router.post("/user")
    async def create(request: Request) -> Response:
        _admit_account(request)
        payload = await _body(request)
        _create_payload(payload)
        return await _operation(
            binding, request, lambda service: service.create(request, payload), status_code=201
        )

    @router.patch("/user/{record_id}")
    async def disable(request: Request, record_id: str) -> Response:
        _admit_account(request)
        payload = await _body(request)
        if set(payload) != {"enabled"} or payload["enabled"] is not False:
            raise HTTPException(422, "disable-only audio settings request required")
        return await _operation(
            binding, request, lambda service: service.disable(request, record_id), status_code=204
        )

    @router.delete("/user/{record_id}")
    async def delete(request: Request, record_id: str) -> Response:
        _admit_account(request)
        return await _operation(
            binding,
            request,
            lambda service: {"credential_removed": service.delete(request, record_id)},
        )

    @router.get("/user/{record_id}/budget")
    async def get_budget(request: Request, record_id: str) -> Response:
        _admit_account(request)
        return await _budget_operation(binding, request, record_id)

    @router.put("/user/{record_id}/budget")
    async def put_budget(request: Request, record_id: str) -> Response:
        _admit_account(request)
        limit = _budget_limit(await _body(request))
        return await _budget_operation(binding, request, record_id, limit_cents=limit)

    app.include_router(router)
