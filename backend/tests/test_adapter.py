"""Adapter normalisation tests — no live Green API account required.

Covers: text message, image message, non-message notification (status update),
empty polling response, and the webhook-payload path.
"""

from __future__ import annotations

import pytest

from app.adapters.whatsapp.green_api import GreenApiAdapter
from app.adapters.whatsapp.base import IncomingMessage

INSTANCE_ID = "1234567890"
TOKEN = "fake-token-for-tests"

# Shared adapter instance (no API calls made in these tests).
adapter = GreenApiAdapter(INSTANCE_ID, TOKEN)


# ------------------------------------------------------------------
# Sample Green API payloads
# ------------------------------------------------------------------

TEXT_NOTIFICATION = {
    "receiptId": 10001,
    "body": {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": int(INSTANCE_ID)},
        "timestamp": 1700000000,
        "idMessage": "BAEF1234ABCD",
        "senderData": {
            "chatId": "972501234567@c.us",
            "sender": "972501234567@c.us",
            "chatName": "Alice",
        },
        "messageData": {
            "typeMessage": "textMessage",
            "textMessageData": {"textMessage": "שלום! יש לכם ספה לבנה?"},
        },
    },
}

IMAGE_NOTIFICATION = {
    "receiptId": 10002,
    "body": {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": int(INSTANCE_ID)},
        "timestamp": 1700000001,
        "idMessage": "BAEF5678EFGH",
        "senderData": {
            "chatId": "972501234567@c.us",
            "sender": "972501234567@c.us",
        },
        "messageData": {
            "typeMessage": "imageMessage",
            "fileMessageData": {
                "downloadUrl": "https://cdn.greenapi.com/img/photo.jpg",
                "caption": "Is this available?",
                "mimeType": "image/jpeg",
            },
        },
    },
}

EXTENDED_TEXT_NOTIFICATION = {
    "receiptId": 10004,
    "body": {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": int(INSTANCE_ID)},
        "timestamp": 1700000002,
        "idMessage": "BAEF9999ZZZZ",
        "senderData": {
            "chatId": "972545495209@c.us",
            "sender": "972545495209@c.us",
        },
        "messageData": {
            "typeMessage": "extendedTextMessage",
            "extendedTextMessageData": {"text": "שלום"},
        },
    },
}

STATUS_NOTIFICATION = {
    "receiptId": 10003,
    "body": {
        "typeWebhook": "outgoingMessageStatus",
        "idMessage": "BAEFXXX",
        "status": "delivered",
    },
}

# Webhook payload — same as the polling body but without the outer wrapper.
WEBHOOK_TEXT_BODY = TEXT_NOTIFICATION["body"]


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_text_message_normalised():
    msg = adapter.normalize_polling_notification(TEXT_NOTIFICATION)
    assert msg is not None
    assert isinstance(msg, IncomingMessage)
    assert msg.type == "text"
    assert msg.text == "שלום! יש לכם ספה לבנה?"
    assert msg.chat_id == "972501234567@c.us"
    assert msg.message_id == "BAEF1234ABCD"
    assert msg.notification_id == 10001
    assert msg.instance_id == INSTANCE_ID


def test_image_message_normalised():
    msg = adapter.normalize_polling_notification(IMAGE_NOTIFICATION)
    assert msg is not None
    assert msg.type == "image"
    assert msg.media_url == "https://cdn.greenapi.com/img/photo.jpg"
    assert msg.caption == "Is this available?"
    assert msg.notification_id == 10002


def test_extended_text_message_normalised():
    msg = adapter.normalize_polling_notification(EXTENDED_TEXT_NOTIFICATION)
    assert msg is not None
    assert msg.type == "text"
    assert msg.text == "שלום"
    assert msg.chat_id == "972545495209@c.us"
    assert msg.message_id == "BAEF9999ZZZZ"


def test_non_message_notification_returns_none():
    msg = adapter.normalize_polling_notification(STATUS_NOTIFICATION)
    assert msg is None


def test_empty_body_returns_none():
    msg = adapter.normalize_polling_notification({})
    assert msg is None


def test_webhook_text_normalised():
    msg = adapter.normalize_webhook_payload(WEBHOOK_TEXT_BODY)
    assert msg is not None
    assert msg.type == "text"
    assert msg.text == "שלום! יש לכם ספה לבנה?"
    assert msg.notification_id is None  # webhook has no receiptId


def test_webhook_non_message_returns_none():
    msg = adapter.normalize_webhook_payload({"typeWebhook": "outgoingMessageStatus"})
    assert msg is None
