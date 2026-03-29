from dotenv import load_dotenv
import os
import discord
import io
from discord import app_commands
import sqlite3
import json
import base64
import zlib
from urllib.parse import quote
from datetime import date, datetime, timedelta
import time as timemodule
from splits import splits_formatted as getsplits
from marathon import getMarathons
from typing import Literal

load_dotenv()

#usage: python bot.py

#reqs:
#pip install python-dotenv discord.py

#CONFIG (use .env file)
#─────────────────────────────────────────────────────────────
token = os.getenv("BOT_TOKEN")
# Discord bot token (KEEP SECRET)
# Get it from: https://discord.com/developers/applications/
# Never share or commit this anywhere

db_path = os.getenv("DB_PATH")
# example: "C:/programs/!PROGRAMS/slidysim29/solves.db"
# path to your local slidysim solves database file

YOUR_USER_ID = int(os.getenv("DISCORD_USER_ID"))
# example: "537316990679777280"
# your Discord user ID (right-click username → Copy ID)
# used to restrict commands so only you can run them

# ─────────────────────────────────────────────────────────────
# IMPORTANT: Replay / file hosting setup (REQUIRED)
# ─────────────────────────────────────────────────────────────
# This project DOES NOT store replays in the bot itself.
# Instead, it saves replay files into a GitHub repository you own,
# and generates a public link using GitHub Pages.
#
# You must create your own repo for this system to work.
#
# Example reference setup:
# https://github.com/dphdmn/mytextfiles
# (see index.html for redirect logic)
#
# You need:
# 1. A GitHub repository (your own copy of the template repo)
# 2. GitHub Pages enabled for that repo
# 3. A local clone of the repo on your PC (using git!)
# ─────────────────────────────────────────────────────────────

REPO_NAME = os.getenv("TXT_REPO_NAME")
# example: "mytextfiles"
# your GitHub repository name used for storing replay files

LOCAL_PATH = os.getenv("TXT_REPO_LOCAL_PATH")
# example: "C:/Users/dphdmn/Documents"
# parent folder that contains cloned GitHub repo on your computer

GITHUB = os.getenv("TXT_REPO_GITHUB")
# example: "https://dphdmn.github.io"
# your GitHub Pages domain (must match your repo setup)

SUBFOLDERS = os.getenv("TXT_REPO_SUBFOLDERS")
# example: "slidy/generated"
# folder inside the repo where replay files are saved

# If you do not want to set up your own text files repository:
# You can modify the save_replay_and_generate_url function instead.
# Or modify other functions to send txt files instead of creating URLs
#─────────────────────────────────────────────────────────────

REPO_LOCAL_DIR = os.path.join(LOCAL_PATH, REPO_NAME)
GENERATED_DIR = os.path.join(REPO_LOCAL_DIR, SUBFOLDERS)

def save_replay_and_generate_url(file_content: str, filename: str) -> str:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    filepath = os.path.join(GENERATED_DIR, filename)

    # Save file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(file_content)

    # Git operations
    try:
        os.chdir(REPO_LOCAL_DIR)
        os.system("git add .")
        os.system(f'git commit -m "update {filename}"')
        os.system("git push -u origin main")
    except Exception as e:
        raise RuntimeError(f"Git error: {e}")

    # Generate URL
    return f"{GITHUB}/{REPO_NAME}/index.html?url={REPO_NAME}/{SUBFOLDERS}/{filename}"


def encodeURIComponent(string):
    return ''.join(c if c.isalnum() or c in ['-', '_', '.', '~'] else f"%{ord(c):02X}" for c in string)

def compress_array_to_string(input_array):
    json_string = json.dumps(input_array)
    compressed_data = zlib.compress(json_string.encode(), level=9)
    base64_encoded_string = base64.b64encode(compressed_data).decode()
    return encodeURIComponent(base64_encoded_string)

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

