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
import subprocess
import asyncio
import stats
from discord import app_commands
from power_data import DISPLAY_TYPE_MAP, CONTROL_TYPE_MAP, PB_TYPE_MAP, SOLVE_TYPE_MAP
import re



load_dotenv()

#usage: python bot.py

#reqs:
#pip install python-dotenv discord.py tabulate

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

# Script path (only for web update command)
script_path = os.getenv("UPDATEWEB_SCRIPT_PATH")

REPO_LOCAL_DIR = os.path.join(LOCAL_PATH, REPO_NAME)
GENERATED_DIR = os.path.join(REPO_LOCAL_DIR, SUBFOLDERS)

updateweb_running = False

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

# Add this global variable near the top of your file with other globals
updateweb_running = False

# ======================== PARSE RELAY TYPE ========================

def parse_relay_type(raw: str) -> str:
    """Convert user input to a canonical gameMode name (e.g. 'rel' -> '2-N relay',
    'x10' -> 'Marathon 10')."""
    raw = raw.strip()
    raw_lower = raw.lower()

    # Marathon patterns: "x<num>" or "Marathon <num>"
    m = re.match(r'^x(\d+)$', raw_lower)
    if m:
        return f"Marathon {m.group(1)}"
    m = re.match(r'^marathon\s*(\d+)$', raw_lower)
    if m:
        return f"Marathon {m.group(1)}"

    # Aliases for well‑known relay types
    alias_map = {
        "rel": "2-N relay",
        "relay": "2-N relay",
        "eut": "Everything-up-to relay",
        "everything": "Everything-up-to relay",
        "everything-up-to": "Everything-up-to relay",
        "width": "Width relay",
        "wrel": "Width relay",
        "height": "Height relay",
        "hrel": "Height relay",
        "bld": "BLD",
        "blindfolded": "BLD",
    }
    # exact alias
    if raw_lower in alias_map:
        return alias_map[raw_lower]

    # partial match against SOLVE_TYPE_MAP values (case‑insensitive)
    for name in SOLVE_TYPE_MAP.values():
        if raw_lower in name.lower():
            return name
    # also try if the name is inside the input
    for name in SOLVE_TYPE_MAP.values():
        if name.lower() in raw_lower:
            return name

    # last resort: check for "standard"
    if raw_lower == "standard":
        return "Standard"

    raise ValueError(f"Unknown relay type: '{raw}'. Accepted: Standard, 2-N relay, "
                     "Everything-up-to relay, Width relay, Height relay, BLD, "
                     "Marathon N, xN, rel, eut, width, etc.")

# ======================== AUTOCOMPLETE ========================

async def display_type_autocomplete(interaction, current):
    choices = []
    for name in DISPLAY_TYPE_MAP.values():
        if current.lower() in name.lower():
            choices.append(app_commands.Choice(name=name, value=name))
    return choices[:25]

async def control_type_autocomplete(interaction, current):
    choices = []
    for name in CONTROL_TYPE_MAP.values():
        if current.lower() in name.lower():
            choices.append(app_commands.Choice(name=name, value=name))
    return choices[:25]

async def pb_type_autocomplete(interaction, current):
    choices = []
    for name in PB_TYPE_MAP.values():
        if current.lower() in name.lower():
            choices.append(app_commands.Choice(name=name, value=name))
    return choices[:25]

async def filter_type_autocomplete(interaction, current):
    filter_types = ["NxM singles", "Square averages"]
    return [app_commands.Choice(name=n, value=n) for n in filter_types if current.lower() in n.lower()][:25]

