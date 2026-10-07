from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..logging_utils import redact_url
from ..models import Camera, Credential, StreamProfile
from ..schemas import CameraCreate, CameraOut, CameraUpdate, StreamProfileIn, StreamProfileOut
from ..security import CredentialCipher, inject_url_credentials, strip_url_credentials

LOGGER = logging.getLogger(__name__)


class CameraService:
    def __init__(self, db: Session, cipher: CredentialCipher):
        self.db = db
        self.cipher = cipher

    def list(self, *, search: str | None = None, tag: str | None = None) -> list[Camera]:
        statement = select(Camera).order_by(Camera.name)
        cameras = list(self.db.scalars(statement).unique())
        if search:
            needle = search.casefold()
            cameras = [
                camera
                for camera in cameras
                if needle in camera.name.casefold()
                or needle in (camera.description or "").casefold()
                or needle in (camera.location or "").casefold()
            ]
        if tag:
            cameras = [camera for camera in cameras if tag.casefold() in camera.tags]
        return cameras

    def get(self, camera_id: str) -> Camera:
        camera = self.db.get(Camera, camera_id)
        if camera is None:
            raise KeyError("Camera not found")
        return camera

    def create(self, payload: CameraCreate) -> Camera:
        username = payload.username
        password = payload.password
        clean_profiles: list[StreamProfileIn] = []
        for profile in payload.stream_profiles:
            clean_url, embedded_user, embedded_password = strip_url_credentials(profile.url)
            username = username or embedded_user
            password = password if password is not None else embedded_password
            clean_profiles.append(profile.model_copy(update={"url": clean_url}))

        credential: Credential | None = None
        if username or password:
            credential = Credential(username=username, encrypted_secret="")
            self.db.add(credential)
            self.db.flush()
            credential.encrypted_secret = self.cipher.encrypt(password or "", context=credential.id)

        host = payload.host
        if not host and clean_profiles:
            host = urlsplit(clean_profiles[0].url).hostname
        camera = Camera(
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
            vendor=payload.vendor,
            model=payload.model,
            host=host,
            tags=payload.tags,
            location=payload.location,
            credential=credential,
        )
        self.db.add(camera)
        self.db.flush()
        for profile in clean_profiles:
            camera.stream_profiles.append(self._profile_from_input(profile))
        self.db.flush()
        LOGGER.info("Camera created: %s", camera.name, extra={"camera_id": camera.id})
        return camera

    def update(self, camera_id: str, payload: CameraUpdate) -> Camera:
        camera = self.get(camera_id)
        data = payload.model_dump(exclude_unset=True)
        streams = data.pop("stream_profiles", None)
        clear_credentials = bool(data.pop("clear_credentials", False))
        username_set = "username" in data
        password_set = "password" in data
        username = data.pop("username", None)
        password = data.pop("password", None)

        for field, value in data.items():
            setattr(camera, field, value)

        if clear_credentials:
            if camera.credential:
                self.db.delete(camera.credential)
            camera.credential = None
        elif username_set or password_set:
            if camera.credential is None:
                camera.credential = Credential(username=username, encrypted_secret="")
                self.db.add(camera.credential)
                self.db.flush()
                current_password = ""
            else:
                current_password = self.cipher.decrypt(
                    camera.credential.encrypted_secret, context=camera.credential.id
                )
            if username_set:
                camera.credential.username = username
            if password_set:
                current_password = password or ""
            camera.credential.encrypted_secret = self.cipher.encrypt(
                current_password, context=camera.credential.id
            )

        if streams is not None:
            camera.stream_profiles.clear()
            self.db.flush()
            for raw in streams:
                profile = raw if isinstance(raw, StreamProfileIn) else StreamProfileIn.model_validate(raw)
                clean_url, embedded_user, embedded_password = strip_url_credentials(profile.url)
                if embedded_user or embedded_password:
                    if camera.credential is None:
                        camera.credential = Credential(username=embedded_user, encrypted_secret="")
                        self.db.add(camera.credential)
                        self.db.flush()
                    if embedded_user:
                        camera.credential.username = embedded_user
                    camera.credential.encrypted_secret = self.cipher.encrypt(
                        embedded_password or "", context=camera.credential.id
                    )
                profile = profile.model_copy(update={"url": clean_url})
                camera.stream_profiles.append(self._profile_from_input(profile))
        self.db.flush()
        LOGGER.info("Camera updated: %s", camera.name, extra={"camera_id": camera.id})
        return camera

    def delete(self, camera_id: str) -> None:
        camera = self.get(camera_id)
        credential = camera.credential
        self.db.delete(camera)
        self.db.flush()
        if credential is not None:
            self.db.delete(credential)
        LOGGER.info("Camera deleted: %s", camera.name, extra={"camera_id": camera.id})

    def duplicate(self, camera_id: str) -> Camera:
        source = self.get(camera_id)
        credential_username: str | None = None
        credential_password: str | None = None
        if source.credential:
            credential_username = source.credential.username
            credential_password = self.cipher.decrypt(
                source.credential.encrypted_secret, context=source.credential.id
            )
        name = f"{source.name} Copy"
        counter = 2
        existing_names = {camera.name for camera in self.list()}
        while name in existing_names:
            name = f"{source.name} Copy {counter}"
            counter += 1
        payload = CameraCreate(
            name=name,
            description=source.description,
            enabled=False,
            vendor=source.vendor,
            model=source.model,
            host=source.host,
            tags=list(source.tags),
            location=source.location,
            username=credential_username,
            password=credential_password,
            stream_profiles=[
                StreamProfileIn(
                    name=profile.name,
                    url=profile.url,
                    transport=profile.transport,
                    codec=profile.codec,
                    width=profile.width,
                    height=profile.height,
                    fps=profile.fps,
                    bitrate=profile.bitrate,
                    latency_profile=profile.latency_profile,
                    priority=profile.priority,
                )
                for profile in source.stream_profiles
            ],
        )
        return self.create(payload)

    def output(self, camera: Camera) -> CameraOut:
        return CameraOut(
            id=camera.id,
            name=camera.name,
            description=camera.description,
            enabled=camera.enabled,
            vendor=camera.vendor,
            model=camera.model,
            host=camera.host,
            tags=camera.tags,
            location=camera.location,
            username=camera.credential.username if camera.credential else None,
            has_password=bool(camera.credential and camera.credential.encrypted_secret),
            stream_profiles=[StreamProfileOut.model_validate(profile) for profile in camera.stream_profiles],
            created_at=camera.created_at,
            updated_at=camera.updated_at,
        )

    def resolve_stream_url(
        self, camera_id: str, stream_profile_id: str | None = None
    ) -> tuple[Camera, StreamProfile, str]:
        camera = self.get(camera_id)
        if not camera.enabled:
            raise ValueError(f"Camera {camera.name} is disabled")
        profiles = sorted(camera.stream_profiles, key=lambda profile: profile.priority)
        if stream_profile_id:
            profile = next((item for item in profiles if item.id == stream_profile_id), None)
        else:
            profile = profiles[0] if profiles else None
        if profile is None:
            raise ValueError(f"Camera {camera.name} has no matching stream profile")
        username: str | None = None
        password: str | None = None
        if camera.credential:
            username = camera.credential.username
            password = self.cipher.decrypt(camera.credential.encrypted_secret, context=camera.credential.id)
        return camera, profile, inject_url_credentials(profile.url, username, password)

    @staticmethod
    def _profile_from_input(profile: StreamProfileIn) -> StreamProfile:
        return StreamProfile(
            id=profile.id or None,
            name=profile.name,
            url=profile.url,
            transport=profile.transport.value,
            codec=profile.codec,
            width=profile.width,
            height=profile.height,
            fps=profile.fps,
            bitrate=profile.bitrate,
            latency_profile=profile.latency_profile.value,
            priority=profile.priority,
        )