@client.tree.command(description="Get best marathon splits for NxM puzzles")
@app_commands.describe(puzzle_size="Puzzle size in NxM format (e.g. 3x3)")
async def marathons(interaction: discord.Interaction, puzzle_size: str):
    """Get the best cumulative times for each split across all marathons of specified puzzle size"""
    await interaction.response.defer(ephemeral=False)
    try:
        # Check if the user is authorized
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return

        # Parse puzzle size
        try:
            width, height = map(int, puzzle_size.lower().split('x'))
            if width <= 0 or height <= 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send(
                "Invalid puzzle size format. Please use format like '6x6' or '3x3'.",
                ephemeral=True
            )
            return

        best_splits = getMarathons(width, height, db_path)

        if not best_splits:
            await interaction.followup.send(
                f"No marathon solves found for {puzzle_size} puzzles.",
                ephemeral=True
            )
            return

        # Format the results
        description = "```\n"
        description += f"{'Split':<6}{'Time':<10}{'From':<14}{'Date':<12}\n"
        description += "-" * 49 + "\n"
        
        for x_num in sorted(best_splits.keys()):
            if x_num > 42:  # Limit to x42 max
                continue
            
            split = best_splits[x_num]
            date_only = datetime.fromtimestamp(split['timestamp'] / 1000).strftime('%Y-%m-%d')
            description += (
                f"x{x_num:<5}{split['time']:>6.3f}  "
                f"{split['fulltime']/1000:>6.3f} x{split['marathon_length']:<7} "
                f"{date_only}\n"
            )
        description += "```"

        # Create embed
        embed = discord.Embed(
            title=f"Best Marathon Splits for {puzzle_size}",
            description=description,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Times are cumulative in seconds")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(
            f"An error occurred: {str(e)}",
            ephemeral=True
        )

