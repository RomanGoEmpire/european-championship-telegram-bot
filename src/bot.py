import os
import re
import datetime

from dotenv import load_dotenv
import telegram
from icecream import ic
from surrealdb import Surreal
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)
from .formulars import win_percentages
from .messages import (
    START_TEXT,
    HELP_TEXT,
    ME_TEXT,
    INFO_TEXT,
    EXISTING_BET_TEXT,
    CORRECT_GUESS,
    WRONG_GUESS,
    TOURNAMENT_END_TEXT,
)

from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning
)


# - - - - - DB - - - - -

load_dotenv()
DB = Surreal("ws://localhost:8000/rpc")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
USER = os.getenv("SURREAL_USER")
PASSWORD = os.getenv("SURREAL_PASSWORD")


async def connect():

    await DB.connect()
    await DB.signin({"user": USER, "pass": PASSWORD})
    await DB.use("main", "main")


async def get_gambler(id: int):
    await connect()
    gambler = await DB.select(f"gambler:{id}")
    await DB.close()
    return gambler


async def add_message(user_id: int, update_id: int, update: Update):
    await connect()
    await DB.create(
        "message",
        data={
            "gambler": f"gambler:{user_id}",
            "chat_id": update_id,
            "data": str(update),
        },
    )
    await DB.close()


async def get_active_matches() -> list:
    await connect()
    active_games = await DB.query(
        "SELECT *,<-plays<-player.* as players,round.* FROM match WHERE round.active"
    )
    await DB.close()
    return active_games[0]["result"]


async def get_payout(match_id):
    await connect()
    bets = await DB.query(
        f"SELECT *,out.odds as odds,out<-plays<-player.* AS players FROM bets WHERE out=={match_id}"
    )
    bets = bets[0]["result"]
    if not bets:
        match = await DB.select(match_id)
        await DB.close()
        odds = match["odds"]
        return (round(1 + odds[1] / odds[0], 2), round(1 + odds[0] / odds[1], 2))
    await DB.close()
    players = bets[0]["players"]
    odds = bets[0]["odds"]
    player_amounts = [
        sum(bet["amount"] for bet in bets if bet["winner"] == players[0]["id"]),
        sum(bet["amount"] for bet in bets if bet["winner"] == players[1]["id"]),
    ]

    if 0 in player_amounts:
        return (round(1 + odds[1] / odds[0], 2), round(1 + odds[0] / odds[1], 2))
    else:
        return (
            round(1 + player_amounts[1] / player_amounts[0], 2),
            round(1 + player_amounts[0] / player_amounts[1], 2),
        )


# - - - - - Telegram Bot - - - - -

GAME, WINNER, AMOUNT = range(3)
REMOVE_BET = range(1)
CHANGE_NAME = range(1)
ADMIN_GAME, ADMIN_WINNER = range(2)


def init_bot():

    TOKEN = os.getenv("TOKEN")
    assert TOKEN and TOKEN != "", "Token missing"

    application = ApplicationBuilder().token(TOKEN).build()

    bet_handler = ConversationHandler(
        entry_points=[CommandHandler("bet", bet)],
        states={
            GAME: [
                CallbackQueryHandler(game, pattern="^match"),
            ],
            WINNER: [
                CallbackQueryHandler(winner, pattern="^player"),
            ],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_bet)],
        },
        fallbacks=[
            CallbackQueryHandler(stop_bet_button, pattern="^stop"),
            MessageHandler(filters.TEXT | filters.COMMAND, stop_bet),
        ],
        name="bet_handler",
    )
    remove_handler = ConversationHandler(
        entry_points=[CommandHandler("remove", remove)],
        states={REMOVE_BET: [CallbackQueryHandler(display_remove, pattern="^bets")]},
        fallbacks=[
            CallbackQueryHandler(stop_remove_button, pattern="^stop_remove"),
            MessageHandler(filters.TEXT | filters.COMMAND, stop_remove),
        ],
        name="bet_handler",
    )
    admin_hanlder = ConversationHandler(
        entry_points=[CommandHandler("winner", admin_set_winner)],
        states={
            ADMIN_GAME: [
                CallbackQueryHandler(admin_game, pattern="^match"),
            ],
            ADMIN_WINNER: [
                CallbackQueryHandler(admin_winner, pattern="^player"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(stop_admin_button, pattern="^stop"),
        ],
        name="admin_handler",
    )

    application.add_handler(bet_handler)
    application.add_handler(remove_handler)
    application.add_handler(admin_hanlder)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("changename", changename))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("info", info))

    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    # application.add_error_handler(error)

    ic("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    id = update.effective_user.id
    gambler = await get_gambler(id)
    if not gambler:
        await connect()
        username = update.effective_user.full_name
        if username is None:
            username = "unknown user"
        chat_id = update.message.chat_id

        await DB.create(
            f"gambler:{id}",
            data={"name": username, "username": username, "chat_id": chat_id},
        )
        await DB.close()
    await update.message.reply_text(START_TEXT, parse_mode="markdown")


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="markdown")


