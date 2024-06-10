import os
import random
import re
import sqlite3
import time
import threading
from datetime import date

import discord
from discord.ext import commands
from dotenv import load_dotenv
from ossapi import Ossapi, UserCompact, UserLookupKey
from flask import Flask, jsonify

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Bot Setup

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='>', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')

# db setup

con = sqlite3.connect("score.db")

con.cursor().execute(
    "CREATE TABLE IF NOT EXISTS registered_users"
    "(discord_id PRIMARY KEY, osu_user_id UNIQUE, osu_user_name)"
)
con.commit()

con.cursor().execute(
    "CREATE TABLE IF NOT EXISTS history"
    "(osu_user_id, date, osu_user_name, ranked_score, PRIMARY KEY (osu_user_id, date))"
)
con.commit()

con.cursor().execute(
    "CREATE TABLE IF NOT EXISTS start_score"
    "(osu_user_id PRIMARY KEY, osu_user_name, starting_ranked_score)"
)
con.commit()

# ossapi setup

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

api = Ossapi(CLIENT_ID, CLIENT_SECRET)  # type: ignore


# Bot Commands

@bot.command()
async def register(ctx: commands.Context, arg: str):
    if (ctx.author.id != 262833401051086858):
        await ctx.send(f"Unauthorized.\nLeaked IP: {random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.")
        return

    if not re.match("[1-9][0-9]*", arg):
        await ctx.send('Error : Invalid user ID')
        return

    osu_user_name = api.user(arg, key=UserLookupKey.ID).username

    query = f"""
    INSERT INTO registered_users (discord_id, osu_user_id, osu_user_name) VALUES ({ctx.author.id}, {arg}, '{osu_user_name}')
    ON CONFLICT (discord_id) DO UPDATE SET
        osu_user_id = excluded.osu_user_id,
        osu_user_name = excluded.osu_user_name;
    """
    cur = con.cursor()
    cur.execute(query)
    con.commit()

    await ctx.send(f"Registered user {ctx.author.name} with osu! id {arg} and username {osu_user_name}")

@bot.command()
async def update(ctx: commands.Context):
    if (ctx.author.id != 262833401051086858):
        await ctx.send(f"Unauthorized.\nLeaked IP: {random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.")
        return

    query = f"""SELECT osu_user_id FROM registered_users WHERE discord_id = {ctx.author.id}"""
    cur = con.cursor()
    cur.execute(query)
    result: list = cur.fetchall()

    if len(result) == 0:
        await ctx.send("Error : osu user id not found. Please register");
        return

    osu_user_id, = result[0]

    user = api.user(osu_user_id, key=UserLookupKey.ID)
    osu_user_name = user.username
    statistics = user.statistics
    if statistics is None:
        await ctx.send("Shit hit the fan")
        return

    query = f"""
    INSERT INTO history ( osu_user_id ,   date          ,   osu_user_name  ,             ranked_score )
                 VALUES ({osu_user_id}, '{date.today()}', '{osu_user_name}', {statistics.ranked_score})
    ON CONFLICT (osu_user_id, date) DO UPDATE SET
        ranked_score = excluded.ranked_score;
    """

    print(query)

    cur = con.cursor()
    cur.execute(query)
    con.commit()


