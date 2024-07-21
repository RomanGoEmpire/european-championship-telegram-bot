import os
import re
import datetime

import telegram
from icecream import ic
from dotenv import load_dotenv
from surrealdb import Surreal
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)


# - - - - - DB - - - - -

DB = Surreal("ws://localhost:8000/rpc")
ADMIN_ID = os.getenv("admin_id")

GAME, WINNER, AMOUNT = range(3)
REMOVE_BET = 3


async def connect():
    await DB.connect()
    await DB.signin({"user": "root", "pass": "root"})
    await DB.use("test", "test")


async def add_message(user_id: int, message_id: int, data: dict) -> None:
    await connect()
    await DB.create(f"message:{message_id}", data)
    await DB.query(f"RELATE gambler:{user_id}->wrote->message:{message_id}")
    await DB.close()


# - - - - - Telegram Bot - - - - -


def init_bot():
    load_dotenv()
    TOKEN = os.getenv("TOKEN")
    assert TOKEN and TOKEN != "", "Token missing"

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("setname", setname))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("matches", matches))
    application.add_handler(CommandHandler("match", match))

    bet_handler = ConversationHandler(
        entry_points=[CommandHandler("bet", bet)],  # choose a game
        states={
            GAME: [MessageHandler(filters.TEXT, game)],  # choose a winner
            WINNER: [MessageHandler(filters=None, callback=winner)],  # choose an amount
            AMOUNT: [MessageHandler(None, set_bet)],
        },
        fallbacks=[],
        name="bet_handler",
    )
    remove_handler = ConversationHandler(
        entry_points=[CommandHandler("remove", remove)],  # choose game
        states={
            REMOVE_BET: [
                MessageHandler(filters.TEXT, display_remove)
            ],  # Display remove
        },
        fallbacks=[],
        name="bet_handler",
    )
    application.add_handler(bet_handler)
    application.add_handler(remove_handler)

    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    application.add_error_handler(error)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_message(update._effective_user.id, update.update_id, update.to_dict())
    await connect()
    gambler = await DB.select(f"gambler:{update.effective_user.id}")
    if not gambler:
        await DB.create(
            f"gambler:{update.effective_user.id}",
            data={"name": update.effective_user.username},
        )
    await DB.close()

    start_text = """Get ready to place your bets and follow the exciting battles of the European Go Championship!

🏆 The top three players with the highest points after the finals will receive a prize.

*Format:*
- Each player starts with 1,000 points.
- Place your bets on your favorite players with /bet.

❗ To change the name that will be displayed on the leaderboard, use the command /setname name.

ℹ️ To learn more about the available commands and features, start by typing /help.

Let's get started, and may the best player win! 🚀
"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=start_text, parse_mode="markdown"
    )


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🔍 *Profile*
/profile - View your current balance, pending bets and betting history

💬 *Change Name*
/setname _newname_ - Set your Name (Default is your Telegram name)

🏆 *Leaderboard*
/leaderboard - View the current leaderboard of all players

🥊 *Open Matches*
/matches - List all matches that are currently open for betting

🎲 *Match Information*
/match _matchnumber_ - Retrieve detailed information about a match

🎯 *Place a Bet*
/bet _matchnumber_ _player_ _points_ - Place a bet on a player in a match

❌ *Remove a Bet*
/removebet _matchnumber_ - Cancel a bet on a match
"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=help_text, parse_mode="markdown"
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect()
    gambler = await DB.select(f"gambler:{update.effective_user.id}")
    await DB.close()

    active_bets = None
    previous_bets = None

    profile_text = f"""
*Name:* {gambler["name"]}
*Balance:* {gambler["balance"]}

*Active Bets:*
{active_bets}

*Previous Bets:*
{previous_bets}
"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=profile_text, parse_mode="markdown"
    )


async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please provide a name.\nExample: /setname MyName",
            parse_mode="markdown",
        )
        return

    name = " ".join(context.args)
    await connect()
    await DB.query(f'UPDATE gambler:{update.effective_user.id} SET name="{name}"')
    await DB.close()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ Your name was updated to '{name}'",
        parse_mode="markdown",
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect()
    gamblers = await DB.select("gambler")
    await DB.close()

    leaderboard_text = "🏆 *Leaderboard*\n\n"
    leaderboard_position = 0
    for index, gambler in enumerate(gamblers):
        if gambler["id"] == f"gambler:{update.effective_user.id}":
            leaderboard_position = index + 1
        if index == 0:
            leaderboard_text += "*Top 3*\n"
            leaderboard_text += "🥇 "
        elif index == 1:
            leaderboard_text += "🥈 "
        elif index == 2:
            leaderboard_text += "🥉 "
        else:
            if index == 3:
                leaderboard_text += "\n*Top 100*\n"
            if index == 99:
                leaderboard_text += "\n*Placement above 100*\n"
            leaderboard_text += f"{index + 1}: "
        leaderboard_text += f"{gambler["name"]} - {gambler["balance"]}\n"
    leaderboard_text += f"\n\nYou are *{leaderboard_position}* with *{gamblers[leaderboard_position -1]["balance"]}* points"
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=leaderboard_text, parse_mode="markdown"
    )


