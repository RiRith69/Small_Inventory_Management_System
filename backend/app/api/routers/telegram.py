"""Telegram linking from the website ("Link Telegram" in the profile page).

Workflow
--------
1. The signed-in user clicks *Link Telegram*.
2. The server issues a single-use, short-lived token (only its hash is stored).
3. The website shows a ``t.me`` deep link that pre-fills the token.
4. The user presses Start in the bot; the bot passes the verified numeric
   Telegram user id back to the internal bot API.
5. The token is consumed and the Telegram account is bound to the website user.

The user never types their website password into Telegram.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_session
from app.core.config import settings
from app.database.session import get_db
from app.models.user import UserSession
from app.schemas.auth import TelegramStatus
from app.schemas.telegram import TelegramLinkStartOut, TelegramUnlinkOut
from app.services import telegram_service

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatus)
def status(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    return telegram_service.link_status(db, session.user_id)


@router.post("/link", response_model=TelegramLinkStartOut)
def start_link(
    request: Request,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Issue a new single-use linking token (invalidates any previous one)."""
    raw_token, record = telegram_service.create_link_token(
        db, user_id=session.user_id, ip_address=client_ip(request)
    )
    deep_link = telegram_service.link_url(raw_token)
    bot_username = settings.telegram_bot_username or None

    instructions_km = (
        "១. ចុចប៊ូតុង «បើក Telegram» ខាងក្រោម។\n"
        "២. ប្រសិនបើ Telegram មិនបើក សូមចម្លងកូដនេះ ហើយផ្ញើទៅ bot: /start " + raw_token + "\n"
        "៣. bot នឹងភ្ជាប់គណនីរបស់អ្នកដោយស្វ័យប្រវត្តិ។\n"
        f"(កូដមានសុពលភាព {settings.telegram_link_ttl_minutes} នាទី និងប្រើបានតែម្ដង)"
    )
    instructions_en = (
        f"Open the bot and press Start, or send to the bot: /start {raw_token}\n"
        f"The code is single-use and expires in {settings.telegram_link_ttl_minutes} minutes."
    )
    return {
        "token": raw_token,
        "deep_link": deep_link,
        "expires_at": record.expires_at,
        "ttl_minutes": settings.telegram_link_ttl_minutes,
        "bot_username": bot_username,
        "instructions_en": instructions_en,
        "instructions_km": instructions_km,
    }


@router.delete("/link", response_model=TelegramUnlinkOut)
def unlink(
    request: Request,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Unlink your own Telegram account."""
    revoked = telegram_service.unlink_self(
        db, user=session.user, ip_address=client_ip(request)
    )
    return {"revoked": revoked, "status": telegram_service.link_status(db, session.user_id)}