async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gambler = await get_gambler(update.effective_user.id)
    assert type(gambler) == dict, "gambler is not a dict"

    await connect()
    active_bets = await DB.query(
        f"SELECT *,winner.name as winner,out<-plays<-player.* as players,out.winner as actual_winner FROM bets where in=={gambler["id"]} and actual_winner is None"
    )
    active_bets = active_bets[0]["result"]
    active_bets_text = "\n".join(
        [
            f"{bet["players"][0]["name"]} vs {bet["players"][1]["name"]}\n🎯 Place {bet["amount"]} on {bet["winner"]}\n"
            for bet in active_bets
        ]
    )
    await update.message.reply_text(
        ME_TEXT.format(
            name=gambler["name"],
            balance=gambler["balance"],
            active_bets=active_bets_text,
        ),
        parse_mode="markdown",
    )


async def changename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Please provide a name.\nExample: /changename NewName",
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
    gamblers.sort(key=lambda gambler: gambler["balance"], reverse=True)
    await DB.close()

    leaderboard_text = "🏆 *Leaderboard*\n\n"
    leaderboard_position = 0
    for index, gambler in enumerate(gamblers):
        if gambler["id"] == f"gambler:{update.effective_user.id}":
            leaderboard_position = index + 1
        if index == 0:
            leaderboard_text += "🥇 "
        elif index == 1:
            leaderboard_text += "🥈 "
        elif index == 2:
            leaderboard_text += "🥉 "
        else:
            leaderboard_text += f"{index + 1}: "
        leaderboard_text += f"{gambler["name"]} - {gambler["balance"]}\n"
    leaderboard_text += f"\n\nYou are *{leaderboard_position}.* with *{gamblers[leaderboard_position -1]["balance"]}* points"
    await update.message.reply_text(leaderboard_text, parse_mode="markdown")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    def convert_seconds(seconds):
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours}:{minutes}:{seconds}"

    active_matches = await get_active_matches()
    round_name = active_matches[0]["round"]["name"]
    deadline = convert_string_to_datetime(active_matches[0]["round"]["deadline"])
    payouts = [await get_payout(match["id"]) for match in active_matches]
    time_left = (deadline - datetime.datetime.now()).total_seconds()

    if time_left < 0:
        time_left_text = "🔒 Bets are closed for this round"
    else:
        time_left_text = f"⏰ Time left: {convert_seconds(time_left)}"

    matches = "\n".join(
        [
            f"""*Match {match["id"].split(":")[-1]}*
    {match["players"][0]["name"]} {match["players"][0]["rank"]} ({match["players"][0]["elo"]}) vs
    {match["players"][1]["name"]} {match["players"][1]["rank"]} ({match["players"][1]["elo"]})

    Odds: {match["odds"][0] * 100:.2f}% , {match["odds"][1] * 100:.2f}%
    Current Payout: {payouts[index][0]} : {payouts[index][1]}
    """
            for index, match in enumerate(active_matches)
        ]
    )

    await update.message.reply_text(
        INFO_TEXT.format(
            round_name=round_name, matches=matches, time_left=time_left_text
        ),
        parse_mode="markdown",
    )