async def relay_type_autocomplete(interaction, current):
    """autocomplete for relay/gameMode, including marathons and aliases."""
    # canonical names from SOLVE_TYPE_MAP
    suggestions = list(SOLVE_TYPE_MAP.values())
    # common marathon values
    marathon_samples = ["Marathon 10", "Marathon 25", "Marathon 42", "Marathon 50", "Marathon 100"]
    suggestions.extend(marathon_samples)
    # aliases shown as hints
    aliases = ["x10", "x25", "x42", "x50", "x100", "rel", "eut", "width", "height", "bld", "blindfolded"]
    suggestions.extend(aliases)

    current_lower = current.lower()
    filtered = []
    seen = set()
    for s in suggestions:
        if current_lower in s.lower() and s.lower() not in seen:
            filtered.append(app_commands.Choice(name=s, value=s))
            seen.add(s.lower())
    return filtered[:25]

async def avglen_autocomplete(interaction, current):
    options = ["single", "ao5", "ao12", "ao25", "ao50", "ao100"]
    return [app_commands.Choice(name=o, value=o) for o in options if current.lower() in o.lower()][:25]

def get_puzzle_size_from_channel(channel_name: str) -> str:
    match = re.search(r'(\d+x\d+)', channel_name, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return "4x4"

def validate_and_get_display(display_type: str):
    display_lower = display_type.lower().strip()
    for id_, name in DISPLAY_TYPE_MAP.items():
        if name.lower().strip() == display_lower:
            return id_, name
    for id_, name in DISPLAY_TYPE_MAP.items():
        if display_lower in name.lower().strip():
            return id_, name
    available = ", ".join(DISPLAY_TYPE_MAP.values())
    raise ValueError(f"unknown display_type: '{display_type}'. available: {available}")

def validate_and_get_control(control_type: str):
    control_lower = control_type.lower().strip()
    for id_, name in CONTROL_TYPE_MAP.items():
        if name.lower().strip() == control_lower:
            return id_, name
    for id_, name in CONTROL_TYPE_MAP.items():
        if control_lower in name.lower().strip():
            return id_, name
    available = ", ".join(CONTROL_TYPE_MAP.values())
    raise ValueError(f"unknown control_type: '{control_type}'. available: {available}")

def validate_and_get_pb(pb_type: str):
    pb_lower = pb_type.lower().strip()
    for id_, name in PB_TYPE_MAP.items():
        if name.lower().strip() == pb_lower:
            return id_
    if pb_lower.endswith('s'):
        pb_singular = pb_lower[:-1]
        for id_, name in PB_TYPE_MAP.items():
            if name.lower().strip() == pb_singular:
                return id_
    else:
        pb_plural = pb_lower + 's'
        for id_, name in PB_TYPE_MAP.items():
            if name.lower().strip() == pb_plural:
                return id_
    available = ", ".join(PB_TYPE_MAP.values())
    raise ValueError(f"unknown pb_type: '{pb_type}'. available: {available}")

# ======================== COMMANDS ========================

@client.tree.command(description="get personal bests for a puzzle size")
@app_commands.describe(
    username="player name (or part of it) - defaults to your discord display name",
    puzzle_size="puzzle size in nxm format (e.g., 4x4, 3x3) - defaults to channel name or 4x4",
    power_system="power system to use for tier info",
    display_type="display type for filtering scores",
    control_type="control type for filtering scores",
    pb_type="pb type to display"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
@app_commands.autocomplete(pb_type=pb_type_autocomplete)
async def getpb(
    interaction: discord.Interaction,
    username: str = None,
    puzzle_size: str = None,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique",
    pb_type: str = "time"
):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        if puzzle_size is None:
            channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else ""
            puzzle_size = get_puzzle_size_from_channel(channel_name)

        display_id, display_name = validate_and_get_display(display_type)
        control_id, control_name = validate_and_get_control(control_type)
        pb_id = validate_and_get_pb(pb_type)

        result = stats.get_pb(username, puzzle_size.lower(), power_system.lower(),
                              display_type.lower(), control_type.lower(), pb_type.lower())
        lines = result.strip().split('\n')
        title = lines[0] if lines else "personal bests"
        details = lines[1] if len(lines) > 1 else ""
        body = "\n".join(lines[2:]) if len(lines) > 2 else ""
        output = f"**{title}**\n_{details}_\n```\n{body if body else 'no data'}\n```"
        await interaction.followup.send(content=output)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

@client.tree.command(description="get world records for a puzzle size")
@app_commands.describe(
    puzzle_size="puzzle size in nxm format (e.g., 4x4, 3x3) - defaults to channel name or 4x4",
    power_system="power system to use for tier info",
    display_type="display type for filtering scores",
    control_type="control type for filtering scores",
    pb_type="pb type to display"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
@app_commands.autocomplete(pb_type=pb_type_autocomplete)
async def getwr(
    interaction: discord.Interaction,
    puzzle_size: str = None,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique",
    pb_type: str = "time"
):
    await interaction.response.defer(ephemeral=False)
    try:
        if puzzle_size is None:
            channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else ""
            puzzle_size = get_puzzle_size_from_channel(channel_name)

        display_id, display_name = validate_and_get_display(display_type)
        control_id, control_name = validate_and_get_control(control_type)
        pb_id = validate_and_get_pb(pb_type)

        result = stats.get_wr(puzzle_size.lower(), power_system.lower(),
                              display_type.lower(), control_type.lower(), pb_type.lower())
        lines = result.strip().split('\n')
        title = lines[0] if lines else "world records"
        details = lines[1] if len(lines) > 1 else ""
        body = "\n".join(lines[2:]) if len(lines) > 2 else ""
        output = f"**{title}**\n_{details}_\n```\n{body if body else 'no data'}\n```"
        await interaction.followup.send(content=output)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

@client.tree.command(description="get power ranking for a player")
@app_commands.describe(
    username="player name (or part of it) - defaults to your discord display name",
    power_system="power system: modern, classic, or fmc",
    display_type="display type for filtering scores",
    control_type="control type for filtering scores",
    pb_type="pb type for power calculation"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
@app_commands.autocomplete(pb_type=pb_type_autocomplete)
async def rank(
    interaction: discord.Interaction,
    username: str = None,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique",
    pb_type: str = "time"
):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        display_id, display_name = validate_and_get_display(display_type)
        control_id, control_name = validate_and_get_control(control_type)
        pb_id = validate_and_get_pb(pb_type)
        result = stats.get_rank(username, power_system.lower(),
                                display_type.lower(), control_type.lower(), pb_type.lower())
        lines = result.strip().split('\n')
        main_line = lines[0] if lines else "no rank data"
        output = f"```\n{main_line}\n```\n_{display_name} | {control_name} | {power_system.lower()}_"
        await interaction.followup.send(content=output)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

@client.tree.command(description="get tier requirements for a puzzle size")
@app_commands.describe(
    tier_name="tier name (e.g., 'grandmaster', 'ascended', 'gold i')",
    power_system="power system: modern, classic, or fmc",
    puzzle_size="puzzle size in nxm format (e.g., 4x4) - defaults to channel name or 4x4"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
async def getreq(
    interaction: discord.Interaction,
    tier_name: str,
    power_system: str = "modern",
    puzzle_size: str = None
):
    await interaction.response.defer(ephemeral=False)
    try:
        if puzzle_size is None:
            channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else ""
            puzzle_size = get_puzzle_size_from_channel(channel_name)
        result = stats.get_req(tier_name.lower(), power_system.lower(), puzzle_size.lower())
        output = f"```\n{result}\n```\n_{power_system.lower()} | {puzzle_size}_"
        await interaction.followup.send(content=output)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ====================== NUMWRS ======================

@client.tree.command(description="count world records per player with filters")
@app_commands.describe(
    display_type="display type for filtering scores",
    control_type="control type for filtering scores",
    pb_type="pb type for comparison (time, move, tps)",
    filter_type="'NxM singles' (default, avglen=1 any size) or 'Square averages' (NxN puzzles only)",
    relay_type="filter by game mode (default: Standard, or Marathon 10, x10, rel, eut, width...)",
    power_system="power system: modern, classic, or fmc"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
@app_commands.autocomplete(pb_type=pb_type_autocomplete)
@app_commands.autocomplete(filter_type=filter_type_autocomplete)
@app_commands.autocomplete(relay_type=relay_type_autocomplete)
async def numwrs(
    interaction: discord.Interaction,
    display_type: str = "standard",
    control_type: str = "unique",
    pb_type: str = "time",
    filter_type: str = "NxM singles",
    relay_type: str = "Standard",
    power_system: str = "modern"
):
    await interaction.response.defer(ephemeral=False)
    try:
        # Parse relay_type to canonical form (support "x10", "rel", etc.)
        canonical_relay = parse_relay_type(relay_type)

        result = stats.numwrs(
            display_type=display_type,
            control_type=control_type,
            pb_type=pb_type,
            filter_type=filter_type,
            relay_type=canonical_relay,
            power_system=power_system
        )
        lines = result.strip().split('\n')
        header = "World Record Counts"
        body_lines = []
        info_parts = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[Display:") or stripped.startswith("[Filter:"):
                info_parts.append(stripped)
            else:
                body_lines.append(stripped)
        body = "\n".join(body_lines) if body_lines else "no world records found"
        info = "\n".join(info_parts) if info_parts else ""
        output = f"**{header}**\n```\n{body}\n```"
        if info:
            output += f"\n_{info}_"
        await interaction.followup.send(content=output)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ====================== TOP25 ======================

@client.tree.command(description="Show the top 25 players by power")
@app_commands.describe(
    power_system="Power system: modern, classic, or fmc",
    display_type="Display type for filtering scores",
    control_type="Control type for filtering scores",
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc"),
])
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
async def top25(
    interaction: discord.Interaction,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique",
):
    await interaction.response.defer(ephemeral=False)
    try:
        result = stats.top25(
            power_system=power_system.lower(),
            display_type=display_type.lower(),
            control_type=control_type.lower(),
        )
        lines = result.strip().split('\n')
        body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
        info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""

        max_chunk_size = 1900
        chunks = []
        current_chunk = []
        current_length = 0
        for line in body_lines:
            line_length = len(line) + 1
            if current_length + line_length > max_chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_length = line_length
            else:
                current_chunk.append(line)
                current_length += line_length
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        header = "**Top 25 Players**\n"
        for i, chunk in enumerate(chunks):
            if i == 0:
                output = f"{header}```\n{chunk}\n```"
            else:
                output = f"```\n{chunk}\n```"
            if i == len(chunks) - 1 and info_line:
                output += f"\n_{info_line}_"
            if i == 0:
                await interaction.followup.send(content=output)
            else:
                await interaction.followup.send(content=output, ephemeral=False)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ====================== BESTSCORES / WORSTSCORES ======================

@client.tree.command(description="Show a player's best scores per category, grouped by tier")
@app_commands.describe(
    username="Player name (or part of it) – defaults to your Discord display name",
    power_system="Power system: modern, classic, or fmc",
    display_type="Display type for filtering scores",
    control_type="Control type for filtering scores",
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc"),
])
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
async def bestscores(
    interaction: discord.Interaction,
    username: str = None,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique",
):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        result = stats.bestscores(username, power_system=power_system.lower(),
                                  display_type=display_type.lower(),
                                  control_type=control_type.lower())
        output = f"**Best Scores for {username}**\n```\n{result}\n```"
        await interaction.followup.send(content=output)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ====================== LB30 ======================

@client.tree.command(description="Top 30 scores for a puzzle/relay/avglen, shown as % of #1")
@app_commands.describe(
    puzzle_size="Puzzle size (e.g., 4x4, 3x3) – defaults to channel name or 4x4",
    relay_type="Game mode (Standard, Marathon 10, x10, rel, eut, width, bld …)",
    avglen="Average length: single, ao5, ao12, ao25, ao50, ao100",
    display_type="Display type for filtering scores",
    control_type="Control type for filtering scores",
    pb_type="PB type (time, move, tps)",
)
@app_commands.autocomplete(relay_type=relay_type_autocomplete)
@app_commands.autocomplete(avglen=avglen_autocomplete)
@app_commands.autocomplete(display_type=display_type_autocomplete)
@app_commands.autocomplete(control_type=control_type_autocomplete)
@app_commands.autocomplete(pb_type=pb_type_autocomplete)
async def lb30(
    interaction: discord.Interaction,
    puzzle_size: str = None,
    relay_type: str = "Standard",
    avglen: str = "single",
    display_type: str = "standard",
    control_type: str = "unique",
    pb_type: str = "time",
):
    await interaction.response.defer(ephemeral=False)
    try:
        if puzzle_size is None:
            channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else ""
            puzzle_size = get_puzzle_size_from_channel(channel_name)

        canonical_relay = parse_relay_type(relay_type)

        result = stats.lb30(
            puzzle_size=puzzle_size.lower(),
            relay_type=canonical_relay,
            avglen=avglen.lower(),
            display_type=display_type.lower(),
            control_type=control_type.lower(),
            pb_type=pb_type.lower(),
        )

        lines = result.strip().split('\n')
        body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
        info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
        body = "\n".join(body_lines)
        output = f"**Top 30 – {puzzle_size} {canonical_relay} {avglen}**\n```\n{body}\n```"
        if info_line:
            output += f"\n_{info_line}_"
        await interaction.followup.send(content=output)

    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)   

@client.tree.command(description="Update web backup by running updateweb.py script")
async def updateweb(interaction: discord.Interaction):
    global updateweb_running

    await interaction.response.defer(ephemeral=False)

    try:
        if updateweb_running:
            await interaction.followup.send(
                "⚠️ Web update is already in progress. Please wait.",
                ephemeral=True
            )
            return

        script_path = os.getenv("UPDATEWEB_SCRIPT_PATH")
        if not script_path or not os.path.exists(script_path):
            await interaction.followup.send("Error: script path invalid.", ephemeral=True)
            return

        updateweb_running = True

        # 🥚 Start thinking message
        msg = await interaction.followup.send("🤖 thinking about eggs :zzz:")

        start_time = timemodule.time()

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        script_dir = os.path.dirname(script_path)
        script_name = os.path.basename(script_path)

        process = await asyncio.create_subprocess_exec(
            "python", "-u", script_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=script_dir,
            env=env
        )

        # 🥚 Animate while running
        async def animate():
            states = [
                "🤖 thinking about eggs (web update is taking 3-4 minutes) :zzz:",
                "🤖 thinking about eggs (web update is taking 3-4 minutes) :zzz: :zzz: ",
                "🤖 thinking about eggs (web update is taking 3-4 minutes) :zzz: :zzz: "
            ]
            i = 0
            while process.returncode is None:
                await msg.edit(content=states[i % len(states)])
                i += 1
                await asyncio.sleep(10)

        anim_task = asyncio.create_task(animate())

        stdout, stderr = await process.communicate()

        anim_task.cancel()

        elapsed_time = timemodule.time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = elapsed_time % 60
        time_str = f"{minutes}m {seconds:.1f}s" if minutes > 0 else f"{seconds:.1f}s"

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
            await msg.edit(content=f"❌ Web update failed after {time_str}\n{error_msg[:1000]}")
            return

        # 🥚 Final success message (edit instead of new send)
        await msg.edit(content=f""":egg: Web backup updated successfully! (took {time_str})

**Leaderboard URL:** https://slidysim.github.io/lb
**Web-only scores:** https://slidysim.github.io/archive""")

    except Exception as e:
        await interaction.followup.send(f"❌ Error running web update: {str(e)}")

    finally:
        updateweb_running = False

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

@client.tree.command(description="Get your personal best history (progression of records) for a specific puzzle size")
@app_commands.describe(
    size="Puzzle size in NxM format (e.g., 4x5, 10x18, 5x5)",
    pbtype="Type of personal best to track (time = lower better, moves = lower better, tps = higher better)",
    time_limit="Optional maximum time in seconds (only solves under this count toward PBs)",
    moves_limit="Optional maximum moves (only solves under this count toward PBs)",
    tps_limit="Optional minimum TPS (only solves above this count toward PBs)",
    hours_limit="Optional time window in hours (e.g., 24 for last day; defaults to all time)"
)
async def pbhistory(
    interaction: discord.Interaction,
    size: str,
    pbtype: Literal["time", "moves", "tps"] = "time",
    time_limit: float = None,
    moves_limit: int = None,
    tps_limit: float = None,
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
        
        # Build the base query (same filters as getpb, but we fetch ALL qualifying solves)
        query = """
            SELECT 
                a.time,
                a.moves,
                a.tps,
                b.timestamp
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
        
        # Add optional PB-consideration filters (these define which solves are eligible to become PBs)
        if time_limit is not None:
            query += " AND a.time < ?"
            params.append(int(time_limit * 1000))
            
        if moves_limit is not None:
            query += " AND a.moves < ?"
            params.append(moves_limit * 1000)
            
        if tps_limit is not None:
            query += " AND a.tps > ?"
            params.append(tps_limit * 1000)
        
        # Always order by timestamp ASC so we can track PB progression chronologically
        query += " ORDER BY b.timestamp ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        if not rows:
            size_filter = f" for size {width}x{height}"
            time_filter = f" under {time_limit}s" if time_limit is not None else ""
            moves_filter = f" with moves < {moves_limit}" if moves_limit is not None else ""
            tps_filter = f" with TPS > {tps_limit}" if tps_limit is not None else ""
            hours_filter = f" in last {hours_limit} hours" if hours_limit is not None else ""
            
            await interaction.followup.send(
                f"No matching solves found{size_filter}{time_filter}{moves_filter}{tps_filter}{hours_filter}.",
                ephemeral=False
            )
            return
        
        # Determine how to compare for the chosen pbtype
        if pbtype in ["time", "moves"]:
            best_value = float('inf')
            is_better = lambda val: val < best_value
        else:  # tps
            best_value = float('-inf')
            is_better = lambda val: val > best_value
        
        # Walk through solves in chronological order and record only new PBs
        pb_history = []
        for time_ms, moves_ms, tps_ms, ts_ms in rows:
            val = time_ms if pbtype == "time" else moves_ms if pbtype == "moves" else tps_ms
            if is_better(val):
                pb_history.append((time_ms, moves_ms, tps_ms, ts_ms))
                best_value = val
        
        # Build the markdown table (exactly as requested)
        table_lines = [
            " Time (s) | Moves |  TPS   | Date (UTC)",
            "----------|-------|--------|--------------"
        ]
        
        for time_ms, moves_ms, tps_ms, ts_ms in pb_history:
            time_s = time_ms / 1000
            moves = int(moves_ms / 1000)
            tps = tps_ms / 1000
            date_str = datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
            table_lines.append(f"{time_s:>9.3f} | {moves:>5} | {tps:>6.3f} | {date_str}")
        
        # Prepare filter metadata (exactly as requested)
        filter_info = []
        if time_limit is not None:
            filter_info.append(f"Time < {time_limit}s")
        if moves_limit is not None:
            filter_info.append(f"Moves < {moves_limit}")
        if tps_limit is not None:
            filter_info.append(f"TPS > {tps_limit}")
        if hours_limit is not None:
            filter_info.append(f"Last {hours_limit}h")
        
        metadata = f"Filters: {', '.join(filter_info) if filter_info else 'None'}\n"
        
        # Create embed (styled similarly to playtime + getpb)
        embed = discord.Embed(
            title=f"📜 PB History ({pbtype}) — {width}x{height}",
            color=discord.Color.gold()
        )
        
        embed.description = (
            f"```\n" + "\n".join(table_lines) + "\n```\n"
            f"{metadata}"
        )
        
        await interaction.followup.send(embed=embed, ephemeral=False)

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}", ephemeral=False)
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
async def getpbexe(
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