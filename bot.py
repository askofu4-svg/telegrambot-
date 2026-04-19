import asyncio
import logging
import os
import time
from queue import Queue
from threading import Thread
from typing import Dict, Set

import requests
from flask import Flask, jsonify, request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
telegram_app = None
paid_users: Set[int] = set()
pending_payments: Dict[str, Dict[str, object]] = {}
message_queue: Queue = Queue()

ENTER_PHONE = 1


def build_start_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ I Agree — Proceed to Pay KES 300", callback_data="pay")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_try_again_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Try Again", callback_data="try_again")]]
    )


def is_valid_kenyan_number(phone: str) -> bool:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return (
        (phone.startswith("07") and len(digits) == 10)
        or (phone.startswith("2547") and len(digits) == 12)
        or (phone.startswith("01") and len(digits) == 10)
    )


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())

    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]

    if digits.startswith("254") and len(digits) == 12:
        return digits

    if digits.startswith("01") and len(digits) == 10:
        return digits

    raise ValueError(
        "Invalid number. Please enter a valid Safaricom number in format 07XXXXXXXX or 01xxxxxxxx"
    )


def build_hashback_payload(phone_number: str, amount: int, chat_id: int) -> Dict[str, object]:
    reference = f"ref-{chat_id}-{int(time.time())}"
    return {
        "api_key": config.HASHBACK_API_KEY,
        "account_id": config.HASHBACK_MERCHANT_CODE,
        "amount": str(amount),
        "msisdn": phone_number,
        "reference": reference,
    }


def request_stk_push(phone_number: str, amount: int, chat_id: int) -> Dict[str, object]:
    headers = {
        "Content-Type": "application/json",
    }
    payload = build_hashback_payload(phone_number, amount, chat_id)
    response = requests.post(
        config.HASHBACK_API_URL, json=payload, headers=headers, timeout=30
    )
    response.raise_for_status()
    return response.json()


async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id in paid_users:
        await update.message.reply_text(
            "✅ You already have access to Kenya Political Desk Premium. Here is your channel link:"
        )
        await update.message.reply_text(config.PREMIUM_CHANNEL_INVITE)
        return

    await update.message.reply_text(
        "🇰🇪 Welcome to KENYA POLITICAL DESK — Premium Intelligence Network\n\n"
        "This is a strictly private and exclusive channel dedicated to in-depth political analysis, insider briefings, and strategic forecasts leading up to the 2027 General Elections.\n\n"
        "What you get access to:\n"
        "🔍 Classified political breakdowns\n"
        "📊 2027 election predictions and analysis  \n"
        "🎯 Insider moves from key political figures\n"
        "🔥 Uncensored discussions you won't find anywhere else\n"
        "👥 A community of serious Kenyan political minds\n\n"
        "⚠️ Disclaimer: This channel contains sensitive political opinions and analysis. By proceeding to join you agree to respect all members, maintain confidentiality of shared content, and acknowledge that all analysis is opinion-based.\n\n"
        "This intelligence does not come free. Serious members only.\n\n"
        "One time access fee: KES 300"
    )
    await update.message.reply_text("👇 Choose an option below to proceed:", reply_markup=build_start_keyboard())


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(
            "You have cancelled. Type /start anytime to begin again."
        )
        return ConversationHandler.END

    if query.data == "try_again":
        await query.edit_message_text(
            "🇰🇪 Welcome to KENYA POLITICAL DESK — Premium Intelligence Network\n\n"
            "This is a strictly private and exclusive channel dedicated to in-depth political analysis, insider briefings, and strategic forecasts leading up to the 2027 General Elections.\n\n"
            "What you get access to:\n"
            "🔍 Classified political breakdowns\n"
            "📊 2027 election predictions and analysis  \n"
            "🎯 Insider moves from key political figures\n"
            "🔥 Uncensored discussions you won't find anywhere else\n"
            "👥 A community of serious Kenyan political minds\n\n"
            "⚠️ Disclaimer: This channel contains sensitive political opinions and analysis. By proceeding to join you agree to respect all members, maintain confidentiality of shared content, and acknowledge that all analysis is opinion-based.\n\n"
            "This intelligence does not come free. Serious members only.\n\n"
            "One time access fee: KES 300",
            reply_markup=build_start_keyboard(),
        )
        return ConversationHandler.END

    if query.data == "pay":
        await query.edit_message_text(
            "Please enter your M-Pesa phone number below in format 07XXXXXXXX or 2547XXXXXXXX"
        )
        return ENTER_PHONE

    return ConversationHandler.END


