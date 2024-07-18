import os
import logging
import asyncio
from requests.exceptions import ContentDecodingError
import telegram
from icecream import ic
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from .database import add_gambler, add_message


def init_bot():
    load_dotenv()
    token = os.getenv("token")
    assert token and token != "", "Token missing"
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    application.add_error_handler(error)
    application.run_polling()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_message(update.update_id, update.to_dict())

    await add_gambler(update.effective_user.id, update.effective_user.username)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"HEllo",
    )


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """Bot Commands:
    *Information*
    /info - Display information about this bot

    *Leaderboard*
    /leaderboard - View the current leaderboard of all players

    *Match Odds*
    /odds _match number_ - Retrieve the odds for a specific match

    *Place a Bet*
    /bet _match number_ _player_ _points_ - Place a bet on a player in a match

    *Remove a Bet*
    /removebet _match number_ - Cancel a bet on a match

    Open Matches
    /matches - List all matches that are currently open for betting
    """

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=help_text, parse_mode="markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("/"):
        message = "It seems like you are trying to use a command that doesn't exists.\n"
    else:
        message = "Please use the provided commands.\n"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{message}If you need assistance, use the /help command to access all relevant commands.",
    )


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ic(f"Update {update} caused error {context.error}")
