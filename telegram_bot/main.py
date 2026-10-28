"""Khmer warehouse bot. All inventory and payment data comes from the API."""

from __future__ import annotations

import asyncio
import calendar
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from telegram_bot.states import DeliveryFlow, PaymentFlow

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("warehouse.telegram_bot")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

MENU_DELIVERY = "កត់ត្រាការទទួលទំនិញ"
MENU_SUMMARY = "មើលចំនួនកាវ"
MENU_DELIVERIES = "មើលប្រវត្តិការទទួល"
MENU_UNPAID = "មើលចំនួនមិនទាន់បង់"
MENU_PAYMENTS = "មើលប្រវត្តិការបង់"
MENU_HELP = "ជំនួយ"
CANCEL = "បោះបង់"
DATE_PAGE_SIZE = 8
KHMER_DIGITS = str.maketrans("0123456789", "០១២៣៤៥៦៧៨៩")
KHMER_MONTHS = (
    "មករា",
    "កុម្ភៈ",
    "មីនា",
    "មេសា",
    "ឧសភា",
    "មិថុនា",
    "កក្កដា",
    "សីហា",
    "កញ្ញា",
    "តុលា",
    "វិច្ឆិកា",
    "ធ្នូ",
)

router = Router()
_client: httpx.AsyncClient | None = None
_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=MENU_DELIVERY), KeyboardButton(text=MENU_SUMMARY)],
        [KeyboardButton(text=MENU_DELIVERIES), KeyboardButton(text=MENU_UNPAID)],
        [KeyboardButton(text=MENU_PAYMENTS), KeyboardButton(text=MENU_HELP)],
    ],
    resize_keyboard=True,
    input_field_placeholder="ជ្រើសរើសមុខងារ",
)
_cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=CANCEL)]],
    resize_keyboard=True,
)


class BotAPIError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _telegram_id(message: Message | CallbackQuery) -> int | None:
    sender = message.from_user
    return sender.id if sender else None


async def _request(
    method: str,
    path: str,
    *,
    telegram_user_id: int | None = None,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    if _client is None:
        raise BotAPIError("backend_unavailable", "សេវាកម្មមិនទាន់រួចរាល់ទេ។")
    request_params = {
        key: value for key, value in (params or {}).items() if value is not None
    }
    if telegram_user_id is not None:
        request_params["telegram_user_id"] = telegram_user_id
    try:
        response = await _client.request(
            method,
            path,
            params=request_params or None,
            json=payload,
        )
    except httpx.RequestError as exc:
        raise BotAPIError(
            "backend_unavailable",
            "មិនអាចភ្ជាប់ទៅប្រព័ន្ធឃ្លាំងបានទេ។ សូមសាកល្បងម្ដងទៀត។",
        ) from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise BotAPIError("invalid_response", "ប្រព័ន្ធបានផ្ញើការឆ្លើយតបមិនត្រឹមត្រូវ។") from exc
    if not response.is_success:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code", "request_failed")
        message = _khmer_error(code)
        raise BotAPIError(code, message)
    return data


def _khmer_error(code: str) -> str:
    messages = {
        "telegram_not_linked": "សូមភ្ជាប់ Telegram ពីទំព័រគណនីនៅលើគេហទំព័រជាមុនសិន។",
        "telegram_link_revoked": "ការភ្ជាប់ Telegram ត្រូវបានដកហើយ។ សូមភ្ជាប់ម្ដងទៀត។",
        "user_inactive": "គណនីនេះត្រូវបានបិទ។ សូមទាក់ទងអ្នកគ្រប់គ្រង។",
        "link_token_expired": "កូដភ្ជាប់ផុតកំណត់។ សូមបង្កើតកូដថ្មីនៅលើគេហទំព័រ។",
        "link_token_invalid": "កូដភ្ជាប់មិនត្រឹមត្រូវ។ សូមពិនិត្យម្ដងទៀត។",
        "link_token_used": "កូដនេះត្រូវបានប្រើរួចហើយ។",
        "telegram_link_rate_limited": "សាកល្បងច្រើនដងពេក។ សូមរង់ចាំបន្តិច។",
        "forbidden": "អ្នកមិនមានសិទ្ធិបញ្ជាក់ការបង់ប្រាក់ទេ។",
        "nothing_to_pay": "មិនមានចំនួនមិនទាន់បង់ក្នុងកាលបរិច្ឆេទនេះទេ។",
        "exceeds_unpaid_quantity": "ចំនួននេះលើសពីចំនួនដែលនៅមិនទាន់បង់។",
        "invalid_date_range": "កាលបរិច្ឆេទចាប់ផ្ដើមត្រូវតែមុនកាលបរិច្ឆេទបញ្ចប់។",
    }
    return messages.get(code, "សំណើមិនអាចបំពេញបានទេ។ សូមពិនិត្យព័ត៌មានហើយព្យាយាមម្ដងទៀត។")


async def _principal(telegram_user_id: int) -> dict[str, Any]:
    return await _request("GET", "/api/bot/me", telegram_user_id=telegram_user_id)


async def _linked_or_reply(message: Message, telegram_user_id: int) -> dict[str, Any] | None:
    try:
        principal = await _principal(telegram_user_id)
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return None
    if not principal.get("linked"):
        await message.answer(
            principal.get("message") or "សូមភ្ជាប់ Telegram ពីគេហទំព័រជាមុនសិន។",
            reply_markup=_menu,
        )
        return None
    return principal


def _items_keyboard(items: list[dict[str, Any]], field: str = "name") -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=str(item[field]))] for item in items]
    rows.append([KeyboardButton(text=CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="បញ្ជាក់ការបង់", callback_data="payment:confirm")],
            [InlineKeyboardButton(text=CANCEL, callback_data="flow:cancel")],
        ]
    )


