from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest

from telegram_bot import main
from telegram_bot.states import DeliveryFlow, PaymentFlow


class FakeState:
    def __init__(self, current: str, data: dict | None = None):
        self.current = current
        self.data = data or {}

    async def get_state(self):
        return self.current

    async def set_state(self, state):
        self.current = state.state

    async def update_data(self, **values):
        self.data.update(values)

    async def get_data(self):
        return dict(self.data)

    async def clear(self):
        self.current = None
        self.data.clear()


class FakeMessage:
    def __init__(self, text: str | None = None):
        self.text = text
        self.from_user = SimpleNamespace(id=1234)
        self.answers = []
        self.answer = AsyncMock(side_effect=self._record_answer)
        self.edit_text = AsyncMock()
        self.edit_reply_markup = AsyncMock()

    async def _record_answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def fake_callback(data: str, message: FakeMessage | None = None):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=1234),
        message=message,
        answer=AsyncMock(),
    )


def test_today_and_display_date_use_phnom_penh_calendar_date():
    expected = datetime.now(ZoneInfo("Asia/Phnom_Penh")).date()
    assert main._phnom_penh_today() == expected
    assert main._format_date_kh(date(2026, 10, 19)) == "១៩ តុលា ២០២៦"


def test_delivery_calendar_contains_selectable_days_and_month_navigation(monkeypatch):
    monkeypatch.setattr(main, "_phnom_penh_today", lambda: date(2026, 10, 19))
    keyboard = main._calendar_keyboard(2026, 10)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "delivery:date:2026-10-19" for button in buttons)
    assert any(button.callback_data == "delivery:calendar:2026-09" for button in buttons)
    assert any(button.callback_data == "delivery:calendar:2026-11" for button in buttons)
    assert any(button.text == "តុលា ២០២៦" for button in buttons)
    assert any(button.callback_data == "delivery:calendar:back" for button in buttons)


@pytest.mark.asyncio
async def test_calendar_date_selection_advances_to_note_and_preserves_iso_date(monkeypatch):
    monkeypatch.setattr(main, "_phnom_penh_today", lambda: date(2026, 10, 19))
    state = FakeState(DeliveryFlow.date.state)
    message = FakeMessage()
    callback = fake_callback("delivery:date:2026-10-18", message)

    await main.select_delivery_calendar_date(callback, state)

    assert state.data["delivery_date"] == "2026-10-18"
    assert state.current == DeliveryFlow.note.state
    assert "សូមបញ្ចូលកំណត់ចំណាំ ប្រសិនបើមាន៖" in message.answers[0][0]


@pytest.mark.asyncio
async def test_today_button_uses_cambodia_date_and_moves_to_note(monkeypatch):
    today = date(2026, 10, 19)
    monkeypatch.setattr(main, "_phnom_penh_today", lambda: today)
    state = FakeState(DeliveryFlow.date.state)
    message = FakeMessage()

    await main.select_delivery_today(fake_callback("delivery:today", message), state)

    assert state.data["delivery_date"] == today.isoformat()
    assert state.current == DeliveryFlow.note.state
    assert message.answers[0][0] == "សូមបញ្ចូលកំណត់ចំណាំ ប្រសិនបើមាន៖"


@pytest.mark.asyncio
async def test_calendar_month_navigation_renders_requested_month(monkeypatch):
    monkeypatch.setattr(main, "_phnom_penh_today", lambda: date(2026, 10, 19))
    state = FakeState(DeliveryFlow.date.state)
    message = FakeMessage()

    await main.navigate_delivery_calendar(
        fake_callback("delivery:calendar:2026-11", message),
        state,
    )

    message.edit_text.assert_awaited_once()
    assert "វិច្ឆិកា ២០២៦" in message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_calendar_back_returns_to_today_or_another_date_choices():
    state = FakeState(DeliveryFlow.date.state)
    message = FakeMessage()

    await main.back_to_delivery_date_choices(
        fake_callback("delivery:calendar:back", message),
        state,
    )

    message.edit_text.assert_awaited_once()
    assert message.edit_text.await_args.kwargs["reply_markup"] == main._delivery_date_keyboard()