@client.tree.command(description="Show your total playtime by puzzle size")
@app_commands.describe(
    timeframe="Optional filter: all (default), last N hours, day, week, or month"
)
async def playtime(interaction: discord.Interaction, timeframe: str = "all"):
    try:
        # Defer the response to prevent timeout
        await interaction.response.defer(ephemeral=False)
        
        # Check if the user is authorized
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Determine time filter condition
        params = []
        usehours = False
        since = None
        since_ms = None

        if timeframe.lower() != "all":
            now = datetime.now()
            
            if timeframe.isdigit():
                # timeframe is a number of hours
                hours = int(timeframe)
                usehours = True
                since = now - timedelta(hours=hours)
            elif timeframe.lower() == "day":
                since = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif timeframe.lower() == "week":
                start_of_week = now - timedelta(days=now.weekday())
                since = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            elif timeframe.lower() == "month":
                since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Convert to milliseconds
            since_ms = int(since.timestamp() * 1000)
            params.append(since_ms)
        else:
            # Use arbitrarily large default timestamp values for "all" case
            since_ms = 0  # Beginning of Unix epoch
            params.append(since_ms)

        # Query 1: Get attempts and playtime
        attempts_query = """
            SELECT 
                ss.width,
                ss.height,
                ROUND(SUM(ss.time) / 3600000.0, 3) AS hours,
                COUNT(*) AS attempts
            FROM single_solves ss
            JOIN solves s ON ss.id BETWEEN s.single_start_id AND s.single_end_id
            WHERE s.scrambler = 'Random permutation'
                AND s.timestamp >= ?
            GROUP BY ss.width, ss.height
        """
        cursor.execute(attempts_query, params)
        attempts_results = {f"{row[0]}x{row[1]}": {"hours": row[2], "attempts": row[3], "width": row[0], "height": row[1]} 
                           for row in cursor.fetchall()}

        # Query 2: Get solves (completed ones)
        solves_query = """
            SELECT 
                ss.width,
                ss.height,
                COUNT(*) AS solves
            FROM single_solves ss
            JOIN solves s ON ss.id BETWEEN s.single_start_id AND s.single_end_id
            WHERE s.scrambler = 'Random permutation'
                AND s.timestamp >= ?
                AND s.completed = 1
                AND (s.success IS NULL OR s.success = 1)
            GROUP BY ss.width, ss.height
        """
        cursor.execute(solves_query, params)
        solves_results = {f"{row[0]}x{row[1]}": row[2] for row in cursor.fetchall()}

        # Query 3: Get skips
        skips_query = """
            SELECT 
                width,
                height,
                COUNT(*) AS skips
            FROM skipped_scrambles
            WHERE scrambler = 'Random permutation'
                AND timestamp >= ?
            GROUP BY width, height
        """
        cursor.execute(skips_query, params)
        skips_results = {f"{row[0]}x{row[1]}": row[2] for row in cursor.fetchall()}

        # Combine all data
        all_puzzles = set(attempts_results.keys()) | set(solves_results.keys()) | set(skips_results.keys())
        
        combined_results = []
        for puzzle_key in all_puzzles:
            puzzle_data = attempts_results.get(puzzle_key, {})
            solves = solves_results.get(puzzle_key, 0)
            skips = skips_results.get(puzzle_key, 0)
            
            combined_results.append({
                "width": puzzle_data.get("width", int(puzzle_key.split('x')[0])),
                "height": puzzle_data.get("height", int(puzzle_key.split('x')[1])),
                "hours": puzzle_data.get("hours", 0),
                "attempts": puzzle_data.get("attempts", 0),
                "solves": solves,
                "skips": skips
            })
        
        # Sort by hours and get top 20
        combined_results.sort(key=lambda x: x["hours"], reverse=True)
        top_results = combined_results[:20]

        if not top_results:
            await interaction.followup.send("No playtime data found.", ephemeral=True)
            return

        # Get total playtime across ALL puzzles
        total_query = """
            SELECT ROUND(SUM(ss.time) / 3600000.0, 3) AS total_hours
            FROM single_solves ss
            JOIN solves s ON ss.id BETWEEN s.single_start_id AND s.single_end_id
            WHERE s.scrambler = 'Random permutation'
                AND s.timestamp >= ?
        """
        cursor.execute(total_query, params)
        total_result = cursor.fetchone()
        total_hours = total_result[0] if total_result[0] else 0
        
        total_minutes = int(total_hours * 60)
        total_h = total_minutes // 60
        total_m = total_minutes % 60
        total_time_str = f"{total_h}:{total_m:02d}"

        if usehours:
            timeframe = f"Last {timeframe} hours"
        else:
            timeframe = timeframe.capitalize() if timeframe.lower() != "all" else "All Time"

        # Create embed
        embed = discord.Embed(
            title=f"🕹️ SlidySim Playtime Summary ({timeframe})",
            color=discord.Color.blurple()
        )

        # Format header row
        table_lines = [" Size |  Time  |Attempts| Solves | Skips", "------|--------|--------|--------|-------"]

        # Format each row
        for row in top_results:
            total_minutes = int(row["hours"] * 60)
            h = total_minutes // 60
            m = total_minutes % 60
            time_str = f"{h}:{m:02d}"
            size = f"{row['width']}x{row['height']}".ljust(5)
            table_lines.append(f"{size} | {time_str:<6} | {row['attempts']:<6} | {row['solves']:<6} | {row['skips']}")

        # Join into a code block
        embed.description = "```\n" + "\n".join(table_lines) + "\n```"
        
        # Add total playtime as footer
        embed.set_footer(text=f"Total playtime across ALL puzzles: {total_time_str}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
    finally:
        if 'conn' in locals():
            conn.close()

@client.tree.command(description="Get your personal best solve for a specific puzzle size")
@app_commands.describe(
    size="Puzzle size in NxM format (e.g., 4x5, 10x18, 5x5)",
    pbtype="Type of personal best to retrieve",
    time_limit="Optional maximum time in seconds",
    moves_limit="Optional maximum moves",
    hours_limit="Optional time window in hours (e.g., 24 for last day)"
)
async def getpb(
    interaction: discord.Interaction,
    size: str,
    pbtype: Literal["time", "moves", "tps"] = "time",
    time_limit: float = None,
    moves_limit: int = None,
    hours_limit: int = None
):
    await interaction.response.defer(ephemeral=False)
    
    try:
        # Check if the user is authorized
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        # Parse size
        try:
            width, height = map(int, size.lower().split('x'))
        except:
            await interaction.followup.send(
                "Invalid size format. Please use NxM format (e.g., 4x5, 10x18).",
                ephemeral=False
            )
            return
        
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Calculate timestamp cutoff if hours_limit is provided
        timestamp_cutoff = None
        if hours_limit is not None:
            timestamp_cutoff = int(timemodule.time() - (hours_limit * 3600)) * 1000
        
        # Build the query based on parameters
        query = """
            SELECT 
                a.id,
                a.time,
                a.moves,
                a.tps,
                a.scramble,
                a.solution,
                a.move_times_start_id,
                a.move_times_end_id,
                b.timestamp,
                a.width,
                a.height
            FROM 
                (single_solves a 
                JOIN solves b 
                ON a.id BETWEEN b.single_start_id AND b.single_end_id) 
            WHERE 
                a.completed = 1 
                AND b.scrambler = 'Random permutation' 
                AND (b.success IS NULL OR b.success = 1)
                AND b.solve_type != 'BLD'
                AND b.display_type = 'Standard'
                AND a.width = ? AND a.height = ?
        """
        
        params = [width, height]
        
        # Add hours_limit filter if provided
        if timestamp_cutoff is not None:
            query += " AND b.timestamp >= ?"
            params.append(timestamp_cutoff)
            
        # Add optional filters
        if time_limit is not None:
            query += " AND a.time < ?"
            params.append(int(time_limit * 1000))
            
        if moves_limit is not None:
            query += " AND a.moves < ?"
            params.append(moves_limit * 1000)
        
        # Add ordering based on pbtype
        if pbtype == "time":
            query += " ORDER BY a.time ASC LIMIT 1"
        elif pbtype == "moves":
            query += " ORDER BY a.moves ASC LIMIT 1"
        elif pbtype == "tps":
            query += " ORDER BY a.tps DESC LIMIT 1"
        
        cursor.execute(query, params)
        solve_row = cursor.fetchone()
        
        if not solve_row:
            size_filter = f" for size {width}x{height}"
            time_filter = f" under {time_limit}s" if time_limit else ""
            moves_filter = f" with moves < {moves_limit}" if moves_limit else ""
            hours_filter = f" in last {hours_limit} hours" if hours_limit else ""
            
            await interaction.followup.send(
                f"No matching solves found{size_filter}{time_filter}{moves_filter}{hours_filter}.",
                ephemeral=False
            )
            return
            
        # Get column names
        column_names = [
            'id', 'time', 'moves', 'tps', 'scramble', 'solution', 
            'move_times_start_id', 'move_times_end_id', 'timestamp', 'width', 'height'
        ]
        row_map = dict(zip(column_names, solve_row))
        
        # Get move times
        starting_point = row_map['move_times_start_id']
        ending_point = row_map['move_times_end_id']
        cursor.execute(
            "SELECT time FROM move_times WHERE id >= ? AND id <= ?", 
            (starting_point, ending_point)
        )
        sequence = [row[0] for row in cursor.fetchall()]
        
        # Format information
        width = row_map['width']
        height = row_map['height']
        time = row_map['time'] / 1000
        moves = int(row_map['moves'] / 1000)
        tps = row_map['tps'] / 1000
        scramble = row_map['scramble']
        solution = row_map['solution']
        timestamp = datetime.fromtimestamp(row_map['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        
        # Generate SlidySim URL
        slidy_url = "https://slidysim.github.io/replay?r=" + compress_array_to_string([solution, row_map['tps'], scramble, sequence])
        splits_data = getsplits(slidy_url)

        url_length = len(slidy_url)
        extra_note = ""  # Only used if >1950

        if url_length <= 512:
            final_link = slidy_url
            use_button = True
        elif url_length <= 1950:
            final_link = slidy_url
            use_button = False
        else:
            timestamp_str = str(int(timemodule.time()))
            filename = f"{timestamp_str}.txt"
            final_link = save_replay_and_generate_url(slidy_url, filename)
            use_button = True
            extra_note = "*Replay may take a minute to activate.*"

        # Create embed
        pb_type_display = {
            "time": f"Fastest Time: {time:.3f}s",
            "moves": f"Fewest Moves: {moves}",
            "tps": f"Highest TPS: {tps:.2f}"
        }[pbtype]

        time_window_info = f" (last {hours_limit} hours)" if hours_limit else ""
        
        # Add filter information
        filter_info = []
        if time_limit is not None:
            filter_info.append(f"Time < {time_limit}s")
        if moves_limit is not None:
            filter_info.append(f"Moves < {moves_limit}")
        if hours_limit is not None:
            filter_info.append(f"Last {hours_limit}h")
            
        filters_applied = ""
        if filter_info:
            filters_applied = "\n**Filters:** " + ", ".join(filter_info)
        
        embed_description = f"""
        **{pb_type_display}{time_window_info}** on {width}x{height}
        **Date:** {timestamp}{filters_applied}
        """
        
        if splits_data != "Invalid splits data":
            embed_description += f"```\n{splits_data}\n```"
        
        if extra_note:
            embed_description += extra_note

        embed = discord.Embed(
            title=f"Personal Best ({pbtype})",
            description=embed_description,
            color=discord.Color.gold()
        )
        
        embed.set_footer(text="Click the button below to view." if use_button else "Link provided above.")

        if use_button:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View on SlidySim", url=final_link, style=discord.ButtonStyle.link))
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        else:
            await interaction.followup.send(content=f"# [View on SlidySim]({final_link})", embed=embed, ephemeral=False)

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}", ephemeral=False)
    finally:
        if 'conn' in locals():
            conn.close()

@client.tree.command(description="Get latest SlidySim solve")
async def latest(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    try:
        # Check if the user is authorized
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get column info
        cursor.execute("PRAGMA table_info(single_solves)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        # Get latest solve
        cursor.execute("SELECT * FROM single_solves ORDER BY id DESC LIMIT 1")
        highest_single_solve_row = cursor.fetchone()
        
        if not highest_single_solve_row:
            await interaction.followup.send("No solves found in database", ephemeral=False)
            return
            
        row_map = dict(zip(column_names, highest_single_solve_row))
        
        # Get move times
        starting_point = row_map['move_times_start_id']
        cursor.execute(f"SELECT time FROM move_times WHERE id >= {starting_point}")
        sequence = [row[0] for row in cursor.fetchall()]
        
        # Format information
        width = row_map['width']
        height = row_map['height']
        time = row_map['time'] / 1000
        moves = int(row_map['moves'] / 1000)
        tps = row_map['tps'] / 1000
        scramble = row_map['scramble']
        solution = row_map['solution']
        
        # Generate SlidySim URL
        slidy_url = "https://slidysim.github.io/replay?r=" + compress_array_to_string([solution, row_map['tps'], scramble, sequence])
        splits_data = getsplits(slidy_url)

        url_length = len(slidy_url)
        timestamp = str(int(timemodule.time()))
        extra_note = ""  # Only used if >1950

        if url_length <= 512:
            final_link = slidy_url
            use_button = True
        elif url_length <= 1950:
            final_link = slidy_url
            use_button = False
        else:
            filename = f"{timestamp}.txt"
            final_link = save_replay_and_generate_url(slidy_url, filename)
            use_button = True
            extra_note = "*Replay may take a minute to activate.*"

        embed_description = f"```\n{splits_data}\n```" if splits_data != "Invalid splits data" else ""
        if extra_note:
            embed_description += extra_note

        embed = discord.Embed(
            title="Latest solve by DPH",
            description=embed_description,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Click the button below to view." if use_button else "Link provided above.")

        if use_button:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View on SlidySim", url=final_link, style=discord.ButtonStyle.link))
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        else:
            await interaction.followup.send(content=f"# [View on SlidySim]({final_link})", embed=embed, ephemeral=False)


        
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}", ephemeral=False)
    finally:
        if 'conn' in locals():
            conn.close()

@client.tree.command(description="Get Splits of Replay File or Text")
@app_commands.describe(
    file="Optional .txt replay file",
    text="Or paste replay text directly here"
)
async def splits(
    interaction: discord.Interaction,
    file: discord.Attachment = None,
    text: str = None
):
    await interaction.response.defer(ephemeral=False)

    try:
        if file:
            if not file.filename.endswith('.txt'):
                await interaction.followup.send("Please upload a .txt file.", ephemeral=True)
                return

            file_content = await file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode('utf-8')

        elif text:
            file_content = text

        else:
            await interaction.followup.send("You must upload a file or provide text.", ephemeral=True)
            return

        # Get splits result
        splits_data = getsplits(file_content)
        if splits_data == "Invalid splits data":
            await interaction.followup.send("Invalid splits data in the provided input.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Replay Splits",
            description=f"```\n{splits_data}\n```",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed, ephemeral=False)

    except Exception as e:
        await interaction.followup.send(f"An error occurred while processing: {str(e)}", ephemeral=True)

    

@client.tree.command(description="Get a short URL one-click button from Replay File")
async def replay(interaction: discord.Interaction, file: discord.Attachment, metadata: str = None):
    ALLOWED_USER_IDS = [YOUR_USER_ID]

    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    if not file.filename.endswith('.txt'):
        await interaction.response.send_message("Please upload a .txt file.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)  # Defer to handle long processing

    timestamp = str(int(timemodule.time()))
    filename = f"{timestamp}.txt"
    file_content = (await file.read()).decode('utf-8')

    try:
        slidy_url = save_replay_and_generate_url(file_content, filename)
    except Exception as e:
        await interaction.followup.send(f"Error saving file or pushing to Git: {str(e)}", ephemeral=True)
        return

    splits_data = getsplits(file_content)

    embed = discord.Embed(
        title=f"🌟 {metadata or 'Replay Link'} 🌟",
        description=f"```\n{splits_data}\n```*Replay may take a minute to activate.*" if splits_data != "Invalid splits data" else "*Replay may take a minute to activate.*",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Click the button below to view.")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="View on SlidySim", url=slidy_url, style=discord.ButtonStyle.link))

    await interaction.followup.send(embed=embed, view=view, ephemeral=False)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

client.run(token)