def update_all_players(con: sqlite3.Connection):
    query = f"""SELECT osu_user_id FROM registered_users"""
    cur = con.cursor()
    cur.execute(query)
    result: list = cur.fetchall()

    if len(result) == 0:
        print("[Update All Players] Error: no results from player ids query")
        return

    users: list[UserCompact] = list()

    for i in range((len(result) - 1) // 50 + 1):
        request_list: list[int] = list()
        for osu_user_id, in result[i*50:(i+1)*50]:
            request_list.append(osu_user_id)
        users += api.users(request_list)

    for user in users:
        if (user.statistics_rulesets == None or user.statistics_rulesets.osu == None) :
            print(f"Shit hit the fan. None statistics_rulesets(.osu) for player {user.id} ({user.username})")
            continue
        query = f"""
        INSERT INTO history ( osu_user_id ,   date          ,   osu_user_name  ,                               ranked_score )
                     VALUES ({user.id}    , '{date.today()}', '{user.username}', {user.statistics_rulesets.osu.ranked_score})
        ON CONFLICT (osu_user_id, date) DO UPDATE SET
            ranked_score = excluded.ranked_score;
        """
        cur.execute(query)
    con.commit()

def updateIndefinitely():
    localcon = sqlite3.connect("score.db")
    while True:
        update_all_players(localcon)
        time.sleep(60)

@bot.command()
async def updateAll(ctx: commands.Context):
    if (ctx.author.id != 262833401051086858):
        await ctx.send(f"Unauthorized.\nLeaked IP: {random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.")
        return
    update_all_players(con)

@bot.command()
async def getRegistrations(ctx: commands.Context):
    if (ctx.author.id != 262833401051086858):
        await ctx.send(f"Unauthorized.\nLeaked IP: {random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.")
        return

    discord_osu_ids: list[tuple[int, int]] = list()
    channel = bot.get_channel(1241815392922636388)
    messages = channel.history(limit=200) #type: ignore
    async for message in messages:
        match = re.search(r"u(sers)?/[a-zA-Z0-9]+", message.content)
        if match is None:
            print("\nFUCK\n", message.content, "\n")
            continue
        string = message.content[match.start():match.end()].split("/")[1]
        id = 0
        if string == "atsuuu":
            id = 13798356
        else:
            id = int(string)
        discord_osu_ids.append((message.author.id, id))

    for discord_id, osu_id in discord_osu_ids:
        osu_user_name = api.user(osu_id, key=UserLookupKey.ID).username

        # For trail mix and umbre, will figure out how they access the bot later
        if discord_id == 793331642801324063 and osu_id != 8513384:
            discord_id = osu_id

        query = f"""
        INSERT INTO registered_users (discord_id, osu_user_id, osu_user_name) VALUES ({discord_id}, {osu_id}, '{osu_user_name}')
        ON CONFLICT (discord_id) DO UPDATE SET
            osu_user_id = excluded.osu_user_id,
            osu_user_name = excluded.osu_user_name;
        """
        cur = con.cursor()
        cur.execute(query)
    con.commit()

@bot.command()
async def setStartingScore(ctx: commands.Context):
    if (ctx.author.id != 262833401051086858):
        await ctx.send(f"Unauthorized.\nLeaked IP: {random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.")
        return

    cur = con.cursor()
    with open("startscore.csv") as csvfile:
        for line in csvfile.readlines():
            [username, userid, startingscore] = line.split(',')

            query = f"""
            INSERT INTO start_score (  osu_user_id, osu_user_name, starting_ranked_score)
                             VALUES ({int(userid)},  '{username}',  {int(startingscore)})
            """
            cur.execute(query)

    con.commit()

@bot.command(aliases=['lb'])
async def leaderboard(ctx: commands.Context):
    query = f"""
    select discord_id, registered_users.osu_user_name, ranked_score - starting_ranked_score as gain
        from start_score 
        join (select osu_user_id, max(ranked_score) as ranked_score from history group by osu_user_id) maxes
        on start_score.osu_user_id = maxes.osu_user_id
        join registered_users on registered_users.osu_user_id = start_score.osu_user_id
        order by gain desc
    """

    result = list()

    cur = con.cursor()
    cur.execute(query)
    result = cur.fetchall()

    if len(result) == 0:
        await ctx.send("No Result")
        return

    sender_rank = 0
    for index, (discord_id, _, _) in enumerate(result):
        if discord_id == ctx.author.id:
            sender_rank = index
            break

    embed = discord.Embed(title=f"Gained Score Leaderboard")

    lb_string = "```css\n"
    for index, row in enumerate(result[0:10]):

        rank = "#" + "{:<2}".format(index+1)
        username = "{:15}".format(row[1])
        thousand_separated_total_score = "{:,}".format(int(row[2]))
        total_score = "{:>15}".format(thousand_separated_total_score)

        row_string = f"{rank}| {username}|{total_score}\n"
        lb_string += row_string

    NUM_PLAYERS_DIRECTLY_ABOVE = 3
    if sender_rank >= 10:
        lb_string += "...\n"
        for index, row in enumerate(result[max(10,sender_rank - NUM_PLAYERS_DIRECTLY_ABOVE):sender_rank+1]):

            rank = "#" + "{:<2}".format(index+1+sender_rank-NUM_PLAYERS_DIRECTLY_ABOVE)
            username = "{:15}".format(row[1])
            thousand_separated_total_score = "{:,}".format(int(row[2]))
            total_score = "{:>15}".format(thousand_separated_total_score)

            row_string = f"{rank}| {username}|{total_score}\n"
            lb_string += row_string

    lb_string += "```"

    embed.description = lb_string

    await ctx.send(embed=embed)

# Fun


@bot.command()
async def meow(ctx: commands.Context):
    await ctx.send("https://cdn.discordapp.com/emojis/1086007780957241364.gif?size=128&quality=lossless")


@bot.command()
async def barack(ctx: commands.Context):
    await ctx.send("https://cdn.discordapp.com/attachments/750265305258786870/1133087258149392634/FzuaWTAaMAIjL5Z.png")

app = Flask(__name__)

@app.route("/")
def index():
    localcon = sqlite3.connect("score.db")
    query = f"""
    select start_score.osu_user_id, registered_users.osu_user_name, ranked_score - starting_ranked_score as gain
        from start_score 
        join (select osu_user_id, max(ranked_score) as ranked_score from history group by osu_user_id) maxes
        on start_score.osu_user_id = maxes.osu_user_id
        join registered_users on registered_users.osu_user_id = start_score.osu_user_id
        order by gain desc
    """

    result = list()

    cur = localcon.cursor()
    cur.execute(query)
    result = cur.fetchall()

    if len(result) == 0:
        print("No Result")
        return jsonify(dict())

    data = dict()
    for (osu_user_id, username, ranked_score) in result:
        data[osu_user_id] = (username, ranked_score)

    return jsonify(data)

def run_api():
    app.run(host='127.0.0.1', port=24707)

def run_bot():
    bot.run(BOT_TOKEN)  # type: ignore

if __name__ == "__main__":
    apiThread = threading.Thread(target=run_api)
    apiThread.start()
    updateThread = threading.Thread(target=updateIndefinitely)
    updateThread.start()
    botThread = threading.Thread(target=run_bot)
    botThread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        apiThread.join()
        updateThread.join()
        botThread.join()

