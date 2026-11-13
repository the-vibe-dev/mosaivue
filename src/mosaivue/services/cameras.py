from __future__ import annotations

import logging
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Camera, Credential, Layout, LayoutRevision, RotationGroup, StreamProfile, uuid4
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
        clean_profiles, username, password = self._clean_profiles(
            payload.stream_profiles, payload.username, payload.password
        )

        credential: Credential | None = None
        if username is not None or password is not None:
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
            camera.stream_profiles.append(self._profile_from_input(profile.model_copy(update={"id": None})))
        self.db.flush()
        LOGGER.info("Camera created: %s", camera.name, extra={"camera_id": camera.id})
        return camera

    @staticmethod
    def _clean_profiles(
        profiles: list[StreamProfileIn], username: str | None, password: str | None
    ) -> tuple[list[StreamProfileIn], str | None, str | None]:
        clean_profiles = []
        embedded_users: set[str] = set()
        embedded_passwords: set[str] = set()
        for profile in profiles:
            clean_url, embedded_user, embedded_password = strip_url_credentials(profile.url)
            if embedded_user is not None:
                embedded_users.add(embedded_user)
            if embedded_password is not None:
                embedded_passwords.add(embedded_password)
            clean_profiles.append(profile.model_copy(update={"url": clean_url}))
        if (username is None and len(embedded_users) > 1) or (
            password is None and len(embedded_passwords) > 1
        ):
            raise ValueError("All profiles of a camera must use the same credentials")
        if username is None and embedded_users:
            username = next(iter(embedded_users))
        if password is None and embedded_passwords:
            password = next(iter(embedded_passwords))
        return clean_profiles, username, password

    def _references(self, camera_id: str, profile_ids: set[str] | None = None) -> list[str]:
        references: list[str] = []
        current = self.db.execute(
            select(Layout.name, LayoutRevision.data).join(
                LayoutRevision,
                (LayoutRevision.layout_id == Layout.id)
                & (LayoutRevision.revision == Layout.current_revision),
            )
        )
        for name, data in current:
            for slot in data.get("slots", []):
                if profile_ids is None:
                    used = camera_id in {slot.get("camera_id"), slot.get("selected_camera_id")}
                else:
                    used = slot.get("stream_profile_id") in profile_ids
                if used:
                    references.append(f"layout {name}")
                    break
        for group in self.db.scalars(select(RotationGroup)):
            if any(
                (entry.get("camera_id") == camera_id if profile_ids is None
                 else entry.get("stream_profile_id") in profile_ids)
                for entry in group.camera_entries
            ):
                references.append(f"rotation group {group.name}")
        return references

    def update(self, camera_id: str, payload: CameraUpdate) -> Camera:
        camera = self.get(camera_id)
        data = payload.model_dump(exclude_unset=True)
        data.pop("stream_profiles", None)
        clear_credentials = bool(data.pop("clear_credentials", False))
        username_set = "username" in data
        password_set = "password" in data
        username = data.pop("username", None)
        password = data.pop("password", None)
        profiles = payload.stream_profiles
        replacements: list[tuple[StreamProfileIn, StreamProfile | None]] = []
        removed: list[StreamProfile] = []
        if profiles is not None:
            profiles, embedded_user, embedded_password = self._clean_profiles(
                profiles, username if username_set else None, password if password_set else None
            )
            if not clear_credentials:
                if not username_set and embedded_user is not None:
                    username, username_set = embedded_user, True
                if not password_set and embedded_password is not None:
                    password, password_set = embedded_password, True
            by_id = {profile.id: profile for profile in camera.stream_profiles}
            by_name = {profile.name: profile for profile in camera.stream_profiles}
            kept_ids: set[str] = set()
            for profile in profiles:
                if profile.id is not None and profile.id not in by_id:
                    raise ValueError("Stream profile ID does not belong to this camera")
                existing = by_id.get(profile.id) if profile.id else by_name.get(profile.name)
                if existing is not None:
                    if existing.id in kept_ids:
                        raise ValueError("A stream profile cannot be submitted more than once")
                    kept_ids.add(existing.id)
                replacements.append((profile, existing))
            removed = [profile for profile in camera.stream_profiles if profile.id not in kept_ids]
            references = self._references(camera.id, {profile.id for profile in removed})
            if references:
                raise ValueError("Stream profiles are still used by " + ", ".join(references))

        # Validate references and credentials before mutating any database rows.
        for field, value in data.items():
            setattr(camera, field, value)
        if clear_credentials:
            if camera.credential:
                self.db.delete(camera.credential)
            camera.credential = None
        elif (username_set or password_set) and (
            camera.credential is not None or username is not None or password is not None
        ):
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

        if profiles is not None:
            for profile in removed:
                camera.stream_profiles.remove(profile)
            # Release old unique names before renaming (including a name swap).
            for profile, existing in replacements:
                if existing is not None and profile.name != existing.name:
                    existing.name = f"__update_{uuid4()}"
            self.db.flush()
            for profile, existing in replacements:
                if existing is None:
                    camera.stream_profiles.append(self._profile_from_input(profile.model_copy(update={"id": None})))
                else:
                    for field, value in profile.model_dump(mode="json", exclude={"id"}).items():
                        setattr(existing, field, value)
        self.db.flush()
        LOGGER.info("Camera updated: %s", camera.name, extra={"camera_id": camera.id})
        return camera

    def delete(self, camera_id: str) -> None:
        camera = self.get(camera_id)
        references = self._references(camera.id)
        if references:
            raise ValueError("Camera is still used by " + ", ".join(references))
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
        name = f"{source.name[:250]} Copy"
        counter = 2
        existing_names = {camera.name for camera in self.list()}
        while name in existing_names:
            suffix = f" Copy {counter}"
            name = source.name[:255 - len(suffix)] + suffix
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
        has_password = bool(
            camera.credential
            and self.cipher.decrypt(
                camera.credential.encrypted_secret, context=camera.credential.id
            )
        )
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
            has_password=has_password,
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