async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect()
    matches = await DB.query(
        "SELECT *,round.*,<-plays.in.* as players FROM match where round.active"
    )
    await DB.close()
    matches = matches[0]["result"]
    matches_text = "🥊 *Open Matches*\n ℹ️ These games are open for betting.\n\n"
    for match in matches:
        player1_name = match["players"][0]["name"]
        player1_rank = match["players"][0]["rank"]
        player2_name = match["players"][1]["name"]
        player2_rank = match["players"][1]["rank"]
        matches_text += f"""*Match: {match["id"].split(":")[-1]}*
    {player1_name} {player1_rank} vs.
    {player2_name} {player2_rank}

"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=matches_text, parse_mode="markdown"
    )


async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please provide a match number.\nExample: /match 1",
        )
        return

    match_id = int(context.args[0])

    if not valid_match_id(match_id):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Match {match_id} does not exist.\nUse /matches to get a list of valid matches.",
        )
        return

    await connect()
    match = await DB.query(
        f"SELECT *,round.*,<-plays<-player.* as players,<-bets.* as bets,winner.name as winner FROM match:{match_id}"
    )
    match = match[0]["result"][0]

    if len(match["players"]) != 2:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Match {match_id} does not have two players yet.\nUse /matches to get a list of valid matches.",
        )
        return

    player1, player2 = match["players"]

    payout1 = sum(
        [bet["amount"] for bet in match["bets"] if bet["player"] == player1["id"]]
    )
    payout2 = sum(
        [bet["amount"] for bet in match["bets"] if bet["player"] == player2["id"]]
    )

    odds = match["odds"]
    if payout1 == 0 or payout2 == 0:
        current_payout = (
            f"{1 + round(odds[1]/odds[0],2)} : {1 + round(odds[0]/odds[1],2)}"
        )
    else:
        current_payout = (
            f"{1 + round(payout2/payout1,2)} : {1 + round(payout1/payout2,2)}"
        )

    winner = f"Winner: {match["winner"]}" if match["winner"] else ""

    time_left = (
        convert_string_to_datetime(match["round"]["deadline"]) - datetime.datetime.now()
    )
    if time_left.total_seconds() > 0:
        closing_time = f"Bet closes in: {(time_left.total_seconds() - time_left.seconds)// 3600 } hours {(time_left.seconds // 60) % 60} minutes"
    else:
        closing_time = "Bets are closed for this round."

    match_text = f"""🎲 *Match Information*
Match: {match_id}
{match["round"]["name"]}

Players:
    {player1["name"]} {player1["rank"]} ({player1["elo"]}) vs.
    {player2["name"]} {player2["rank"]} ({player2["elo"]})

Odds: {odds[0] * 100:.2f}% , {odds[1] * 100:.2f}%
Current payout: {current_payout}

{winner}

{closing_time}
"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=match_text,
        parse_mode="markdown",
    )


async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect()
    matches = await DB.query(
        f"SELECT *,round.*,<-plays.in.* as players FROM match where round.active"
    )
    matches = matches[0]["result"]
    keyboard = ReplyKeyboardMarkup(
        [
            [
                f"{match["players"][0]["name"]} vs {match["players"][1]["name"]}",
            ]
            for match in matches
        ],
        one_time_keyboard=True,
    )
    context.user_data["matches"] = matches
    await update.message.reply_text(
        "Choose a game to place your bet", reply_markup=keyboard
    )
    return GAME


async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player1_name, player2_name = update.message.text.split(" vs ")
    context.user_data["match"] = [
        match
        for match in context.user_data["matches"]
        if all(
            player["name"] in [player1_name, player2_name]
            for player in match["players"]
        )
    ][0]
    del context.user_data["matches"]

    existing_bet = await DB.query(
        f"select * from bets where in == gambler:{update.effective_user.id} and out=={context.user_data["match"]["id"]}"
    )
    existing_bet = existing_bet[0]["result"]

    actions = [[player1_name, player2_name]]
    if existing_bet:
        context.user_data["existing_bet"] = existing_bet[0]

        actions.append(["Stop"])
        await update.message.reply_text(
            "ℹ️There is already a bet. You can override it by continuing or stopping it."
        )

    keyboard = ReplyKeyboardMarkup(
        actions,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "Choose the player you want to bet on", reply_markup=keyboard
    )
    return WINNER