async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect()
    matches = await DB.query(
        f"SELECT *,round.*,<-plays.in.* as players FROM match where round.active and round.deadline > time::now()"
    )
    matches = matches[0]["result"]

    if not matches:
        await update.message.reply_text("🎲 There are no bets open at the moment.")
        return ConversationHandler.END

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{match["players"][0]["name"]} vs {match["players"][1]["name"]}",
                callback_data=match["id"],
            )
        ]
        for match in matches
    ]
    buttons.append([InlineKeyboardButton(text="Stop", callback_data="stop")])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        "Choose a game to place your bet", reply_markup=keyboard
    )
    return GAME


async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_id = update.callback_query.data
    context.user_data["match_id"] = match_id

    existing_bet = await DB.query(
        f"SELECT *,winner.name as winner from bets where in == gambler:{update.effective_user.id} and out=={match_id}"
    )
    existing_bet = existing_bet[0]["result"]

    await connect()
    if existing_bet:
        await DB.delete(existing_bet[0]["id"])
        await DB.query(
            f"UPDATE gambler:{update.effective_user.id} SET balance+={existing_bet[0]["amount"]}"
        )
        context.user_data["existing_bet"] = existing_bet
    match = await DB.query(f"SELECT *,round.*,<-plays.in.* as players FROM {match_id}")
    match = match[0]["result"][0]
    payout = await get_payout(match["id"])

    await DB.close()
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{match["players"][0]["name"]} {match["players"][0]["rank"]}",
                callback_data=match["players"][0]["id"],
            ),
            InlineKeyboardButton(
                text=f"{match["players"][1]["name"]} {match["players"][1]["rank"]}",
                callback_data=match["players"][1]["id"],
            ),
        ]
    ]
    buttons.append([InlineKeyboardButton(text="Stop", callback_data="stop")])
    keyboard = InlineKeyboardMarkup(buttons)

    game_text = f"Select the player you want to bet on.\nOdds: {match["odds"][0] * 100:.2f}% , {match["odds"][1] * 100:.2f}%\nCurrent Payout: {payout[0]} : {payout[1]}"

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(game_text, reply_markup=keyboard)
    return WINNER


async def winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    winner_id = update.callback_query.data
    context.user_data["winner_id"] = winner_id

    await connect()
    gambler = await DB.select(f"gambler:{update.effective_user.id}")
    await DB.close()

    context.user_data["gambler"] = gambler

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        f"Your Balance: {gambler["balance"]}.\nHow much do you want to bet?",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(text="Stop", callback_data="stop")]]
        ),
    )
    return AMOUNT


async def set_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_id = context.user_data["match_id"]
    gambler = context.user_data["gambler"]
    winner_id = context.user_data["winner_id"]

    bet_amount = update.message.text

    if not bet_amount.isdigit():
        await update.message.reply_text(
            f"🚨 Please enter a number between 0 and {gambler["balance"]}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="Stop", callback_data="stop")]]
            ),
        )
        return AMOUNT

    bet_amount = int(bet_amount)
    if bet_amount <= 0 or bet_amount > gambler["balance"]:
        await update.message.reply_text(
            f"🚨 Please enter a number between 0 and {gambler["balance"]}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="Stop", callback_data="stop")]]
            ),
        )
        return AMOUNT

    await connect()
    await DB.query(
        f"RELATE {gambler["id"]}->bets->{match_id} SET amount={bet_amount},winner={winner_id}"
    )
    await DB.query(
        f"UPDATE gambler:{update.effective_user.id} set balance-={bet_amount}"
    )
    player = await DB.select(winner_id)
    await DB.close()

    await update.message.reply_text(
        f"✅ Your bet as accepted. \n\nMatch: {match_id.split(":")[-1]}\nPlayer: {player["name"]}\nAmount: {bet_amount}"
    )
    return ConversationHandler.END