@pytest.mark.asyncio
async def test_skipping_note_sets_optional_value_and_opens_confirmation():
    state = FakeState(
        DeliveryFlow.note.state,
        {
            "supplier_name": "អ្នកផ្គត់ផ្គង់",
            "roll_type_name": "កាវក្រាស់",
            "quantity": 5,
            "delivery_date": "2026-10-18",
        },
    )
    message = FakeMessage()
    callback = fake_callback("delivery:note:skip", message)

    await main.skip_delivery_note(callback, state)

    assert state.current == DeliveryFlow.confirm.state
    assert state.data["note"] is None
    assert "រំលង" not in str(state.data["note"])
    assert len(message.answers) == 2
    assert "ថ្ងៃទទួល៖ ១៨ តុលា ២០២៦" in message.answers[0][0]


@pytest.mark.asyncio
async def test_entering_real_note_keeps_note_and_delivery_details(monkeypatch):
    state = FakeState(
        DeliveryFlow.note.state,
        {
            "supplier_name": "អ្នកផ្គត់ផ្គង់",
            "roll_type_name": "កាវស្ដើង",
            "quantity": 8,
            "delivery_date": "2026-10-18",
        },
    )
    monkeypatch.setattr(main, "_linked_or_reply", AsyncMock(return_value={"linked": True}))
    message = FakeMessage("កំណត់ចំណាំពិត")

    await main.enter_delivery_note(message, state)

    assert state.current == DeliveryFlow.confirm.state
    assert state.data["note"] == "កំណត់ចំណាំពិត"
    assert state.data["quantity"] == 8
    assert "កំណត់ចំណាំ៖ កំណត់ចំណាំពិត" in message.answers[0][0]


@pytest.mark.asyncio
async def test_cancel_callback_clears_current_operation():
    state = FakeState(DeliveryFlow.note.state, {"delivery_date": "2026-10-18"})
    message = FakeMessage()

    await main.cancel_callback(fake_callback("flow:cancel", message), state)

    assert state.current is None
    assert state.data == {}
    assert "បានបោះបង់សកម្មភាព។" in message.answers[0][0]


def test_payment_date_keyboard_paginates_and_offers_all_dates():
    dates = [date(2026, 10, day).isoformat() for day in range(1, 12)]
    keyboard = main._payment_date_keyboard(dates, stage="start", page=0)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert sum(button.callback_data.startswith("payment:start:2026-") for button in buttons) == 8
    assert buttons[0].callback_data == "payment:start:2026-10-11"
    assert any(button.callback_data == "payment:page:start:1" for button in buttons)
    assert any(
        button.callback_data == "payment:all" and button.text == "សម្រាប់ទាំងអស់"
        for button in buttons
    )
    assert any(button.callback_data == "payment:back:roll_type" for button in buttons)
    assert any(button.callback_data == "flow:cancel" for button in buttons)


def test_empty_payment_date_keyboard_keeps_all_and_navigation_actions():
    keyboard = main._payment_date_keyboard([], stage="start")
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert any(button.callback_data == "payment:all" for button in buttons)
    assert any(button.callback_data == "payment:back:roll_type" for button in buttons)
    assert any(button.callback_data == "flow:cancel" for button in buttons)


@pytest.mark.asyncio
async def test_payment_date_pagination_displays_older_real_dates():
    dates = [date(2026, 10, day).isoformat() for day in range(1, 12)]
    state = FakeState(PaymentFlow.start_date.state, {"payment_dates": dates})
    message = FakeMessage()

    await main.navigate_payment_dates(
        fake_callback("payment:page:start:1", message),
        state,
    )

    assert state.data["payment_start_page"] == 1
    markup = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("payment:start:")
    ]
    assert callbacks == [
        "payment:start:2026-10-03",
        "payment:start:2026-10-02",
        "payment:start:2026-10-01",
    ]