async def winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Stop":
        return ConversationHandler.END

    context.user_data["winner"] = update.message.text

    await connect()
    existing_bet = context.user_data.get("existing_bet")
    if existing_bet:
        await DB.query(
            f"DELETE bets where in == gambler:{update.effective_user.id} and out=={context.user_data["match"]["id"]}"
        )
        await DB.query(
            f"UPDATE gambler:{update.effective_user.id} set balance+={existing_bet["amount"]}"
        )
        await update.message.reply_text(f"ℹ️ Your existing bet refunded.")

    gambler = await DB.select(f"gambler:{update.effective_user.id}")
    await DB.close()

    context.user_data["gambler"] = gambler

    await update.message.reply_text(
        f"Your Balance: {gambler["balance"]}.\nHow much do you want to bet?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AMOUNT


async def set_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gambler = context.user_data["gambler"]
    match = context.user_data["match"]

    bet_amount = update.message.text

    if not bet_amount.isdigit():
        await update.message.reply_text(
            f"Please enter a number between 0 and {gambler["balance"]}"
        )
        return AMOUNT
    bet_amount = int(bet_amount)
    if bet_amount < 0 or bet_amount > gambler["balance"]:
        await update.message.reply_text(
            f"Please enter a number between 0 and {gambler["balance"]}"
        )
        return AMOUNT

    winner = next(
        player
        for player in match["players"]
        if player["name"] == context.user_data["winner"]
    )
    await connect()

    await DB.query(
        f"RELATE gambler:{update.effective_user.id}->bets->{match["id"]} SET amount={bet_amount},winner={winner["id"]}"
    )
    await DB.query(
        f"UPDATE gambler:{update.effective_user.id} set balance-={bet_amount}"
    )
    await DB.close()
    await update.message.reply_text(
        f"✅ Your bet as accepted. \n\nMatch: {match["id"].split(":")[-1]}\nPlayer: {winner["name"]}\nAmount: {bet_amount}"
    )
    return ConversationHandler.END


async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect()
    bets = await DB.query(
        f"SELECT *,out.round.* AS round, player.name as winner, out<-plays<-player.name as players, in.balance as balance FROM bets WHERE in==gambler:{update.effective_user.id}"
    )
    await DB.close()

    bets = bets[0]["result"]
    bets = list(
        filter(
            lambda bet: convert_string_to_datetime(bet["round"]["deadline"])
            > datetime.datetime.now()
            and bet["round"]["active"],
            bets,
        )
    )

    if not bets:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There are no bets you can remove.",
        )
        return ConversationHandler.END

    context.user_data["bets"] = bets
    keyboard = ReplyKeyboardMarkup(
        [
            [
                (
                    f"({bet["players"][0]}) vs {bet["players"][1]} - {bet["amount"]}"
                    if bet["winner"] == bet["players"][0]
                    else f"{bet["players"][0]} vs ({bet["players"][1]}) - {bet["amount"]}"
                ),
            ]
            for bet in bets
        ],
        one_time_keyboard=True,
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Select the match you want to remove",
        reply_markup=keyboard,
    )
    return REMOVE_BET


async def display_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    remove_text = update.message.text.split(" -")[0]

    player1_name, player2_name = re.sub(r"[()]", "", remove_text).split(" vs ")

    bet = [
        bet
        for bet in context.user_data["bets"]
        if all(player in [player1_name, player2_name] for player in bet["players"])
    ][0]

    await connect()
    gambler = await DB.select(f"gambler:{user_id}")
    await DB.query(f"UPDATE gambler:{user_id} set balance+={bet["amount"]}")
    await DB.delete(f"{bet["id"]}")
    await DB.close()
    await update.message.reply_text(
        text=f"✅ Your bet for Match {bet["out"].split(":")[-1]} was removed and {bet["amount"]} where added back to your balance.\n\nYour new balance is {bet["balance"] + bet["amount"]}"
    )
    return ConversationHandler.END


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
    await add_message(update._effective_user.id, update.update_id, update.to_dict())
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"An error occurred. Please try again. The admin has been notified and will work to resolve the problem.",
    )
    await context.bot.send_message(
        chat_id=str(ADMIN_ID),
        text=f"{update.update_id}",
    )


def is_admin(user_id: int) -> bool:
    return ADMIN_ID == user_id


def valid_match_id(match_id: int) -> bool:
    return match_id > 0 and match_id <= 60


def convert_string_to_datetime(date_string) -> datetime.datetime:
    return datetime.datetime.fromisoformat(date_string).replace(tzinfo=None)
