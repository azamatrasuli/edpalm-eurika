from __future__ import annotations

from fastapi import HTTPException, status

import hashlib

from app.auth.external import ExternalLinkAuth
from app.auth.portal import PortalAuth
from app.auth.telegram import TelegramAuth
from app.config import get_settings
from app.models.chat import ActorContext, AuthPayload, Channel


class AuthService:
    def __init__(self) -> None:
        self.portal_auth = PortalAuth()
        self.telegram_auth = TelegramAuth()
        self.external_auth = ExternalLinkAuth()

    def resolve(self, auth: AuthPayload) -> ActorContext:
        # Manager auth — separate check, takes priority
        if auth.manager_key:
            return self._resolve_manager(auth.manager_key)

        provided = [
            bool(auth.portal_token),
            bool(auth.telegram_init_data),
            bool(auth.external_token),
            bool(auth.guest_id),
        ]
        if sum(provided) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ошибка аутентификации. Обновите страницу и попробуйте снова.",
            )

        if auth.portal_token:
            return self.portal_auth.resolve(auth.portal_token)
        if auth.telegram_init_data:
            return self.telegram_auth.resolve(auth.telegram_init_data)
        if auth.external_token:
            return self.external_auth.resolve(auth.external_token)
        if auth.guest_id:
            return ActorContext(
                channel=Channel.guest,
                actor_id=f"guest:{auth.guest_id}",
                display_name=None,
                phone=None,
                metadata={},
            )

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ошибка аутентификации. Обновите страницу и попробуйте снова.")

    def _resolve_manager(self, manager_key: str) -> ActorContext:
        """Authenticate manager by dashboard API key."""
        settings = get_settings()
        if not settings.dashboard_api_key or manager_key != settings.dashboard_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный ключ менеджера.",
            )
        key_hash = hashlib.sha256(manager_key.encode()).hexdigest()[:12]
        return ActorContext(
            channel=Channel.manager,
            actor_id=f"manager:{key_hash}",
            display_name="Менеджер",
            phone=None,
            metadata={"is_manager": True},
        )