async def stop_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("existing_bet"):
        await update.message.reply_text(EXISTING_BET_TEXT)

    await update.message.reply_text("Bet was interrupted")
    return ConversationHandler.END


async def stop_bet_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("existing_bet"):
        await update.message.reply_text(EXISTING_BET_TEXT)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Bet was interrupted")
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

    buttons = [
        [
            (
                InlineKeyboardButton(
                    (
                        f"({bet["players"][0]}) vs {bet["players"][1]} - {bet["amount"]}"
                        if bet["winner"] == bet["players"][0]
                        else f"{bet["players"][0]} vs ({bet["players"][1]}) - {bet["amount"]}"
                    ),
                    callback_data=bet["id"],
                )
            ),
        ]
        for bet in bets
    ]

    buttons.append([InlineKeyboardButton(text="Stop", callback_data="stop_remove")])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        text="Select the match you want to remove",
        reply_markup=keyboard,
    )
    return REMOVE_BET


async def display_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bet_id = update.callback_query.data
    await connect()
    bet: dict = await DB.select(bet_id)
    gambler: dict = await DB.select(f"gambler:{user_id}")
    await DB.query(f"UPDATE gambler:{user_id} set balance+={bet["amount"]}")
    await DB.delete(bet["id"])
    await DB.close()
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=f"✅ Your bet for Match {bet["out"].split(":")[-1]} was removed and {bet["amount"]} where added back to your balance.\nYour new balance is {gambler["balance"] + bet["amount"]}."
    )
    return ConversationHandler.END


async def stop_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Remove bet was interrupted")
    return ConversationHandler.END


async def stop_remove_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Remove bet was interrupted")
    return ConversationHandler.END


async def admin_set_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    await connect()
    matches = await DB.query(
        f"SELECT *,round.*,<-plays.in.* as players FROM match where round.active and winner is None"
    )
    matches = matches[0]["result"]

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{match["players"][0]["name"]} vs {match["players"][1]["name"]}",
                callback_data=match["id"],
            )
        ]
        for match in matches
    ]
    buttons.append([InlineKeyboardButton(text="Stop", callback_data="stop")])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.message.reply_text("Which game finished", reply_markup=keyboard)
    return ADMIN_GAME


async def admin_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    match_id = update.callback_query.data

    await connect()
    match = await DB.query(f"SELECT *,round.*,<-plays.in.* as players FROM {match_id}")
    await DB.close()

    match = match[0]["result"][0]
    context.user_data["admin_match"] = match

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{match["players"][0]["name"]} {match["players"][0]["rank"]}",
                callback_data=match["players"][0]["id"],
            ),
            InlineKeyboardButton(
                text=f"{match["players"][1]["name"]} {match["players"][1]["rank"]}",
                callback_data=match["players"][1]["id"],
            ),
        ],
        [InlineKeyboardButton(text="Stop", callback_data="stop")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Select Winner", reply_markup=keyboard
    )
    return ADMIN_WINNER