async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_raw = update.message.text.strip()
    if not is_valid_kenyan_number(phone_raw):
        await update.message.reply_text(
            "Invalid number. Please enter a valid Safaricom number in format 07XXXXXXXX or 01xxxxxxxx"
        )
        return ENTER_PHONE

    try:
        phone_number = normalize_phone(phone_raw)
    except ValueError:
        await update.message.reply_text(
            "Invalid number. Please enter a valid Safaricom number in format 07XXXXXXXX or 01xxxxxxxx"
        )
        return ENTER_PHONE

    amount = config.PREMIUM_AMOUNT
    await update.message.reply_text(
        "⏳ STK Push sent to your number. Please check your phone and enter your M-Pesa PIN to complete payment."
    )

    try:
        result = request_stk_push(phone_number, amount, update.effective_chat.id)
    except Exception as exc:
        logger.error("STK Push request failed: %s", exc, exc_info=True)
        await update.message.reply_text(
            "Sorry, the payment request could not be sent. Please try again later."
        )
        return ConversationHandler.END

    transaction_reference = (
        result.get("transaction_reference")
        or result.get("transactionReference")
        or result.get("reference")
    )
    if transaction_reference:
        pending_payments[transaction_reference] = {
            "chat_id": update.effective_chat.id,
            "user_id": update.effective_user.id,
            "amount": amount,
            "phone_number": phone_number,
        }

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Payment flow cancelled. Send /start anytime to begin again.")
    return ConversationHandler.END


@app.route("/payment_callback", methods=["POST"])
def payment_callback() -> object:
    data = request.get_json(force=True)
    logger.info("Received payment callback: %s", data)

    transaction_reference = (
        data.get("TransactionReference")
        or data.get("transaction_reference")
        or data.get("transactionReference")
        or data.get("reference")
    )
    status = data.get("ResponseCode") if "ResponseCode" in data else (data.get("status") or data.get("ResultCode"))
    description = data.get("ResponseDescription") or data.get("status_message") or data.get("ResultDesc") or "No description provided."

    if not transaction_reference or transaction_reference not in pending_payments:
        return jsonify({"success": True, "message": "Unknown transaction reference."}), 200

    payment = pending_payments.pop(transaction_reference)
    chat_id = payment["chat_id"]
    user_id = payment["user_id"]
    amount = payment["amount"]

    if str(status) == "0" or str(status).lower() == "success":
        paid_users.add(user_id)
        message_queue.put({
            "chat_id": chat_id,
            "user_id": user_id,
            "success": True,
        })
    else:
        message_queue.put({
            "chat_id": chat_id,
            "user_id": user_id,
            "success": False,
        })

    return jsonify({"success": True}), 200


async def process_message_queue() -> None:
    """Process messages from Flask callback queue in the async context."""
    while True:
        await asyncio.sleep(1)
        while not message_queue.empty():
            msg = message_queue.get()
            chat_id = msg["chat_id"]
            user_id = msg["user_id"]
            try:
                if msg["success"]:
                    paid_users.add(user_id)
                    success_text = (
                        "✅ Payment Confirmed!\n\n"
                        "Welcome to Kenya Political Desk Premium. You now have full lifetime access.\n\n"
                        "Tap the link below to join your exclusive channel immediately:"
                    )
                    await telegram_app.bot.send_message(chat_id=chat_id, text=success_text)
                    await telegram_app.bot.send_message(chat_id=chat_id, text=config.PREMIUM_CHANNEL_INVITE)
                else:
                    failure_text = (
                        "❌ Payment was not completed. This could be due to insufficient funds, wrong PIN, or timeout."
                    )
                    await telegram_app.bot.send_message(
                        chat_id=chat_id,
                        text=failure_text,
                        reply_markup=build_try_again_keyboard(),
                    )
            except Exception as e:
                logger.error("Failed to send message from queue: %s", e)


def run_flask() -> None:
    app.run(host="0.0.0.0", port=5000, debug=False)


async def start_bot() -> None:
    config.validate_environment()

    global telegram_app
    telegram_app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_button, pattern="^(pay|cancel|try_again)$")],
        states={
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    telegram_app.add_handler(CommandHandler("start", send_welcome))
    telegram_app.add_handler(conv_handler)

    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start queue processor in same event loop
    asyncio.ensure_future(process_message_queue())

    logger.info("Starting Telegram bot polling and callback server...")
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )
    # Keep running forever
    await asyncio.Event().wait()


def main() -> None:
    asyncio.run(start_bot())


if __name__ == "__main__":
    main()
