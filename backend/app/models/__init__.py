"""SQLAlchemy models.  Importing this package registers every table on ``Base``."""

from app.database.base import Base
from app.models.catalog import RollType, Supplier
from app.models.delivery import Delivery
from app.models.enums import DeliverySource, DeliveryStatus, UserRole
from app.models.payment import Payment, PaymentAllocation
from app.models.system import AppSetting, AuditLog
from app.models.telegram import TelegramAccount, TelegramLinkAttempt, TelegramLinkToken
from app.models.user import LoginAttempt, User, UserSession

__all__ = [
    "Base",
    "User",
    "UserSession",
    "LoginAttempt",
    "TelegramAccount",
    "TelegramLinkToken",
    "TelegramLinkAttempt",
    "Supplier",
    "RollType",
    "Delivery",
    "Payment",
    "PaymentAllocation",
    "AppSetting",
    "AuditLog",
    "UserRole",
    "DeliverySource",
    "DeliveryStatus",
]