def _delivery_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="រក្សាទុកការទទួល", callback_data="delivery:confirm")],
            [InlineKeyboardButton(text=CANCEL, callback_data="flow:cancel")],
        ]
    )


def _delivery_date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ថ្ងៃនេះ", callback_data="delivery:today")],
            [
                InlineKeyboardButton(
                    text="ជ្រើសរើសថ្ងៃផ្សេង",
                    callback_data="delivery:calendar:open",
                )
            ],
            [InlineKeyboardButton(text=CANCEL, callback_data="flow:cancel")],
        ]
    )


def _delivery_note_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="រំលង", callback_data="delivery:note:skip")],
            [InlineKeyboardButton(text=CANCEL, callback_data="flow:cancel")],
        ]
    )


def _phnom_penh_today() -> date:
    return datetime.now(ZoneInfo("Asia/Phnom_Penh")).date()


def _format_date_kh(value: date | str) -> str:
    day = date.fromisoformat(value) if isinstance(value, str) else value
    return (
        f"{str(day.day).translate(KHMER_DIGITS)} "
        f"{KHMER_MONTHS[day.month - 1]} "
        f"{str(day.year).translate(KHMER_DIGITS)}"
    )


def _calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    first_day = date(year, month, 1)
    today = _phnom_penh_today()
    earliest = date(2000, 1, 1)
    latest = today + timedelta(days=365)
    _, days_in_month = calendar.monthrange(year, month)
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data="delivery:calendar:noop")
            for label in ("ច", "អ", "ព", "ព្រ", "សុ", "ស", "អា")
        ]
    ]
    days = []
    for day in range(1, days_in_month + 1):
        selected = date(year, month, day)
        callback_data = (
            f"delivery:date:{selected.isoformat()}"
            if earliest <= selected <= latest
            else "delivery:calendar:noop"
        )
        days.append(
            InlineKeyboardButton(
                text=str(day).translate(KHMER_DIGITS),
                callback_data=callback_data,
            )
        )
    offset = first_day.weekday()
    weeks: list[list[InlineKeyboardButton]] = []
    current_week: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="·", callback_data="delivery:calendar:noop")
        for _ in range(offset)
    ]
    for button in days:
        current_week.append(button)
        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []
    if current_week:
        current_week.extend(
            InlineKeyboardButton(text="·", callback_data="delivery:calendar:noop")
            for _ in range(7 - len(current_week))
        )
        weeks.append(current_week)
    rows.extend(weeks)

    previous_month = first_day - timedelta(days=1)
    next_month = date(year + (1 if month == 12 else 0), month % 12 + 1, 1)
    min_month = date(2000, 1, 1)
    max_month = date(latest.year, latest.month, 1)
    rows.append(
        [
            InlineKeyboardButton(
                text="‹",
                callback_data=(
                    f"delivery:calendar:{previous_month.year:04d}-{previous_month.month:02d}"
                    if previous_month >= min_month
                    else "delivery:calendar:noop"
                ),
            ),
            InlineKeyboardButton(
                text=f"{KHMER_MONTHS[month - 1]} {str(year).translate(KHMER_DIGITS)}",
                callback_data="delivery:calendar:noop",
            ),
            InlineKeyboardButton(
                text="›",
                callback_data=(
                    f"delivery:calendar:{next_month.year:04d}-{next_month.month:02d}"
                    if next_month <= max_month
                    else "delivery:calendar:noop"
                ),
            ),
        ]
    )
    rows.extend(
        [
            [InlineKeyboardButton(text="ត្រឡប់ក្រោយ", callback_data="delivery:calendar:back")],
            [InlineKeyboardButton(text=CANCEL, callback_data="flow:cancel")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _payment_date_keyboard(
    dates: list[str],
    *,
    stage: str,
    page: int = 0,
) -> InlineKeyboardMarkup:
    options = sorted(set(dates), reverse=True)
    page_count = max(1, (len(options) + DATE_PAGE_SIZE - 1) // DATE_PAGE_SIZE)
    page = max(0, min(page, page_count - 1))
    first = page * DATE_PAGE_SIZE
    page_dates = options[first : first + DATE_PAGE_SIZE]
    rows = [
        [
            InlineKeyboardButton(
                text=_format_date_kh(value),
                callback_data=f"payment:{stage}:{value}",
            )
            for value in page_dates[index : index + 2]
        ]
        for index in range(0, len(page_dates), 2)
    ]
    if page_count > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="‹",
                    callback_data=f"payment:page:{stage}:{page - 1}",
                )
                if page > 0
                else InlineKeyboardButton(text="·", callback_data="payment:noop"),
                InlineKeyboardButton(
                    text=(
                        f"{str(page + 1).translate(KHMER_DIGITS)}/"
                        f"{str(page_count).translate(KHMER_DIGITS)}"
                    ),
                    callback_data="payment:noop",
                ),
                InlineKeyboardButton(
                    text="›",
                    callback_data=f"payment:page:{stage}:{page + 1}",
                )
                if page + 1 < page_count
                else InlineKeyboardButton(text="·", callback_data="payment:noop"),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="សម្រាប់ទាំងអស់", callback_data="payment:all")]
    )
    if stage == "end":
        rows.append(
            [
                InlineKeyboardButton(
                    text="មិនកំណត់ថ្ងៃបញ្ចប់",
                    callback_data="payment:end:unbounded",
                )
            ]
        )
        rows.append([InlineKeyboardButton(text="ត្រឡប់ក្រោយ", callback_data="payment:back:start")])
    else:
        rows.append([InlineKeyboardButton(text="ត្រឡប់ក្រោយ", callback_data="payment:back:roll_type")])
    rows.append([InlineKeyboardButton(text=CANCEL, callback_data="flow:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
) -> None:
    await state.clear()
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None:
        await message.answer("មិនអាចផ្ទៀងផ្ទាត់គណនី Telegram បានទេ។")
        return
    if command.args:
        try:
            linked = await _request(
                "POST",
                "/api/bot/link",
                payload={
                    "token": command.args,
                    "telegram_user_id": telegram_user_id,
                    "telegram_username": message.from_user.username if message.from_user else None,
                    "telegram_chat_id": message.chat.id,
                },
            )
        except BotAPIError as exc:
            await message.answer(exc.message, reply_markup=_menu)
            return
        await message.answer(
            f"បានភ្ជាប់គណនីដោយជោគជ័យ។ សួស្តី {linked['username']}!",
            reply_markup=_menu,
        )
        return
    try:
        principal = await _principal(telegram_user_id)
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return
    if not principal.get("linked"):
        await message.answer(
            "សូមភ្ជាប់គណនី Telegram ពីផ្នែក «គណនី និង Telegram» នៅលើគេហទំព័រជាមុនសិន។",
            reply_markup=_menu,
        )
        return
    await message.answer(
        f"សួស្តី {principal['username']}! ជ្រើសរើសមុខងារខាងក្រោម។",
        reply_markup=_menu,
    )


@router.message(Command("cancel"))
@router.message(F.text == CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("បានបោះបង់សកម្មភាព។", reply_markup=_menu)


@router.message(Command("help"))
@router.message(F.text == MENU_HELP)
async def help_message(message: Message) -> None:
    await message.answer(
        "ជ្រើសរើសមុខងារពីម៉ឺនុយ។ អ្នកអាចប្រើ /cancel ដើម្បីបោះបង់ជំហានណាមួយ "
        "និង /start ដើម្បីចាប់ផ្ដើមឡើងវិញ។",
        reply_markup=_menu,
    )


@router.message(F.text == MENU_DELIVERY)
async def begin_delivery(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        return
    try:
        catalog = await _request("GET", "/api/bot/catalog", telegram_user_id=telegram_user_id)
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return
    if not catalog["suppliers"] or not catalog["roll_types"]:
        await message.answer("មិនទាន់មានអ្នកផ្គត់ផ្គង់ ឬប្រភេទកាវសកម្មទេ។", reply_markup=_menu)
        return
    await state.clear()
    await state.update_data(suppliers=catalog["suppliers"], roll_types=catalog["roll_types"])
    await state.set_state(DeliveryFlow.supplier)
    await message.answer("សូមជ្រើសរើសអ្នកផ្គត់ផ្គង់៖", reply_markup=_items_keyboard(catalog["suppliers"]))


@router.message(DeliveryFlow.supplier)
async def select_delivery_supplier(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        await state.clear()
        return
    data = await state.get_data()
    supplier = next((item for item in data["suppliers"] if item["name"] == message.text), None)
    if supplier is None:
        await message.answer("សូមជ្រើសរើសអ្នកផ្គត់ផ្គង់ពីបញ្ជី។")
        return
    await state.update_data(supplier_id=supplier["id"], supplier_name=supplier["name"])
    await state.set_state(DeliveryFlow.roll_type)
    await message.answer("សូមជ្រើសរើសប្រភេទកាវ៖", reply_markup=_items_keyboard(data["roll_types"]))


@router.message(DeliveryFlow.roll_type)
async def select_delivery_type(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        await state.clear()
        return
    data = await state.get_data()
    roll_type = next((item for item in data["roll_types"] if item["name"] == message.text), None)
    if roll_type is None:
        await message.answer("សូមជ្រើសរើសប្រភេទកាវពីបញ្ជី។")
        return
    await state.update_data(roll_type_id=roll_type["id"], roll_type_name=roll_type["name"])
    await state.set_state(DeliveryFlow.quantity)
    await message.answer("បញ្ចូលចំនួនកី (លេខគត់ធំជាង ០)៖", reply_markup=_cancel_keyboard)


@router.message(DeliveryFlow.quantity)
async def enter_delivery_quantity(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        await state.clear()
        return
    value = (message.text or "").strip()
    if not value.isdecimal() or not 1 <= int(value) <= 1_000_000:
        await message.answer("សូមបញ្ចូលលេខគត់ចាប់ពី ១ ដល់ ១,០០០,០០០។")
        return
    await state.update_data(quantity=int(value))
    await state.set_state(DeliveryFlow.date)
    await message.answer("សូមជ្រើសរើសថ្ងៃទទួល៖", reply_markup=_delivery_date_keyboard())


@router.message(DeliveryFlow.date)
async def reject_typed_delivery_date(message: Message) -> None:
    await message.answer("សូមជ្រើសរើសថ្ងៃទទួលពីប៊ូតុងខាងក្រោម។")


async def _prompt_delivery_note(message: Message, state: FSMContext) -> None:
    await state.set_state(DeliveryFlow.note)
    await message.answer(
        "សូមបញ្ចូលកំណត់ចំណាំ ប្រសិនបើមាន៖",
        reply_markup=_delivery_note_keyboard(),
    )


@router.callback_query(F.data == "delivery:today")
async def select_delivery_today(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != DeliveryFlow.date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    await state.update_data(delivery_date=_phnom_penh_today().isoformat())
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _prompt_delivery_note(callback.message, state)


@router.callback_query(F.data == "delivery:calendar:open")
async def open_delivery_calendar(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != DeliveryFlow.date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    today = _phnom_penh_today()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"ជ្រើសរើសថ្ងៃទទួល៖ {_format_date_kh(today)}",
            reply_markup=_calendar_keyboard(today.year, today.month),
        )


@router.callback_query(F.data == "delivery:calendar:back")
async def back_to_delivery_date_choices(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != DeliveryFlow.date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "សូមជ្រើសរើសថ្ងៃទទួល៖",
            reply_markup=_delivery_date_keyboard(),
        )


@router.callback_query(F.data.startswith("delivery:calendar:"))
async def navigate_delivery_calendar(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == "delivery:calendar:noop":
        await callback.answer()
        return
    if await state.get_state() != DeliveryFlow.date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    month_value = (callback.data or "").removeprefix("delivery:calendar:")
    try:
        year, month = (int(part) for part in month_value.split("-"))
        if not 1 <= month <= 12 or not 2000 <= year <= _phnom_penh_today().year + 2:
            raise ValueError
    except ValueError:
        await callback.answer("ខែដែលបានជ្រើសរើសមិនត្រឹមត្រូវទេ។", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"ជ្រើសរើសថ្ងៃទទួល៖ {KHMER_MONTHS[month - 1]} {str(year).translate(KHMER_DIGITS)}",
            reply_markup=_calendar_keyboard(year, month),
        )


@router.callback_query(F.data.startswith("delivery:date:"))
async def select_delivery_calendar_date(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != DeliveryFlow.date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    try:
        selected = date.fromisoformat((callback.data or "").removeprefix("delivery:date:"))
    except ValueError:
        await callback.answer("ថ្ងៃដែលបានជ្រើសរើសមិនត្រឹមត្រូវទេ។", show_alert=True)
        return
    if not date(2000, 1, 1) <= selected <= _phnom_penh_today() + timedelta(days=365):
        await callback.answer("ថ្ងៃនេះមិនអាចជ្រើសរើសបានទេ។", show_alert=True)
        return
    await state.update_data(delivery_date=selected.isoformat())
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _prompt_delivery_note(callback.message, state)


async def _show_delivery_confirmation(message: Message, state: FSMContext, note: str | None) -> None:
    await state.update_data(
        note=note,
        idempotency_key=str(uuid4()),
    )
    await state.set_state(DeliveryFlow.confirm)
    data = await state.get_data()
    await message.answer(
        "សូមពិនិត្យព័ត៌មានមុនរក្សាទុក៖\n"
        f"អ្នកផ្គត់ផ្គង់៖ {data['supplier_name']}\n"
        f"ប្រភេទកាវ៖ {data['roll_type_name']}\n"
        f"ចំនួន៖ {data['quantity']} កី\n"
        f"ថ្ងៃទទួល៖ {_format_date_kh(data['delivery_date'])}\n"
        f"កំណត់ចំណាំ៖ {data['note'] or '—'}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("តើត្រូវរក្សាទុកកំណត់ត្រានេះទេ?", reply_markup=_delivery_keyboard())


@router.message(DeliveryFlow.note)
async def enter_delivery_note(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        await state.clear()
        return
    note = (message.text or "").strip()
    if note in {"រំលង", "skip", "-"}:
        note = None
    if note is not None and len(note) > 2000:
        await message.answer("កំណត់ចំណាំវែងពេក។ សូមបញ្ចូលមិនលើស ២,០០០ តួ។")
        return
    await _show_delivery_confirmation(message, state, note or None)


@router.callback_query(F.data == "delivery:note:skip")
async def skip_delivery_note(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != DeliveryFlow.note.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _show_delivery_confirmation(callback.message, state, None)


@router.callback_query(F.data == "delivery:confirm")
async def confirm_delivery(callback: CallbackQuery, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(callback)
    if telegram_user_id is None:
        await callback.answer("មិនអាចផ្ទៀងផ្ទាត់គណនីបានទេ។", show_alert=True)
        return
    if await state.get_state() != DeliveryFlow.confirm.state:
        await callback.answer("កំណត់ត្រានេះបានដំណើរការរួចហើយ។", show_alert=True)
        return
    try:
        await _principal(telegram_user_id)
        data = await state.get_data()
        if data.get("delivery_submitting"):
            await callback.answer("កំពុងរក្សាទុក សូមរង់ចាំ។")
            return
        await state.update_data(delivery_submitting=True)
        created = await _request(
            "POST",
            "/api/bot/deliveries",
            payload={
                "telegram_user_id": telegram_user_id,
                "supplier_id": data["supplier_id"],
                "roll_type_id": data["roll_type_id"],
                "quantity_received": data["quantity"],
                "delivery_date": data["delivery_date"],
                "note": data["note"],
                "idempotency_key": data["idempotency_key"],
            },
        )
    except (BotAPIError, KeyError) as exc:
        text = exc.message if isinstance(exc, BotAPIError) else "លំហូរការងារផុតកំណត់។ សូមចាប់ផ្ដើមម្ដងទៀត។"
        await callback.answer(text, show_alert=True)
        if callback.message:
            await callback.message.answer(text, reply_markup=_menu)
        await state.clear()
        return
    delivery = created["delivery"]
    await callback.answer("បានរក្សាទុក")
    if callback.message:
        await callback.message.answer(
            "ការកត់ត្រាជោគជ័យ!\n"
            f"អ្នកផ្គត់ផ្គង់៖ {delivery['supplier_name']}\n"
            f"ប្រភេទកាវ៖ {delivery['roll_type_name']}\n"
            f"ចំនួន៖ {delivery['quantity_received']} កី\n"
            f"ថ្ងៃទទួល៖ {_format_date_kh(delivery['delivery_date'])}",
            reply_markup=_menu,
        )
    await state.clear()


@router.message(F.text == MENU_SUMMARY)
async def show_summary(message: Message) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        return
    try:
        result = await _request("GET", "/api/bot/summary", telegram_user_id=telegram_user_id)
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return
    suppliers = "\n".join(
        f"• {item['supplier_name']}: {item['received']} (មិនទាន់បង់ {item['unpaid']})"
        for item in result["by_supplier"]
    ) or "• មិនទាន់មានទិន្នន័យ"
    types = "\n".join(
        f"• {item['roll_type_name']}: ទទួល {item['received']} · បានបង់ {item['paid']} · មិនទាន់បង់ {item['unpaid']}"
        for item in result["by_roll_type"]
    ) or "• មិនទាន់មានទិន្នន័យ"
    supplier_types = "\n".join(
        f"• {item['supplier_name']} · {item['roll_type_name']}: "
        f"ទទួល {item['received']} · បានបង់ {item['paid']} · មិនទាន់បង់ {item['unpaid']}"
        for item in result["by_supplier_and_roll_type"]
    ) or "• មិនទាន់មានទិន្នន័យ"
    await message.answer(
        "សង្ខេបបរិមាណ (ចំនួនទទួល មិនមែនស្តុកដែលនៅសល់)៖\n"
        f"ទទួលសរុប៖ {result['total_received']}\n"
        f"ទទួលថ្ងៃនេះ៖ {result['received_today']}\n"
        f"បានបង់៖ {result['total_paid']}\n"
        f"មិនទាន់បង់៖ {result['total_unpaid']}\n\n"
        f"តាមអ្នកផ្គត់ផ្គង់៖\n{suppliers}\n\nតាមប្រភេទកាវ៖\n{types}\n\n"
        f"តាមអ្នកផ្គត់ផ្គង់ និងប្រភេទកាវ៖\n{supplier_types}",
        reply_markup=_menu,
    )


@router.message(F.text == MENU_DELIVERIES)
async def show_deliveries(message: Message) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        return
    try:
        result = await _request(
            "GET",
            "/api/bot/deliveries",
            telegram_user_id=telegram_user_id,
            params={"page": 1, "page_size": 10},
        )
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return
    if not result["items"]:
        await message.answer("មិនទាន់មានប្រវត្តិការទទួលទេ។", reply_markup=_menu)
        return
    rows = "\n".join(
        f"• {row['delivery_date']} · {row['supplier_name']} · {row['roll_type_name']} "
        f"· ទទួល {row['quantity_received']} · មិនទាន់បង់ {row['quantity_unpaid']}"
        for row in result["items"]
    )
    await message.answer(f"ប្រវត្តិការទទួលថ្មីៗ៖\n{rows}", reply_markup=_menu)


@router.message(F.text == MENU_UNPAID)
async def begin_payment(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None:
        return
    principal = await _linked_or_reply(message, telegram_user_id)
    if principal is None:
        return
    try:
        catalog = await _request("GET", "/api/bot/catalog", telegram_user_id=telegram_user_id)
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return
    if not catalog["suppliers"]:
        await message.answer("មិនទាន់មានអ្នកផ្គត់ផ្គង់សកម្មទេ។", reply_markup=_menu)
        return
    await state.clear()
    await state.update_data(
        suppliers=catalog["suppliers"],
        roll_types=catalog["roll_types"],
        can_confirm=principal.get("permissions", {}).get("can_confirm_payments", False),
    )
    await state.set_state(PaymentFlow.supplier)
    await message.answer("ជ្រើសអ្នកផ្គត់ផ្គង់សម្រាប់ពិនិត្យចំនួនមិនទាន់បង់៖", reply_markup=_items_keyboard(catalog["suppliers"]))


@router.message(PaymentFlow.supplier)
async def select_payment_supplier(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        await state.clear()
        return
    data = await state.get_data()
    supplier = next((item for item in data["suppliers"] if item["name"] == message.text), None)
    if supplier is None:
        await message.answer("សូមជ្រើសអ្នកផ្គត់ផ្គង់ពីបញ្ជី។")
        return
    await state.update_data(supplier_id=supplier["id"], supplier_name=supplier["name"])
    await state.set_state(PaymentFlow.roll_type)
    await message.answer("ជ្រើសរើសប្រភេទកាវសម្រាប់ការបង់៖", reply_markup=_items_keyboard(data["roll_types"]))


@router.message(PaymentFlow.roll_type)
async def select_payment_roll_type(message: Message, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        await state.clear()
        return
    data = await state.get_data()
    roll_type = next((item for item in data["roll_types"] if item["name"] == message.text), None)
    if roll_type is None:
        await message.answer("សូមជ្រើសរើសប្រភេទកាវពីបញ្ជី។")
        return
    await state.update_data(roll_type_id=roll_type["id"], roll_type_name=roll_type["name"])
    try:
        preview = await _request(
            "GET",
            "/api/bot/payments/unpaid",
            telegram_user_id=telegram_user_id,
            params={
                "supplier_id": data["supplier_id"],
                "roll_type_id": roll_type["id"],
            },
        )
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        await state.clear()
        return
    dates = sorted(
        {date.fromisoformat(str(value)).isoformat() for value in preview["delivery_dates"]},
        reverse=True,
    )
    await state.update_data(payment_dates=dates, payment_start_page=0, payment_end_page=0)
    await state.set_state(PaymentFlow.start_date)
    await message.answer("បានជ្រើសរើសប្រភេទកាវ។", reply_markup=ReplyKeyboardRemove())
    await _send_payment_date_page(message, state, "start", 0)


def _payment_date_options(data: dict[str, Any], stage: str) -> list[str]:
    dates = data.get("payment_dates", [])
    if stage == "end" and data.get("start_date"):
        dates = [value for value in dates if value >= data["start_date"]]
    return sorted(set(dates), reverse=True)


def _payment_date_prompt(data: dict[str, Any], stage: str) -> str:
    if stage == "start":
        if data.get("payment_dates"):
            return "សូមជ្រើសរើសថ្ងៃទទួលចាប់ពី ឬជ្រើស «សម្រាប់ទាំងអស់»៖"
        return "មិនមានកាលបរិច្ឆេទទទួលដែលនៅមិនទាន់បង់ទេ។ អ្នកអាចមើលទាំងអស់ ឬត្រឡប់ក្រោយ។"
    return (
        f"សូមជ្រើសរើសថ្ងៃទទួលដល់ (ចាប់ពី {_format_date_kh(data['start_date'])}) "
        "ឬជ្រើស «សម្រាប់ទាំងអស់»៖"
    )


async def _send_payment_date_page(
    message: Message,
    state: FSMContext,
    stage: str,
    page: int,
) -> None:
    data = await state.get_data()
    dates = _payment_date_options(data, stage)
    page_count = max(1, (len(dates) + DATE_PAGE_SIZE - 1) // DATE_PAGE_SIZE)
    page = max(0, min(page, page_count - 1))
    key = "payment_start_page" if stage == "start" else "payment_end_page"
    await state.update_data(**{key: page})
    await message.answer(
        _payment_date_prompt(data, stage),
        reply_markup=_payment_date_keyboard(dates, stage=stage, page=page),
    )


async def _preview_payment_selection(
    message: Message,
    state: FSMContext,
    telegram_user_id: int,
    start_date: str | None,
    end_date: str | None,
) -> None:
    data = await state.get_data()
    try:
        preview = await _request(
            "GET",
            "/api/bot/payments/unpaid",
            telegram_user_id=telegram_user_id,
            params={
                "supplier_id": data["supplier_id"],
                "roll_type_id": data["roll_type_id"],
                "start_date": start_date,
                "end_date": end_date,
            },
        )
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        await state.clear()
        return
    if preview["totals"]["unpaid"] <= 0:
        await message.answer(
            "មិនមានចំនួនមិនទាន់បង់ក្នុងជម្រើសនេះទេ។",
            reply_markup=_menu,
        )
        await state.clear()
        return
    date_range = (
        "សម្រាប់ទាំងអស់"
        if start_date is None and end_date is None
        else f"ចាប់ពី {_format_date_kh(start_date) if start_date else 'ទាំងអស់'} "
        f"ដល់ {_format_date_kh(end_date) if end_date else 'មិនកំណត់'}"
    )
    if not data.get("can_confirm", False):
        delivery_lines = "\n".join(
            f"• {_format_date_kh(row['delivery_date'])} · {row['roll_type_name']} "
            f"· មិនទាន់បង់ {row['quantity_unpaid']}"
            for row in preview["deliveries"]
        )
        await message.answer(
            f"ចំនួនមិនទាន់បង់៖ {preview['supplier']['name']}\n"
            f"ថ្ងៃទទួល៖ {date_range}\n"
            f"{delivery_lines}\nសរុប៖ {preview['totals']['unpaid']} កី",
            reply_markup=_menu,
        )
        await state.clear()
        return
    await state.update_data(
        start_date=start_date,
        end_date=end_date,
        idempotency_key=str(uuid4()),
    )
    await state.set_state(PaymentFlow.confirm)
    delivery_lines = "\n".join(
        f"• {_format_date_kh(row['delivery_date'])} · {row['roll_type_name']} "
        f"· នៅសល់ {row['quantity_unpaid']}"
        for row in preview["deliveries"]
    )
    await message.answer(
        f"ពិនិត្យការបង់៖\nអ្នកផ្គត់ផ្គង់៖ {preview['supplier']['name']}\n"
        f"ប្រភេទកាវ៖ {data['roll_type_name']}\n"
        f"ថ្ងៃទទួល៖ {date_range}\n"
        f"{delivery_lines}\nសរុប៖ {preview['totals']['unpaid']} កី",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("តើត្រូវបញ្ជាក់ការបង់ទាំងនេះទេ?", reply_markup=_payment_keyboard())


@router.message(PaymentFlow.start_date)
async def enter_payment_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "សូមជ្រើសរើសថ្ងៃពីប៊ូតុងខាងក្រោម។",
        reply_markup=_payment_date_keyboard(
            _payment_date_options(await state.get_data(), "start"),
            stage="start",
            page=0,
        ),
    )


@router.message(PaymentFlow.end_date)
async def enter_payment_end(message: Message, state: FSMContext) -> None:
    await message.answer(
        "សូមជ្រើសរើសថ្ងៃពីប៊ូតុងខាងក្រោម។",
        reply_markup=_payment_date_keyboard(
            _payment_date_options(await state.get_data(), "end"),
            stage="end",
            page=0,
        ),
    )


@router.callback_query(F.data.startswith("payment:page:"))
async def navigate_payment_dates(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        _, _, stage, page_value = (callback.data or "").split(":")
        page = int(page_value)
    except ValueError:
        await callback.answer("ទំព័រមិនត្រឹមត្រូវទេ។", show_alert=True)
        return
    expected_state = PaymentFlow.start_date.state if stage == "start" else PaymentFlow.end_date.state
    if stage not in {"start", "end"} or await state.get_state() != expected_state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        data = await state.get_data()
        dates = _payment_date_options(data, stage)
        page_count = max(1, (len(dates) + DATE_PAGE_SIZE - 1) // DATE_PAGE_SIZE)
        page = max(0, min(page, page_count - 1))
        key = "payment_start_page" if stage == "start" else "payment_end_page"
        await state.update_data(**{key: page})
        await callback.message.edit_text(
            _payment_date_prompt(data, stage),
            reply_markup=_payment_date_keyboard(dates, stage=stage, page=page),
        )


@router.callback_query(F.data == "payment:noop")
async def payment_date_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "payment:all")
async def select_all_payment_dates(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() not in {
        PaymentFlow.start_date.state,
        PaymentFlow.end_date.state,
    }:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    telegram_user_id = _telegram_id(callback)
    if telegram_user_id is None or callback.message is None:
        await callback.answer("មិនអាចផ្ទៀងផ្ទាត់គណនីបានទេ។", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _preview_payment_selection(callback.message, state, telegram_user_id, None, None)


@router.callback_query(F.data == "payment:end:unbounded")
async def select_payment_without_end_date(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PaymentFlow.end_date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    telegram_user_id = _telegram_id(callback)
    if telegram_user_id is None or callback.message is None:
        await callback.answer("មិនអាចផ្ទៀងផ្ទាត់គណនីបានទេ។", show_alert=True)
        return
    data = await state.get_data()
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await _preview_payment_selection(
        callback.message,
        state,
        telegram_user_id,
        data["start_date"],
        None,
    )


@router.callback_query(F.data == "payment:back:start")
async def back_to_payment_start_dates(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PaymentFlow.end_date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await state.set_state(PaymentFlow.start_date)
        data = await state.get_data()
        page = data.get("payment_start_page", 0)
        await callback.message.edit_text(
            _payment_date_prompt(data, "start"),
            reply_markup=_payment_date_keyboard(
                _payment_date_options(data, "start"),
                stage="start",
                page=page,
            ),
        )


@router.callback_query(F.data == "payment:back:roll_type")
async def back_to_payment_roll_type(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PaymentFlow.start_date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        data = await state.get_data()
        await state.set_state(PaymentFlow.roll_type)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "ជ្រើសរើសប្រភេទកាវសម្រាប់ការបង់៖",
            reply_markup=_items_keyboard(data["roll_types"]),
        )


@router.callback_query(F.data.startswith("payment:start:"))
async def select_payment_start_date(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PaymentFlow.start_date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    value = (callback.data or "").removeprefix("payment:start:")
    data = await state.get_data()
    if value not in data.get("payment_dates", []):
        await callback.answer("ថ្ងៃនេះមិនមានក្នុងបញ្ជីទេ។", show_alert=True)
        return
    await state.update_data(start_date=value)
    await state.set_state(PaymentFlow.end_date)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            _payment_date_prompt(await state.get_data(), "end"),
            reply_markup=_payment_date_keyboard(
                _payment_date_options(await state.get_data(), "end"),
                stage="end",
                page=0,
            ),
        )


@router.callback_query(F.data.startswith("payment:end:"))
async def select_payment_end_date(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PaymentFlow.end_date.state:
        await callback.answer("ជំហាននេះបានបញ្ចប់រួចហើយ។", show_alert=True)
        return
    value = (callback.data or "").removeprefix("payment:end:")
    data = await state.get_data()
    if value not in _payment_date_options(data, "end"):
        await callback.answer("ថ្ងៃនេះមិនមានក្នុងបញ្ជីទេ។", show_alert=True)
        return
    telegram_user_id = _telegram_id(callback)
    if telegram_user_id is None or callback.message is None:
        await callback.answer("មិនអាចផ្ទៀងផ្ទាត់គណនីបានទេ។", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _preview_payment_selection(
        callback.message,
        state,
        telegram_user_id,
        data["start_date"],
        value,
    )


@router.callback_query(F.data == "payment:confirm")
async def confirm_payment(callback: CallbackQuery, state: FSMContext) -> None:
    telegram_user_id = _telegram_id(callback)
    if telegram_user_id is None:
        await callback.answer("មិនអាចផ្ទៀងផ្ទាត់គណនីបានទេ។", show_alert=True)
        return
    try:
        principal = await _principal(telegram_user_id)
        if not principal.get("permissions", {}).get("can_confirm_payments"):
            raise BotAPIError("forbidden", "អ្នកមិនមានសិទ្ធិបញ្ជាក់ការបង់ទេ។")
        data = await state.get_data()
        result = await _request(
            "POST",
            "/api/bot/payments/confirm",
            payload={
                "telegram_user_id": telegram_user_id,
                "supplier_id": data["supplier_id"],
                "roll_type_id": data["roll_type_id"],
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "payment_date": None,
                "idempotency_key": data["idempotency_key"],
            },
        )
    except (BotAPIError, KeyError) as exc:
        text = exc.message if isinstance(exc, BotAPIError) else "លំហូរការងារផុតកំណត់។ សូមចាប់ផ្ដើមម្ដងទៀត។"
        await callback.answer(text, show_alert=True)
        if callback.message:
            await callback.message.answer(text, reply_markup=_menu)
        await state.clear()
        return
    await callback.answer("បានបញ្ជាក់")
    if callback.message:
        await callback.message.answer(
            f"បានកត់ត្រាការបង់ជោគជ័យ!\nលេខយោង៖ {result['reference']}\n"
            f"អ្នកផ្គត់ផ្គង់៖ {result['supplier_name']}\n"
            f"ចំនួន៖ {result['total_quantity']} កី",
            reply_markup=_menu,
        )
    await state.clear()


@router.callback_query(F.data == "flow:cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("បានបោះបង់")
    if callback.message:
        await callback.message.answer("បានបោះបង់សកម្មភាព។", reply_markup=_menu)


@router.message(F.text == MENU_PAYMENTS)
async def show_payment_history(message: Message) -> None:
    telegram_user_id = _telegram_id(message)
    if telegram_user_id is None or await _linked_or_reply(message, telegram_user_id) is None:
        return
    try:
        result = await _request(
            "GET",
            "/api/bot/payments/history",
            telegram_user_id=telegram_user_id,
            params={"page": 1},
        )
    except BotAPIError as exc:
        await message.answer(exc.message, reply_markup=_menu)
        return
    if not result["items"]:
        await message.answer("មិនទាន់មានប្រវត្តិការបង់ទេ។", reply_markup=_menu)
        return
    rows = "\n".join(
        f"• {item['reference']} · {item['supplier_name']} · ថ្ងៃបង់ {item['payment_date']} "
        f"· {item['total_quantity']} កី"
        for item in result["items"]
    )
    await message.answer(f"ប្រវត្តិការបង់ថ្មីៗ៖\n{rows}", reply_markup=_menu)


async def main() -> None:
    global _client
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot")
    if not BOT_API_TOKEN or BOT_API_TOKEN in {"change-me-bot-token", "REPLACE_WITH_RANDOM_BOT_TOKEN"}:
        raise RuntimeError("BOT_API_TOKEN must be set to a random secret")
    _client = httpx.AsyncClient(
        base_url=BACKEND_URL,
        headers={"X-Bot-Token": BOT_API_TOKEN},
        timeout=httpx.Timeout(15.0),
    )
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    try:
        await dispatcher.start_polling(bot, drop_pending_updates=True)
    finally:
        await _client.aclose()
        _client = None


if __name__ == "__main__":
    asyncio.run(main())