async def admin_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    winner_id = update.callback_query.data
    match = context.user_data["admin_match"]
    del context.user_data["admin_match"]

    looser_id = (
        match["players"][0]["id"]
        if match["players"][0]["id"] != winner_id
        else match["players"][1]["id"]
    )
    await connect()
    winner: dict = await DB.select(winner_id)
    looser: dict = await DB.select(looser_id)

    await DB.query(f"UPDATE {match["id"]} SET winner={winner_id},looser={looser_id}")
    if match.get("next_match_for_winner"):
        await DB.query(f"RELATE {winner_id}->plays->{match["next_match_for_winner"]}")
    if match.get("next_match_for_looser"):
        await DB.query(f"RELATE {looser_id}->plays->{match["next_match_for_looser"]}")

    # get all bets
    bets = await DB.query(
        f"SELECT *,in.* as gambler,winner.* as winner FROM bets WHERE out=={match["id"]}"
    )
    bets = bets[0]["result"]
    winner_amount, looser_amount = (
        sum(bet["amount"] for bet in bets if bet["winner"]["id"] == winner_id),
        sum(bet["amount"] for bet in bets if bet["winner"]["id"] == looser_id),
    )

    payouts = await get_payout(match["id"])
    index_payout = next(
        (i for i, player in enumerate(match["players"]) if player["id"] == winner_id),
        -1,
    )
    assert index_payout != -1, " index is -1 "
    payout = payouts[index_payout]

    await connect()
    for bet in bets:
        if bet["winner"]["id"] == winner_id:
            message = CORRECT_GUESS
            amount_difference = round(bet["amount"] * payout)
            await DB.query(f"UPDATE {bet["in"]} SET balance+={amount_difference}")

        else:
            message = WRONG_GUESS
            amount_difference = bet["amount"]

        gambler: dict = await DB.select(bet["in"])
        await context.bot.send_message(
            chat_id=bet["gambler"]["chat_id"],
            text=message.format(
                match_id=match["id"].split(":")[-1],
                players=f"{match["players"][0]["name"]} {match["players"][0]["rank"]} vs {match["players"][1]["name"]} {match["players"][1]["rank"]}",
                winner=winner["name"],
                payouts=f"{payouts[0]} : {payouts[1]}",
                bet_amount=bet["amount"],
                guessed_winner=bet["winner"]["name"],
                amount=amount_difference,
                balance=gambler["balance"],
            ),
        )

    ongoing_matches = await DB.query(
        "select *,round.* from match where round.active and winner is None"
    )
    ongoing_matches = ongoing_matches[0]["result"]

    if not ongoing_matches:

        active_round = await DB.query("select * from round where active")
        active_round = active_round[0]["result"][0]

        await DB.query(f"UPDATE {active_round["id"]} set active=False")
        round_number = int(active_round["id"].split(":")[-1])
        if round_number != 8:
            await DB.query(f"UPDATE round:{round_number + 1} set active=True")

        await add_odds()

        gamblers = await DB.select("gambler")

        if active_round["id"] != "round:8":
            end_of_round_text = f"""
            🌟 {active_round["name"]} has ended!

            You received 50 points.

            The bets are now open for the next round.
            Use /bet to start placing bets, or check your new balance with the /me.
            Good luck to everyone in the next round!
            """
        else:
            champion = await DB.query("SELECT *,winner.* as winner FROM match:59")
            champion = champion[0]["result"][0]
            end_of_round_text = TOURNAMENT_END_TEXT.format(
                champion=champion["winner"]["name"]
            )

        for gambler in gamblers:
            if active_round["id"] != "round:8":
                await DB.query(f"UPDATE {gambler["id"]} SET balance+=50")
            await context.bot.send_message(
                chat_id=gambler["chat_id"], text=end_of_round_text
            )

    await DB.close()
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("✅ Winner selected")
    return ConversationHandler.END


async def stop_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Stopped selection of winner")
    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("/"):
        message = "It seems like you are trying to use a command that doesn't exists.\n"
    else:
        message = "Please use the provided commands.\n"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{message}If you need assistance, use the /help csommand to access all relevant commands.",
    )


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 An error occurred. Please try again. The admin has been notified and will work to resolve the problem.",
    )

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🚨🚨🚨 An error happended in {update.update_id} for user {update.effective_user.id}",
    )
    await add_message(update.effective_user.id, update.update_id, update)


# - - - - - Utils - - - - -


def is_admin(user_id: int) -> bool:
    return ADMIN_ID == user_id


def convert_string_to_datetime(date_string) -> datetime.datetime:
    return datetime.datetime.fromisoformat(date_string).replace(tzinfo=None)


async def add_odds() -> None:
    matches = await DB.query(
        "select *,<-plays<-player.elo as elo, <-plays<-player.name as name from match where round.active"
    )
    matches = list(filter(lambda x: len(x["elo"]) > 0, matches[0]["result"]))

    for match in matches:
        r1, r2 = match["elo"]
        p1, p2 = win_percentages(r1, r2)
        await DB.query(f"UPDATE {match["id"]} set odds={[p1,p2]}")
