START_TEXT = """
Get ready to place your bets and follow the exciting battles of the European Go Championship!

*Format*
- Each player starts with 1,000 points.
- After each round each player will receive 50 points.
- Place your bets on players with /bet.
- Player that guessed the winners will receive a payout. Check out /me to see your balance and bets.

🏆 The best participants will receive a prize after the finals.

❗ To change the name that will be displayed on the leaderboard, use the command /changename name.

ℹ️ To learn more about the available commands and features, start by typing /help.

Let's get started! 🚀
"""

HELP_TEXT = """
💬 *Change Name*
/changename _newname_ - Change your Name (Default is your Telegram name)

🔍 *Account Information*
/me - View your name,current balance, active bets and betting history

🏆 *Leaderboard*
/leaderboard - View the current leaderboard of all players

🎲 *Match Information*
/info - Retrieve detailed information about the matches

🎯 *Place a Bet*
/bet - Place a bet

❌ *Remove a Bet*
/remove - Remove a bet
"""

ME_TEXT = """
🔍 *Profile*

Name: {name}
Balance: {balance}

*Active bets:*
{active_bets}
"""

INFO_TEXT = """
🎲 *Match Information for {round_name}*

{matches}

{time_left}
"""

EXISTING_BET_TEXT = "ℹ️ You had placed a bet on this game, but since you attempted to create a new bet, your original bet was refunded. Please use /me to see your bets"

CORRECT_GUESS = """
🎉 Your guess for Match {match_id} was correct!

Game: {players}
Winner: {winner}
Payouts: {payouts}
Your bet was: {bet_amount} on {guessed_winner}

You won {amount} and your balance is now {balance}!
"""

WRONG_GUESS = """
😞 Your guess for Match {match_id} was incorrect.

Game:  {players}
Winner: {winner}
Payouts: {payouts}
Your bet was: {bet_amount} on {guessed_winner}

You lost {bet_amount} and your balance is now {balance}.
"""

TOURNAMENT_END_TEXT = """
🌟 The European Championship 2024 has concluded!

After eight thrilling days of competition, we bid farewell to this year's European Go Championship.
We extend our gratitude to all the participants for their involvement in this exhilarating event.

Congratulations to our champion, *{champion}*, who emerged victorious in the final match!

🏆 Please check out /leaderboard to see your final placement.

We hope you enjoyed this exciting competition. Have a wonderful second week of EGC!
"""