@pytest.mark.asyncio
async def test_payment_date_buttons_use_selected_or_unrestricted_delivery_filter(monkeypatch):
    available = ["2026-10-13", "2026-10-14", "2026-10-15"]
    state = FakeState(
        PaymentFlow.start_date.state,
        {"payment_dates": available, "supplier_id": 3, "roll_type_id": 7},
    )
    message = FakeMessage()
    selected_start = fake_callback("payment:start:2026-10-14", message)

    await main.select_payment_start_date(selected_start, state)

    assert state.data["start_date"] == "2026-10-14"
    assert state.current == PaymentFlow.end_date.state
    assert main._payment_date_options(state.data, "end") == ["2026-10-15", "2026-10-14"]

    preview = AsyncMock()
    monkeypatch.setattr(main, "_preview_payment_selection", preview)
    selected_end = fake_callback("payment:end:2026-10-15", message)
    await main.select_payment_end_date(selected_end, state)
    preview.assert_awaited_once_with(message, state, 1234, "2026-10-14", "2026-10-15")

    selected_all = fake_callback("payment:all", message)
    await main.select_all_payment_dates(selected_all, state)
    assert preview.await_args_list[-1].args == (message, state, 1234, None, None)


@pytest.mark.asyncio
async def test_unrestricted_backend_request_omits_empty_date_query_parameters(monkeypatch):
    queries = []

    async def handler(request):
        queries.append(request.url.query.decode())
        return httpx.Response(200, json={"totals": {"unpaid": 0}})

    client = httpx.AsyncClient(
        base_url="http://backend",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(main, "_client", client)
    try:
        await main._request(
            "GET",
            "/api/bot/payments/unpaid",
            telegram_user_id=1234,
            params={
                "supplier_id": 3,
                "roll_type_id": 7,
                "start_date": None,
                "end_date": None,
            },
        )
    finally:
        await client.aclose()

    assert queries == ["supplier_id=3&roll_type_id=7&telegram_user_id=1234"]


@pytest.mark.asyncio
async def test_repeated_delivery_confirmation_does_not_create_another_delivery(monkeypatch):
    state = FakeState(
        DeliveryFlow.confirm.state,
        {
            "supplier_id": 1,
            "roll_type_id": 2,
            "quantity": 5,
            "delivery_date": "2026-10-18",
            "note": None,
            "idempotency_key": "delivery-key",
        },
    )
    message = FakeMessage()
    callback = fake_callback("delivery:confirm", message)
    request = AsyncMock(
        return_value={
            "delivery": {
                "supplier_name": "អ្នកផ្គត់ផ្គង់",
                "roll_type_name": "កាវក្រាស់",
                "quantity_received": 5,
                "delivery_date": "2026-10-18",
            }
        }
    )
    monkeypatch.setattr(main, "_principal", AsyncMock(return_value={"linked": True}))
    monkeypatch.setattr(main, "_request", request)

    await main.confirm_delivery(callback, state)
    await main.confirm_delivery(callback, state)

    request.assert_awaited_once()
    assert request.await_args.kwargs["payload"]["delivery_date"] == "2026-10-18"
    assert request.await_args.kwargs["payload"]["note"] is None
    assert state.current is None


@pytest.mark.asyncio
async def test_payment_confirmation_preserves_roll_type_and_selected_range(monkeypatch):
    state = FakeState(
        PaymentFlow.confirm.state,
        {
            "supplier_id": 3,
            "roll_type_id": 7,
            "start_date": "2026-10-14",
            "end_date": "2026-10-15",
            "idempotency_key": "payment-key",
        },
    )
    request = AsyncMock(
        return_value={
            "reference": "PAY-1",
            "supplier_name": "អ្នកផ្គត់ផ្គង់",
            "total_quantity": 6,
        }
    )
    monkeypatch.setattr(
        main,
        "_principal",
        AsyncMock(return_value={"permissions": {"can_confirm_payments": True}}),
    )
    monkeypatch.setattr(main, "_request", request)

    await main.confirm_payment(
        fake_callback("payment:confirm", FakeMessage()),
        state,
    )

    payload = request.await_args.kwargs["payload"]
    assert payload["roll_type_id"] == 7
    assert payload["start_date"] == "2026-10-14"
    assert payload["end_date"] == "2026-10-15"
    assert state.current is None
