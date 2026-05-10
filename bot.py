from dotenv import load_dotenv
import os
import sys
import discord
import io
from discord import app_commands, ui
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
import tempfile
import stats
from power_data import DISPLAY_TYPE_MAP, CONTROL_TYPE_MAP, PB_TYPE_MAP, SOLVE_TYPE_MAP
import re

# ── Replay generator setup ──────────────────────────────────────
REPLAY_GEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay_generator")
if REPLAY_GEN_DIR not in sys.path:
    sys.path.insert(0, REPLAY_GEN_DIR)

from replay_init import init_replay_generator as update_replay_repo
update_replay_repo(force_update=True)

from replay_generator import ReplayGenerator, expand_solution
from replay_video import ReplayVideoGenerator, parse_replay_url, CancelError

load_dotenv()

# CONFIG (use .env file)
token = os.getenv("BOT_TOKEN")
db_path = os.getenv("DB_PATH")
YOUR_USER_ID = int(os.getenv("DISCORD_USER_ID"))

REPO_NAME = os.getenv("TXT_REPO_NAME")
LOCAL_PATH = os.getenv("TXT_REPO_LOCAL_PATH")
GITHUB = os.getenv("TXT_REPO_GITHUB")
SUBFOLDERS = os.getenv("TXT_REPO_SUBFOLDERS")
script_path = os.getenv("UPDATEWEB_SCRIPT_PATH")

REPO_LOCAL_DIR = os.path.join(LOCAL_PATH, REPO_NAME)
GENERATED_DIR = os.path.join(REPO_LOCAL_DIR, SUBFOLDERS)

updateweb_running = False

# ───────────────── helper functions (unchanged) ─────────────────
def save_replay_and_generate_url(file_content: str, filename: str) -> str:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    filepath = os.path.join(GENERATED_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(file_content)
    try:
        original_dir = os.getcwd()
        os.chdir(REPO_LOCAL_DIR)
        os.system("git add .")
        os.system(f'git commit -m "update {filename}"')
        os.system("git push -u origin main")
        os.chdir(original_dir)
    except Exception as e:
        os.chdir(original_dir)  # Also restore on error
        raise RuntimeError(f"Git error: {e}")
    return f"{GITHUB}/{REPO_NAME}/index.html?url={REPO_NAME}/{SUBFOLDERS}/{filename}"

def encodeURIComponent(string):
    return ''.join(c if c.isalnum() or c in ['-', '_', '.', '~'] else f"%{ord(c):02X}" for c in string)

def compress_array_to_string(input_array):
    json_string = json.dumps(input_array)
    compressed_data = zlib.compress(json_string.encode(), level=9)
    base64_encoded_string = base64.b64encode(compressed_data).decode()
    return encodeURIComponent(base64_encoded_string)

async def generate_replay_video(msg, replay_url, output_path="replay.mp4", **kwargs):
    import subprocess, shutil
    from replay_video import pick_tile_size as _pick_tile_size
    from replay_generator import expand_solution, parse_scramble_guess

    solution, tps, scramble, movetimes = parse_replay_url(replay_url)

    sol_len = len(expand_solution(solution))

    # Safety checks
    if movetimes not in (None, -1):
        last_mt = movetimes[-1] if isinstance(movetimes, list) else movetimes
        if last_mt > 60000:
            raise ValueError(f"Video would be {last_mt}ms long, exceeding the 60000ms limit.")

    if tps is not None:
        estimated_s = sol_len / (tps / 1000)
        if estimated_s > 600:
            raise ValueError(f"Estimated video length ({estimated_s:.0f}) exceeds the 60000ms limit.")

    # Puzzle info for header
    try:
        _m = parse_scramble_guess(solution)
        w, h = len(_m[0]), len(_m)
    except Exception:
        w = h = "?"
    quality = kwargs.get("quality", 1)
    total_frames = sol_len + 1
    tile_size = _pick_tile_size(w, h) if isinstance(w, int) else "?"
    tps_display = tps if tps else kwargs.get("tps", "auto")

    tmpdir = tempfile.mkdtemp(prefix="replay_vid_")
    output = os.path.join(tmpdir, output_path)
    start_time = timemodule.time()

    # ── DiscordProgress — mirrors TerminalProgress from replay_video.py ──
    class DiscordProgress:
        def __init__(self):
            self.start_time = timemodule.time()
            self.last_update_time = self.start_time
            self.last_current = 0
            self.window_rate = 0.0
            self._last_edit_time = 0.0
            self._gpu_stats = None
            self._phase_offset = 0
            self._phase0_total = None
            self._phase_prev_cur = None
            self.total = 0
            self.last_line = ""

        @staticmethod
        def _time_str(t):
            if t >= 3600:
                return f"{t/3600:.0f}h{(t%3600)/60:.0f}m"
            elif t >= 60:
                return f"{t/60:.0f}m{t%60:.0f}s"
            return f"{t:.1f}s"

        def _build_line(self, current, elapsed, rate, eta):
            frac = current / self.total if self.total > 0 else 0
            pct = frac * 100
            total_t = elapsed + eta
            suffix = f" {pct:.0f}% | {rate:.0f}/s | {self._time_str(elapsed)}/{self._time_str(total_t)}"
            if self._gpu_stats and self._gpu_stats.get("batch_size"):
                s = self._gpu_stats
                mb = s.get("mem_used_mb", 0) / 1024
                tb = s.get("total_mem_mb", 0) / 1024
                suffix += f" | {mb:.1f}/{tb:.1f}GB | Batch: {s.get('batch_size', 0)}"
            bar_w = 40
            filled = int(bar_w * frac)
            bar = "#" * filled + "-" * (bar_w - filled)
            return f"Render: [{bar}]{suffix}"

        def __call__(self, cur, tot, **kwargs):
            if (self._phase_prev_cur is not None and
                cur < self._phase_prev_cur and
                self._phase0_total is not None):
                self._phase_offset += self._phase0_total
            self._phase_prev_cur = cur
            if self._phase0_total is None:
                self._phase0_total = tot
            adjusted_cur = cur + self._phase_offset
            adjusted_tot = self._phase0_total * 2
            self.total = adjusted_tot
            gpu_stats = kwargs.get("gpu_stats")
            if gpu_stats is not None:
                self._gpu_stats = gpu_stats

            now = timemodule.time()
            elapsed = now - self.start_time
            window = now - self.last_update_time
            if window > 0.5 and adjusted_cur > self.last_current:
                instant = (adjusted_cur - self.last_current) / window
                if self.window_rate <= 0:
                    self.window_rate = instant
                else:
                    self.window_rate = self.window_rate * 0.5 + instant * 0.5
                self.last_update_time = now
                self.last_current = adjusted_cur
            rate = self.window_rate if self.window_rate > 0 else adjusted_cur / elapsed if elapsed > 0 else 0
            eta = (self.total - adjusted_cur) / rate if rate > 0 else 0
            self.last_line = self._build_line(adjusted_cur, elapsed, rate, eta)

    dp = DiscordProgress()
    dp.total = total_frames * 2

    # Initial header
    header = f"Puzzle: {w}x{h}, Moves: {sol_len}, TPS: {tps_display}"
    tile = f"Tile size: {tile_size}px x quality={quality}, Frames: {total_frames}"
    header_block = f"{header}\n{tile}"
    bar = dp._build_line(0, 0, 0, 0)
    await msg.edit(content=f"{header_block}\n{bar}")

    def progress_cb(cur, tot, **kw):
        dp(cur, tot, **kw)

    video_gen = ReplayVideoGenerator(temp_dir=tmpdir, cleanup_frames=False)

    async def poll_display():
        while True:
            await asyncio.sleep(3)
            line = dp.last_line
            if line:
                try:
                    await msg.edit(content=f"{header_block}\n{line}")
                except Exception:
                    pass

    poll_task = asyncio.create_task(poll_display())
    try:
        video_path = await asyncio.to_thread(
            video_gen.generate_simple_replay,
            solution, output_path=output,
            tps=tps, scramble=scramble, movetimes=movetimes,
            show_progress=False,
            external_progress_cb=progress_cb,
            **kwargs
        )
        poll_task.cancel()
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Output file not found after generation: {video_path}")
        elapsed = timemodule.time() - start_time
        fn = os.path.basename(video_path)
        await msg.edit(content=f"✅ Done! Video saved to: {fn} (took {elapsed:.1f}s)")
        return discord.File(video_path), tmpdir
    except CancelError:
        poll_task.cancel()
        await msg.edit(content="❌ Video generation cancelled.")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    except Exception as e:
        poll_task.cancel()
        await msg.edit(content=f"❌ Video generation failed: {e}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# ═══════════ autocomplete / helpers (unchanged) ═══════════
async def display_type_autocomplete(interaction, current):
    choices = [app_commands.Choice(name=name, value=name) for name in DISPLAY_TYPE_MAP.values() if current.lower() in name.lower()]
    return choices[:25]

async def control_type_autocomplete(interaction, current):
    choices = [app_commands.Choice(name=name, value=name) for name in CONTROL_TYPE_MAP.values() if current.lower() in name.lower()]
    return choices[:25]

async def pb_type_autocomplete(interaction, current):
    choices = [app_commands.Choice(name=name, value=name) for name in PB_TYPE_MAP.values() if current.lower() in name.lower()]
    return choices[:25]

async def filter_type_autocomplete(interaction, current):
    filter_types = ["NxM singles", "Square averages"]
    return [app_commands.Choice(name=n, value=n) for n in filter_types if current.lower() in n.lower()][:25]

async def relay_type_autocomplete(interaction, current):
    suggestions = list(SOLVE_TYPE_MAP.values()) + ["Marathon 10", "Marathon 25", "Marathon 42", "Marathon 50", "Marathon 100", "x10", "x25", "x42", "x50", "x100", "rel", "eut", "width", "height", "bld", "blindfolded"]
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
    return match.group(1).lower() if match else "4x4"

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

def parse_relay_type(raw: str) -> str:
    raw = raw.strip()
    raw_lower = raw.lower()
    m = re.match(r'^x(\d+)$', raw_lower)
    if m:
        return f"Marathon {m.group(1)}"
    m = re.match(r'^marathon\s*(\d+)$', raw_lower)
    if m:
        return f"Marathon {m.group(1)}"
    alias_map = {
        "rel": "2-N relay", "relay": "2-N relay",
        "eut": "Everything-up-to relay", "everything": "Everything-up-to relay",
        "everything-up-to": "Everything-up-to relay",
        "width": "Width relay", "wrel": "Width relay",
        "height": "Height relay", "hrel": "Height relay",
        "bld": "BLD", "blindfolded": "BLD",
    }
    if raw_lower in alias_map:
        return alias_map[raw_lower]
    for name in SOLVE_TYPE_MAP.values():
        if raw_lower in name.lower():
            return name
    for name in SOLVE_TYPE_MAP.values():
        if name.lower() in raw_lower:
            return name
    if raw_lower == "standard":
        return "Standard"
    raise ValueError(f"Unknown relay type: '{raw}'. Accepted: Standard, 2-N relay, Everything-up-to relay, Width relay, Height relay, BLD, Marathon N, xN, rel, eut, width, etc.")

# ═══════════ safety net for large messages ═══════════
async def safe_followup(interaction: discord.Interaction, content: str, view=None, ephemeral=False, file=None):
    if len(content) > 2000:
        f = discord.File(io.StringIO(content), filename="response.txt")
        await interaction.followup.send(content="Output too large – see attached file.", file=f, view=view, ephemeral=ephemeral)
    else:
        await interaction.followup.send(content=content, view=view, ephemeral=ephemeral)

async def safe_edit(interaction: discord.Interaction, content: str, view=None):
    if len(content) > 2000:
        f = discord.File(io.StringIO(content), filename="response.txt")
        await interaction.edit_original_response(content="Output too large – see attached file.", attachments=[f], view=view)
    else:
        await interaction.edit_original_response(content=content, view=view)

# ═══════════ help command ═══════════
def _discord_file_from_text(content: str, filename: str = "response.txt") -> discord.File:
    return discord.File(io.BytesIO(content.encode("utf-8")), filename=filename)

async def safe_followup(interaction: discord.Interaction, content: str, view=None, ephemeral=False, file=None, fallback_content: str = None):
    if len(content) <= 2000:
        await interaction.followup.send(content=content, view=view, ephemeral=ephemeral)
        return

    if fallback_content and len(fallback_content) <= 2000:
        await interaction.followup.send(content=fallback_content, view=view, ephemeral=ephemeral)
        return

    attachment_content = fallback_content or content
    f = file or _discord_file_from_text(attachment_content)
    await interaction.followup.send(content="Output too large - see attached file.", file=f, view=view, ephemeral=ephemeral)

async def safe_edit(interaction: discord.Interaction, content: str, view=None, fallback_content: str = None):
    if len(content) <= 2000:
        await interaction.edit_original_response(content=content, attachments=[], view=view)
        return

    if fallback_content and len(fallback_content) <= 2000:
        await interaction.edit_original_response(content=fallback_content, attachments=[], view=view)
        return

    attachment_content = fallback_content or content
    f = _discord_file_from_text(attachment_content)
    await interaction.edit_original_response(content="Output too large - see attached file.", attachments=[f], view=view)

class HelpMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.commands = [cmd for cmd in client.tree.get_commands() if "[Admin only]" not in cmd.description]
        
        # Just add all command buttons
        for i, cmd in enumerate(self.commands):
            label = f"/{cmd.name}"[:80]
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                custom_id=f"help_cmd_{i}"
            )
            button.callback = self.make_command_callback(i)
            self.add_item(button)
    
    def make_command_callback(self, index):
        async def callback(interaction: discord.Interaction):
            cmd = self.commands[index]
            description = cmd.description or "No description available"
            
            params_text = ""
            if hasattr(cmd, 'parameters') and cmd.parameters:
                for param in cmd.parameters:
                    if param.name != "interaction":  # skip internal param
                        param_desc = param.description or "No description"
                        required = " (required)" if param.required else " (optional)"
                        params_text += f"• `{param.name}`{required}: {param_desc}\n"
            
            embed = discord.Embed(
                title=f"/{cmd.name}",
                description=description,
                color=0x5865F2
            )
            if params_text:
                embed.add_field(name="Parameters", value=params_text, inline=False)
            
            await interaction.response.edit_message(embed=embed, view=self)
        return callback
    
    async def close_callback(self, interaction: discord.Interaction):
        await interaction.message.delete()


@client.tree.command(description="Show interactive help menu with clickable commands")
async def help(interaction: discord.Interaction):
    view = HelpMenuView()
    embed = discord.Embed(
        title="📚 Help Menu",
        description="Click a command to see details.",
        color=0x5865F2
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ═══════════ getpb (with puzzle size buttons) ═══════════
async def getpb_view(username, puzzle_size, power_system, display_type, control_type, pb_type):
    view = ui.View(timeout=None)
    sizes_small = ["3x3", "4x4", "5x5", "6x6", "7x7", "8x8", "9x9", "10x10"]
    sizes_big   = ["12x12", "16x16", "20x20"]

    async def make_callback(size):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                new_result = stats.get_pb(username, size, power_system,
                                         display_type.lower(), control_type.lower(), pb_type.lower())
                new_lines = new_result.strip().split('\n')
                new_title = new_lines[0] if new_lines else "personal bests"
                new_details = new_lines[1] if len(new_lines) > 1 else ""
                new_body = "\n".join(new_lines[2:]) if len(new_lines) > 2 else ""
                new_output = f"**{new_title}**\n_{new_details}_\n```\n{new_body if new_body else 'no data'}\n```"
                new_view = await getpb_view(username, size, power_system, display_type, control_type, pb_type)
                for child in new_view.children:
                    if isinstance(child, ui.Button):
                        child.callback = await make_callback(child.label)
                await safe_edit(interaction, new_output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb

    for s in sizes_small:
        view.add_item(ui.Button(label=s, style=discord.ButtonStyle.secondary if s != puzzle_size.lower() else discord.ButtonStyle.primary,
                                disabled=(s == puzzle_size.lower()), custom_id=f"getpb_{s}"))
    for s in sizes_big:
        view.add_item(ui.Button(label=s, style=discord.ButtonStyle.secondary if s != puzzle_size.lower() else discord.ButtonStyle.primary,
                                disabled=(s == puzzle_size.lower()), custom_id=f"getpb_{s}"))
    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)
    return view

@client.tree.command(description="get personal bests for a puzzle size")
@app_commands.describe(
    username="player name (or part of it) - defaults to your discord display name",
    puzzle_size="puzzle size in nxm format (e.g., 4x4, 3x3) - defaults to channel name or 4x4",
    power_system="power system to use for tier info",
    display_type="display type for filtering scores",
    control_type="control type for filtering scores",
    pb_type="pb type to display"
)
@app_commands.choices(power_system=[app_commands.Choice(name="modern", value="modern"), app_commands.Choice(name="classic", value="classic"), app_commands.Choice(name="fmc", value="fmc")])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete, pb_type=pb_type_autocomplete)
async def getpb(interaction: discord.Interaction, username: str = None, puzzle_size: str = None, power_system: str = "modern", display_type: str = "standard", control_type: str = "unique", pb_type: str = "time"):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        if puzzle_size is None:
            channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else ""
            puzzle_size = get_puzzle_size_from_channel(channel_name)
        result = stats.get_pb(username, puzzle_size.lower(), power_system.lower(), display_type.lower(), control_type.lower(), pb_type.lower())
        lines = result.strip().split('\n')
        title = lines[0] if lines else "personal bests"
        details = lines[1] if len(lines) > 1 else ""
        body = "\n".join(lines[2:]) if len(lines) > 2 else ""
        output = f"**{title}**\n_{details}_\n```\n{body if body else 'no data'}\n```"
        view = await getpb_view(username, puzzle_size, power_system, display_type, control_type, pb_type)
        await safe_followup(interaction, output, view=view)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ getwr (with puzzle size buttons) ═══════════
async def getwr_view(puzzle_size, power_system, display_type, control_type, pb_type):
    view = ui.View(timeout=None)
    sizes_small = ["3x3", "4x4", "5x5", "6x6", "7x7", "8x8", "9x9", "10x10"]
    sizes_big   = ["12x12", "16x16", "20x20"]
    async def make_callback(size):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                result = stats.get_wr(size.lower(), power_system.lower(), display_type.lower(), control_type.lower(), pb_type.lower())
                lines = result.strip().split('\n')
                title = lines[0] if lines else "world records"
                details = lines[1] if len(lines) > 1 else ""
                body = "\n".join(lines[2:]) if len(lines) > 2 else ""
                output = f"**{title}**\n_{details}_\n```\n{body if body else 'no data'}\n```"
                new_view = await getwr_view(size, power_system, display_type, control_type, pb_type)
                for child in new_view.children:
                    if isinstance(child, ui.Button):
                        child.callback = await make_callback(child.label)
                await safe_edit(interaction, output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb
    for s in sizes_small:
        view.add_item(ui.Button(label=s, style=discord.ButtonStyle.secondary if s != puzzle_size.lower() else discord.ButtonStyle.primary,
                                disabled=(s == puzzle_size.lower()), custom_id=f"getwr_{s}"))
    for s in sizes_big:
        view.add_item(ui.Button(label=s, style=discord.ButtonStyle.secondary if s != puzzle_size.lower() else discord.ButtonStyle.primary,
                                disabled=(s == puzzle_size.lower()), custom_id=f"getwr_{s}"))
    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)
    return view

@client.tree.command(description="get world records for a puzzle size")
@app_commands.describe(
    puzzle_size="puzzle size in nxm format (e.g., 4x4, 3x3) - defaults to channel name or 4x4",
    power_system="power system to use for tier info",
    display_type="display type for filtering scores",
    control_type="control type for filtering scores",
    pb_type="pb type to display"
)
@app_commands.choices(power_system=[app_commands.Choice(name="modern", value="modern"), app_commands.Choice(name="classic", value="classic"), app_commands.Choice(name="fmc", value="fmc")])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete, pb_type=pb_type_autocomplete)
async def getwr(interaction: discord.Interaction, puzzle_size: str = None, power_system: str = "modern", display_type: str = "standard", control_type: str = "unique", pb_type: str = "time"):
    await interaction.response.defer(ephemeral=False)
    try:
        if puzzle_size is None:
            channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else ""
            puzzle_size = get_puzzle_size_from_channel(channel_name)
        result = stats.get_wr(puzzle_size.lower(), power_system.lower(), display_type.lower(), control_type.lower(), pb_type.lower())
        lines = result.strip().split('\n')
        title = lines[0] if lines else "world records"
        details = lines[1] if len(lines) > 1 else ""
        body = "\n".join(lines[2:]) if len(lines) > 2 else ""
        output = f"**{title}**\n_{details}_\n```\n{body if body else 'no data'}\n```"
        view = await getwr_view(puzzle_size, power_system, display_type, control_type, pb_type)
        await safe_followup(interaction, output, view=view)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ rank (power system buttons) – FIXED ═══════════
async def rank_view(username, power_system, display_type, control_type, pb_type):
    view = ui.View(timeout=None)
    systems = ["modern", "classic", "fmc"]
    async def make_callback(sys_label):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                sys = sys_label.lower()  # <-- fix
                result = stats.get_rank(username, sys, display_type.lower(), control_type.lower(), pb_type.lower())
                lines = result.strip().split('\n')
                main_line = lines[0] if lines else "no rank data"
                output = f"```\n{main_line}\n```\n_{display_type} | {control_type} | {sys}_"
                new_view = await rank_view(username, sys, display_type, control_type, pb_type)
                for child in new_view.children:
                    if isinstance(child, ui.Button):
                        child.callback = await make_callback(child.label)
                await safe_edit(interaction, output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb
    for sys in systems:
        view.add_item(ui.Button(label=sys.capitalize(), style=discord.ButtonStyle.secondary if sys != power_system else discord.ButtonStyle.primary,
                                disabled=(sys == power_system), custom_id=f"rank_{sys}"))
    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)
    return view

@client.tree.command(description="get power ranking for a player")
@app_commands.describe(username="player name (or part of it) - defaults to your discord display name",
                       power_system="power system: modern, classic, or fmc",
                       display_type="display type for filtering scores",
                       control_type="control type for filtering scores",
                       pb_type="pb type for power calculation")
@app_commands.choices(power_system=[app_commands.Choice(name="modern", value="modern"), app_commands.Choice(name="classic", value="classic"), app_commands.Choice(name="fmc", value="fmc")])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete, pb_type=pb_type_autocomplete)
async def rank(interaction: discord.Interaction, username: str = None, power_system: str = "modern", display_type: str = "standard", control_type: str = "unique", pb_type: str = "time"):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        result = stats.get_rank(username, power_system.lower(), display_type.lower(), control_type.lower(), pb_type.lower())
        lines = result.strip().split('\n')
        main_line = lines[0] if lines else "no rank data"
        output = f"```\n{main_line}\n```\n_{display_type} | {control_type} | {power_system.lower()}_"
        view = await rank_view(username, power_system.lower(), display_type, control_type, pb_type)
        await safe_followup(interaction, output, view=view)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ top25 (power system buttons only) – FIXED ═══════════
async def top25_view(power_system, display_type, control_type):
    view = ui.View(timeout=None)
    systems = ["modern", "classic", "fmc"]

    async def make_callback(sys_label):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                sys = sys_label.lower()                     # <-- ensures lowercase
                result = stats.top25(
                    power_system=sys,
                    display_type=display_type.lower(),
                    control_type=control_type.lower()
                )
                lines = result.strip().split('\n')
                body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
                info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
                body = "\n".join(body_lines)
                output = f"**Top 25 Players**\n```\n{body}\n```"
                if info_line:
                    output += f"\n_{info_line}_"

                new_view = await top25_view(sys, display_type, control_type)
                # rebind callbacks for the new view
                for child in new_view.children:
                    if isinstance(child, ui.Button):
                        child.callback = await make_callback(child.label)
                await safe_edit(interaction, output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb

    for sys in systems:
        view.add_item(ui.Button(
            label=sys.capitalize(),
            style=discord.ButtonStyle.secondary if sys != power_system else discord.ButtonStyle.primary,
            disabled=(sys == power_system),
            custom_id=f"top25_{sys}"
        ))

    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)

    return view


@client.tree.command(description="Show the top 25 players by power")
@app_commands.describe(
    power_system="Power system: modern, classic, or fmc",
    display_type="Display type for filtering scores",
    control_type="Control type for filtering scores"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete)
async def top25(
    interaction: discord.Interaction,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique"
):
    await interaction.response.defer(ephemeral=False)
    try:
        result = stats.top25(
            power_system=power_system.lower(),
            display_type=display_type.lower(),
            control_type=control_type.lower()
        )
        lines = result.strip().split('\n')
        body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
        info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
        body = "\n".join(body_lines)
        output = f"**Top 25 Players**\n```\n{body}\n```"
        if info_line:
            output += f"\n_{info_line}_"

        view = await top25_view(power_system.lower(), display_type, control_type)
        await safe_followup(interaction, output, view=view)

    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ bestscores (power system buttons) – FIXED ═══════════
def _format_signed_pct(pct_val: float) -> str:
    sign = "+" if pct_val >= 0 else "-"
    num = abs(pct_val)
    if num < 10:
        return f"{sign} {num:.2f}%"
    return f"{sign}{num:.2f}%"

def _ansi_pct(pct_val: float, color_code: str, bold: bool) -> str:
    weight = "1" if bold else "0"
    return f"\u001b[{weight};{color_code}m{_format_signed_pct(pct_val)}\u001b[0;0m"

def _wrap_code_block(body: str, language: str = "") -> str:
    return f"```{language}\n{body}\n```"

def _format_bestscores_result(result: str, use_ansi: bool) -> str:
    formatted_lines = []
    for line in result.strip().split('\n'):
        parts = line.split('|')
        if len(parts) < 4:
            formatted_lines.append(line)
            continue

        pct_raw = parts[-1].strip().replace('%', '')
        try:
            pct_val = float(pct_raw)
        except ValueError:
            formatted_lines.append(line)
            continue

        pct_text = _format_signed_pct(pct_val)
        if use_ansi:
            pct_text = _ansi_pct(pct_val, _get_ansi_color_for_pctBest(pct_val), pct_val >= 0)
        parts[-1] = f" {pct_text} "
        formatted_lines.append('|'.join(parts))

    body = "\n".join(formatted_lines) if formatted_lines else "no data"
    return _wrap_code_block(body, "ansi" if use_ansi else "")

def _bestscores_outputs(result: str) -> tuple[str, str]:
    return _format_bestscores_result(result, True), _format_bestscores_result(result, False)

async def bestscores_view(username, power_system, display_type, control_type):
    view = ui.View(timeout=None)
    systems = ["modern", "classic", "fmc"]

    async def make_callback(sys_label):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                sys = sys_label.lower()
                result = stats.bestscores(
                    username,
                    power_system=sys,
                    display_type=display_type.lower(),
                    control_type=control_type.lower()
                )

                output, plain_output = _bestscores_outputs(result)
                new_view = await bestscores_view(username, sys, display_type, control_type)
                await safe_edit(interaction, output, view=new_view, fallback_content=plain_output)

            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

        return cb

    for sys in systems:
        view.add_item(ui.Button(
            label=sys.capitalize(),
            style=discord.ButtonStyle.secondary if sys != power_system else discord.ButtonStyle.primary,
            disabled=(sys == power_system),
            custom_id=f"bs_{sys}"
        ))

    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)

    return view

@client.tree.command(description="Show a player's best scores per category, grouped by tier")
@app_commands.describe(username="Player name (or part of it) – defaults to your Discord display name",
                       power_system="Power system: modern, classic, or fmc",
                       display_type="Display type for filtering scores",
                       control_type="Control type for filtering scores")
@app_commands.choices(power_system=[app_commands.Choice(name="modern", value="modern"), app_commands.Choice(name="classic", value="classic"), app_commands.Choice(name="fmc", value="fmc")])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete)
async def bestscores(interaction: discord.Interaction, username: str = None, power_system: str = "modern", display_type: str = "standard", control_type: str = "unique"):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        
        result = stats.bestscores(
            username, 
            power_system=power_system.lower(), 
            display_type=display_type.lower(), 
            control_type=control_type.lower()
        )

        output, plain_output = _bestscores_outputs(result)
        view = await bestscores_view(username, power_system.lower(), display_type, control_type)
        await safe_followup(interaction, output, view=view, fallback_content=plain_output)
        
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ latestpbs (power system buttons) ═══════════
async def latestpbs_view(username, power_system, display_type, control_type):
    view = ui.View(timeout=None)
    systems = ["modern", "classic", "fmc"]

    async def make_callback(sys_label):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                sys = sys_label.lower()
                result = stats.latestpbs(
                    username,
                    power_system=sys,
                    display_type=display_type.lower(),
                    control_type=control_type.lower()
                )

                output = f"```\n{result}\n```"
                new_view = await latestpbs_view(username, sys, display_type, control_type)
                await safe_edit(interaction, output, view=new_view, fallback_content=result)

            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

        return cb

    for sys in systems:
        view.add_item(ui.Button(
            label=sys.capitalize(),
            style=discord.ButtonStyle.secondary if sys != power_system else discord.ButtonStyle.primary,
            disabled=(sys == power_system),
            custom_id=f"latestpbs_{sys}"
        ))

    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)

    return view

@client.tree.command(description="Show a player's latest PBs sorted by date")
@app_commands.describe(username="Player name (or part of it) – defaults to your Discord display name",
                       power_system="Power system: modern, classic, or fmc",
                       display_type="Display type for filtering scores",
                       control_type="Control type for filtering scores")
@app_commands.choices(power_system=[app_commands.Choice(name="modern", value="modern"), app_commands.Choice(name="classic", value="classic"), app_commands.Choice(name="fmc", value="fmc")])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete)
async def latestpbs(interaction: discord.Interaction, username: str = None, power_system: str = "modern", display_type: str = "standard", control_type: str = "unique"):
    await interaction.response.defer(ephemeral=False)
    try:
        if username is None:
            username = interaction.user.display_name
        
        result = stats.latestpbs(
            username, 
            power_system=power_system.lower(), 
            display_type=display_type.lower(), 
            control_type=control_type.lower()
        )

        output = f"```\n{result}\n```"
        view = await latestpbs_view(username, power_system.lower(), display_type, control_type)
        await safe_followup(interaction, output, view=view, fallback_content=result)
        
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ numwrs (filter type buttons only – no power buttons) ═══════════
async def numwrs_view(display_type, control_type, pb_type, filter_type, relay_type, power_system):
    view = ui.View(timeout=None)
    filters = ["NxM singles", "Square averages"]
    async def make_filter_cb(ft):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                result = stats.numwrs(display_type=display_type, control_type=control_type, pb_type=pb_type,
                                      filter_type=ft, relay_type=relay_type, power_system=power_system)
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
                new_view = await numwrs_view(display_type, control_type, pb_type, ft, relay_type, power_system)
                for child in new_view.children:
                    if isinstance(child, ui.Button):
                        child.callback = await make_filter_cb(child.label)
                await safe_edit(interaction, output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb
    for ft in filters:
        view.add_item(ui.Button(label=ft, style=discord.ButtonStyle.secondary if ft != filter_type else discord.ButtonStyle.primary,
                                disabled=(ft == filter_type), custom_id=f"numwrs_filter_{ft}"))
    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_filter_cb(child.label)
    return view

@client.tree.command(description="count world records per player with filters")
@app_commands.describe(display_type="display type for filtering scores",
                       control_type="control type for filtering scores",
                       pb_type="pb type for comparison (time, move, tps)",
                       filter_type="'NxM singles' (default, avglen=1 any size) or 'Square averages' (NxN puzzles only)",
                       relay_type="filter by game mode (default: Standard, or Marathon 10, x10, rel, eut, width...)",
                       power_system="power system: modern, classic, or fmc")
@app_commands.choices(power_system=[app_commands.Choice(name="modern", value="modern"), app_commands.Choice(name="classic", value="classic"), app_commands.Choice(name="fmc", value="fmc")])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete, pb_type=pb_type_autocomplete,
                           filter_type=filter_type_autocomplete, relay_type=relay_type_autocomplete)
async def numwrs(interaction: discord.Interaction, display_type: str = "standard", control_type: str = "unique", pb_type: str = "time",
                 filter_type: str = "NxM singles", relay_type: str = "Standard", power_system: str = "modern"):
    await interaction.response.defer(ephemeral=False)
    try:
        canonical_relay = parse_relay_type(relay_type)
        result = stats.numwrs(display_type=display_type, control_type=control_type, pb_type=pb_type,
                              filter_type=filter_type, relay_type=canonical_relay, power_system=power_system)
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
        view = await numwrs_view(display_type, control_type, pb_type, filter_type, canonical_relay, power_system)
        await safe_followup(interaction, output, view=view)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ Updated avglen autocomplete ═══════════
async def avglen_autocomplete(interaction, current):
    options = ["single", "ao5", "ao12", "ao25", "ao50", "ao100",
               "ao250", "ao500", "ao1000", "ao2500"]
    return [app_commands.Choice(name=o, value=o) for o in options if current.lower() in o.lower()][:25]

# ═══════════ Updated pb_type autocomplete ═══════════
async def pb_type_autocomplete(interaction, current):
    options = ["time", "move", "tps", "fmc", "fmc mtm"]
    return [app_commands.Choice(name=o, value=o) for o in options if current.lower() in o.lower()][:25]

# ═══════════ LB30 – modernised view (extended avglens + pb dropdown) ═══════════
class LB30View(ui.View):
    def __init__(self, puzzle_size, relay_type, avglen, display_type, control_type, pb_type):
        super().__init__(timeout=None)
        self.puzzle_size = puzzle_size
        self.relay_type = relay_type
        self.avglen = avglen
        self.display_type = display_type
        self.control_type = control_type
        self.pb_type = pb_type

        # ---------- Avglen buttons ----------
        avglens = ["single", "ao5", "ao12", "ao25", "ao50", "ao100",
                   "ao250", "ao500", "ao1000", "ao2500"]
        for a in avglens:
            style = discord.ButtonStyle.secondary if a != avglen else discord.ButtonStyle.primary
            btn = ui.Button(label=a, style=style, disabled=(a == avglen))
            btn.callback = self.make_avglen_callback(a)
            self.add_item(btn)

        # ---------- Puzzle size dropdown ----------
        sizes = [f"{i}x{i}" for i in range(2, 21)]
        options = [
            discord.SelectOption(label=s, value=s, default=(s == puzzle_size.lower()))
            for s in sizes
        ]
        self.puzzle_select = ui.Select(placeholder="Choose puzzle size", options=options)
        self.puzzle_select.callback = self.select_puzzle_callback
        self.add_item(self.puzzle_select)

        # ---------- Relay dropdown ----------
        relay_options_labels = [
            "Standard",
            "2-N relay",
            "Everything-up-to relay",
            "Width relay",
            "Height relay",
            "BLD",
            "x3",
            "x5",
            "x10",
            "x20",
            "x25",
            "x42",
            "x50",
            "x100"
        ]
        relay_options = [
            discord.SelectOption(label=rel, value=rel, default=(rel == relay_type))
            for rel in relay_options_labels
        ]
        self.relay_select = ui.Select(placeholder="Choose relay type", options=relay_options)
        self.relay_select.callback = self.select_relay_callback
        self.add_item(self.relay_select)

        # ---------- PB type dropdown ----------
        pb_options_labels = ["time", "move", "tps", "fmc", "fmc mtm"]
        pb_options = [
            discord.SelectOption(label=pb, value=pb, default=(pb.lower() == pb_type.lower()))
            for pb in pb_options_labels
        ]
        self.pb_select = ui.Select(placeholder="Choose PB type", options=pb_options)
        self.pb_select.callback = self.select_pb_callback
        self.add_item(self.pb_select)

    # synchronous factory returning the async callback
    def make_avglen_callback(self, new_avglen):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                result = stats.lb30(
                    puzzle_size=self.puzzle_size.lower(),
                    relay_type=self.relay_type,
                    avglen=new_avglen,
                    display_type=self.display_type.lower(),
                    control_type=self.control_type.lower(),
                    pb_type=self.pb_type.lower()
                )
                lines = result.strip().split('\n')
                body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
                info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
                body = "\n".join(body_lines)
                output = f"**Top 30 – {self.puzzle_size} {self.relay_type} {new_avglen}**\n```\n{body}\n```"
                if info_line:
                    output += f"\n_{info_line}_"
                new_view = LB30View(self.puzzle_size, self.relay_type, new_avglen,
                                    self.display_type, self.control_type, self.pb_type)
                await safe_edit(interaction, output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return callback

    async def select_puzzle_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_puzzle = self.puzzle_select.values[0]
        try:
            result = stats.lb30(
                puzzle_size=new_puzzle.lower(),
                relay_type=self.relay_type,
                avglen=self.avglen,
                display_type=self.display_type.lower(),
                control_type=self.control_type.lower(),
                pb_type=self.pb_type.lower()
            )
            lines = result.strip().split('\n')
            body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
            info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
            body = "\n".join(body_lines)
            output = f"**Top 30 – {new_puzzle} {self.relay_type} {self.avglen}**\n```\n{body}\n```"
            if info_line:
                output += f"\n_{info_line}_"
            new_view = LB30View(new_puzzle, self.relay_type, self.avglen,
                                self.display_type, self.control_type, self.pb_type)
            await safe_edit(interaction, output, view=new_view)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    async def select_relay_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_relay = self.relay_select.values[0]
        try:
            result = stats.lb30(
                puzzle_size=self.puzzle_size.lower(),
                relay_type=new_relay,
                avglen=self.avglen,
                display_type=self.display_type.lower(),
                control_type=self.control_type.lower(),
                pb_type=self.pb_type.lower()
            )
            lines = result.strip().split('\n')
            body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
            info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
            body = "\n".join(body_lines)
            output = f"**Top 30 – {self.puzzle_size} {new_relay} {self.avglen}**\n```\n{body}\n```"
            if info_line:
                output += f"\n_{info_line}_"
            new_view = LB30View(self.puzzle_size, new_relay, self.avglen,
                                self.display_type, self.control_type, self.pb_type)
            await safe_edit(interaction, output, view=new_view)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    async def select_pb_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_pb_type = self.pb_select.values[0]
        try:
            result = stats.lb30(
                puzzle_size=self.puzzle_size.lower(),
                relay_type=self.relay_type,
                avglen=self.avglen,
                display_type=self.display_type.lower(),
                control_type=self.control_type.lower(),
                pb_type=new_pb_type.lower()
            )
            lines = result.strip().split('\n')
            body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
            info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
            body = "\n".join(body_lines)
            output = f"**Top 30 – {self.puzzle_size} {self.relay_type} {self.avglen}**\n```\n{body}\n```"
            if info_line:
                output += f"\n_{info_line}_"
            new_view = LB30View(self.puzzle_size, self.relay_type, self.avglen,
                                self.display_type, self.control_type, new_pb_type)
            await safe_edit(interaction, output, view=new_view)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)


@client.tree.command(description="Top 30 scores for a puzzle/relay/avglen, shown as % of #1")
@app_commands.describe(
    puzzle_size="Puzzle size (e.g., 4x4, 3x3) – defaults to channel name or 4x4",
    relay_type="Game mode (Standard, Marathon 10, x10, rel, eut, width, bld …)",
    avglen="Average length: single, ao5, ao12, ao25, ao50, ao100, ao250, ao500, ao1000, ao2500",
    display_type="Display type for filtering scores",
    control_type="Control type for filtering scores",
    pb_type="PB type (time, move, tps, fmc, fmc mtm)"
)
@app_commands.autocomplete(
    relay_type=relay_type_autocomplete,
    avglen=avglen_autocomplete,
    display_type=display_type_autocomplete,
    control_type=control_type_autocomplete,
    pb_type=pb_type_autocomplete
)
async def lb30(
    interaction: discord.Interaction,
    puzzle_size: str = None,
    relay_type: str = "Standard",
    avglen: str = "single",
    display_type: str = "standard",
    control_type: str = "unique",
    pb_type: str = "time"
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
            pb_type=pb_type.lower()
        )
        lines = result.strip().split('\n')
        body_lines = lines[:-1] if len(lines) > 1 and lines[-1].startswith("[") else lines
        info_line = lines[-1] if len(lines) > 1 and lines[-1].startswith("[") else ""
        body = "\n".join(body_lines)
        output = f"**Top 30 – {puzzle_size} {canonical_relay} {avglen}**\n```\n{body}\n```"
        if info_line:
            output += f"\n_{info_line}_"

        view = LB30View(puzzle_size, canonical_relay, avglen, display_type, control_type, pb_type)
        await safe_followup(interaction, output, view=view)

    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ getreq (puzzle size buttons) – unchanged from previous fix ═══════════
async def getreq_view(tier_name, power_system, puzzle_size):
    view = ui.View(timeout=None)
    sizes_small = ["3x3", "4x4", "5x5", "6x6", "7x7", "8x8", "9x9", "10x10"]
    sizes_big   = ["12x12", "16x16", "20x20"]
    async def make_callback(size):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                result = stats.get_req(tier_name.lower(), power_system.lower(), size.lower())
                output = f"```\n{result}\n```\n_{power_system.lower()} | {size}_"
                new_view = await getreq_view(tier_name, power_system, size)
                for child in new_view.children:
                    if isinstance(child, ui.Button):
                        child.callback = await make_callback(child.label)
                await safe_edit(interaction, output, view=new_view)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb
    for s in sizes_small:
        style = discord.ButtonStyle.secondary if s != puzzle_size.lower() else discord.ButtonStyle.primary
        view.add_item(ui.Button(label=s, style=style, disabled=(s == puzzle_size.lower()), custom_id=f"getreq_{s}"))
    for s in sizes_big:
        style = discord.ButtonStyle.secondary if s != puzzle_size.lower() else discord.ButtonStyle.primary
        view.add_item(ui.Button(label=s, style=style, disabled=(s == puzzle_size.lower()), custom_id=f"getreq_{s}"))
    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)
    return view

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
        view = await getreq_view(tier_name, power_system, puzzle_size)
        await safe_followup(interaction, output, view=view)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ═══════════ compare command (with ANSI color gradient) ═══════════

def _get_ansi_color_for_pct(pct: float) -> str:
    if pct >= 10:
        return "32"   # strong positive
    elif pct >= 5:
        return "36"   # positive
    elif pct >= 1:
        return "34"   # slight positive
    elif pct > -1:
        return "37"   # neutral
    elif pct > -5:
        return "35"   # slight negative
    else:
        return "31"   # strong negative
        
def _get_ansi_color_for_pctBest(pct: float) -> str:
    # positive override
    if pct > -2:
        return "32"   # green
    elif pct > -4:
        return "34"   # blue (slight negative)
    elif pct > -6:
        return "36"   # cyan (mild negative)
    elif pct > -10:
        return "35"   # magenta (strong negative)
    else:
        return "31"   # red (extreme negative)        

def _format_compare_result(result: str, use_ansi: bool) -> str:
    lines = result.strip().split('\n')
    header = lines[0] if lines else "Comparison"
    formatted_lines = []
    info_line = ""

    for line in lines[1:]:
        if line.startswith("[Power:"):
            info_line = line
            continue

        parts = line.split('|')
        if len(parts) < 3:
            formatted_lines.append(line)
            continue

        pct_raw = parts[2].strip().replace('%', '')
        try:
            pct_val = float(pct_raw)
        except ValueError:
            formatted_lines.append(line)
            continue

        pct_text = _format_signed_pct(pct_val)
        if use_ansi:
            pct_text = _ansi_pct(pct_val, _get_ansi_color_for_pct(pct_val), abs(pct_val) >= 15)
        parts[2] = f" {pct_text} "
        formatted_lines.append('|'.join(parts))

    body = "\n".join(formatted_lines) if formatted_lines else "no common scores found"
    output = f"**{header}**\n{_wrap_code_block(body, 'ansi' if use_ansi else '')}"
    if info_line:
        output += f"\n_{info_line}_"
    return output

def _compare_outputs(result: str) -> tuple[str, str]:
    return _format_compare_result(result, True), _format_compare_result(result, False)

async def compare_view(username1, username2, power_system, display_type, control_type):
    view = ui.View(timeout=None)
    systems = ["modern", "classic", "fmc"]
    
    async def make_callback(sys_label):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                sys = sys_label.lower()
                result = stats.compare(username1, username2, power_system=sys, display_type=display_type.lower(), control_type=control_type.lower())
                output, plain_output = _compare_outputs(result)
                new_view = await compare_view(username1, username2, sys, display_type, control_type)
                await safe_edit(interaction, output, view=new_view, fallback_content=plain_output)
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        return cb

    for sys in systems:
        view.add_item(ui.Button(
            label=sys.capitalize(),
            style=discord.ButtonStyle.secondary if sys != power_system else discord.ButtonStyle.primary,
            disabled=(sys == power_system),
            custom_id=f"compare_{sys}"
        ))

    for child in view.children:
        if isinstance(child, ui.Button):
            child.callback = await make_callback(child.label)

    return view

@client.tree.command(description="Compare two players' scores across all categories")
@app_commands.describe(
    username1="First player name (or part of it)",
    username2="Second player name (or part of it)",
    power_system="Power system: modern, classic, or fmc",
    display_type="Display type for filtering scores",
    control_type="Control type for filtering scores"
)
@app_commands.choices(power_system=[
    app_commands.Choice(name="modern", value="modern"),
    app_commands.Choice(name="classic", value="classic"),
    app_commands.Choice(name="fmc", value="fmc")
])
@app_commands.autocomplete(display_type=display_type_autocomplete, control_type=control_type_autocomplete)
async def compare(
    interaction: discord.Interaction,
    username1: str,
    username2: str,
    power_system: str = "modern",
    display_type: str = "standard",
    control_type: str = "unique"
):
    await interaction.response.defer(ephemeral=False)
    try:
        result = stats.compare(
            username1, username2,
            power_system=power_system.lower(),
            display_type=display_type.lower(),
            control_type=control_type.lower()
        )
        output, plain_output = _compare_outputs(result)
        view = await compare_view(username1, username2, power_system.lower(), display_type, control_type)
        await safe_followup(interaction, output, view=view, fallback_content=plain_output)

    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"error: {str(e)}", ephemeral=True)

# ====================== UPDATEWEB (unchanged) ======================
@client.tree.command(description="Update Slidysim Web scores data")
async def updateweb(interaction: discord.Interaction):
    global updateweb_running
    await interaction.response.defer(ephemeral=False)
    try:
        if updateweb_running:
            await interaction.followup.send("⚠️ Web update is already in progress. Please wait.", ephemeral=True)
            return
        script_path = os.getenv("UPDATEWEB_SCRIPT_PATH")
        if not script_path or not os.path.exists(script_path):
            await interaction.followup.send("Error: script path invalid.", ephemeral=True)
            return
        updateweb_running = True
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
        async def animate():
            states = [
                ":zzz: (web update is taking about 40 seconds) :zzz:",
                ":zzz: :zzz: (web update is taking about 40 seconds) :zzz: :zzz: ",
                ":zzz: :zzz: :zzz: (web update is taking about 40 seconds) :zzz: :zzz: :zzz: "
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
        await msg.edit(content=f""":egg: Web backup updated successfully! (took {time_str})

**Leaderboard URL:** https://slidysim.github.io/lb
**Web-only scores:** https://slidysim.github.io/archive""")
    except Exception as e:
        await interaction.followup.send(f"❌ Error running web update: {str(e)}")
    finally:
        updateweb_running = False

# ====================== ADMIN COMMANDS (unchanged, only included for completeness) ======================

@client.tree.command(description="[Admin only] Get best marathon splits for NxM puzzles in slidysim exe")
@app_commands.describe(puzzle_size="Puzzle size in NxM format (e.g. 3x3)")
async def admin_marathons_exe(interaction: discord.Interaction, puzzle_size: str):
    await interaction.response.defer(ephemeral=False)
    try:
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return

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

        description = "```\n"
        description += f"{'Split':<6}{'Time':<10}{'From':<14}{'Date':<12}\n"
        description += "-" * 49 + "\n"
        
        for x_num in sorted(best_splits.keys()):
            if x_num > 42:
                continue
            
            split = best_splits[x_num]
            date_only = datetime.fromtimestamp(split['timestamp'] / 1000).strftime('%Y-%m-%d')
            description += (
                f"x{x_num:<5}{split['time']:>6.3f}  "
                f"{split['fulltime']/1000:>6.3f} x{split['marathon_length']:<7} "
                f"{date_only}\n"
            )
        description += "```"

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

@client.tree.command(description="[Admin only] Show your total playtime by puzzle size in slidysim exe")
@app_commands.describe(
    timeframe="Optional filter: all (default), last N hours, day, week, or month"
)
async def admin_playtime_exe(interaction: discord.Interaction, timeframe: str = "all"):
    try:
        await interaction.response.defer(ephemeral=False)
        
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        params = []
        usehours = False
        since = None
        since_ms = None

        if timeframe.lower() != "all":
            now = datetime.now()
            
            if timeframe.isdigit():
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

            since_ms = int(since.timestamp() * 1000)
            params.append(since_ms)
        else:
            since_ms = 0
            params.append(since_ms)

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
        
        combined_results.sort(key=lambda x: x["hours"], reverse=True)
        top_results = combined_results[:20]

        if not top_results:
            await interaction.followup.send("No playtime data found.", ephemeral=True)
            return

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

        embed = discord.Embed(
            title=f"🕹️ SlidySim Playtime Summary ({timeframe})",
            color=discord.Color.blurple()
        )

        table_lines = [" Size |  Time  |Attempts| Solves | Skips", "------|--------|--------|--------|-------"]

        for row in top_results:
            total_minutes = int(row["hours"] * 60)
            h = total_minutes // 60
            m = total_minutes % 60
            time_str = f"{h}:{m:02d}"
            size = f"{row['width']}x{row['height']}".ljust(5)
            table_lines.append(f"{size} | {time_str:<6} | {row['attempts']:<6} | {row['solves']:<6} | {row['skips']}")

        embed.description = "```\n" + "\n".join(table_lines) + "\n```"
        
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

@client.tree.command(description="[Admin only] Get your personal best history for a specific puzzle in slidysim exe")
@app_commands.describe(
    size="Puzzle size in NxM format (e.g., 4x5, 10x18, 5x5)",
    pbtype="Type of personal best to track (time = lower better, moves = lower better, tps = higher better)",
    time_limit="Optional maximum time in seconds (only solves under this count toward PBs)",
    moves_limit="Optional maximum moves (only solves under this count toward PBs)",
    tps_limit="Optional minimum TPS (only solves above this count toward PBs)",
    hours_limit="Optional time window in hours (e.g., 24 for last day; defaults to all time)"
)
async def admin_pbhistory_exe(
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
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        try:
            width, height = map(int, size.lower().split('x'))
        except:
            await interaction.followup.send(
                "Invalid size format. Please use NxM format (e.g., 4x5, 10x18).",
                ephemeral=False
            )
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        timestamp_cutoff = None
        if hours_limit is not None:
            timestamp_cutoff = int(timemodule.time() - (hours_limit * 3600)) * 1000
        
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
        
        if timestamp_cutoff is not None:
            query += " AND b.timestamp >= ?"
            params.append(timestamp_cutoff)
        
        if time_limit is not None:
            query += " AND a.time < ?"
            params.append(int(time_limit * 1000))
            
        if moves_limit is not None:
            query += " AND a.moves < ?"
            params.append(moves_limit * 1000)
            
        if tps_limit is not None:
            query += " AND a.tps > ?"
            params.append(tps_limit * 1000)
        
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
        
        if pbtype in ["time", "moves"]:
            best_value = float('inf')
            is_better = lambda val: val < best_value
        else:
            best_value = float('-inf')
            is_better = lambda val: val > best_value
        
        pb_history = []
        for time_ms, moves_ms, tps_ms, ts_ms in rows:
            val = time_ms if pbtype == "time" else moves_ms if pbtype == "moves" else tps_ms
            if is_better(val):
                pb_history.append((time_ms, moves_ms, tps_ms, ts_ms))
                best_value = val
        
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

@client.tree.command(description="[Admin only] Get your best solves ever for a specific puzzle in slidysim exe (not just records)")
@app_commands.describe(
    size="Puzzle size in NxM format (e.g., 4x5, 10x18, 5x5)",
    pbtype="Sort by: time (lower better), moves (lower better), tps (higher better)",
    time_limit="Optional maximum time in seconds",
    moves_limit="Optional maximum moves",
    tps_limit="Optional minimum TPS",
    hours_limit="Optional time window in hours (e.g., 24 for last day; defaults to all time)"
)
async def admin_coolsolves_exe(
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
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        try:
            width, height = map(int, size.lower().split('x'))
        except:
            await interaction.followup.send(
                "Invalid size format. Please use NxM format (e.g., 4x5, 10x18).",
                ephemeral=False
            )
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        timestamp_cutoff = None
        if hours_limit is not None:
            timestamp_cutoff = int(timemodule.time() - (hours_limit * 3600)) * 1000
        
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
        
        if timestamp_cutoff is not None:
            query += " AND b.timestamp >= ?"
            params.append(timestamp_cutoff)
        
        if time_limit is not None:
            query += " AND a.time < ?"
            params.append(int(time_limit * 1000))
            
        if moves_limit is not None:
            query += " AND a.moves < ?"
            params.append(moves_limit * 1000)
            
        if tps_limit is not None:
            query += " AND a.tps > ?"
            params.append(tps_limit * 1000)
        
        # Sort best first: time/moves = ascending, tps = descending
        if pbtype == "time":
            query += " ORDER BY a.time ASC"
        elif pbtype == "moves":
            query += " ORDER BY a.moves ASC"
        else:
            query += " ORDER BY a.tps DESC"
        
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
        
        # Build table header
        header = " Time (s) | Moves |  TPS   | Date (UTC)\n"
        header += "----------|-------|--------|--------------"
        
        table_lines = []
        for time_ms, moves_ms, tps_ms, ts_ms in rows:
            time_s = time_ms / 1000
            moves = int(moves_ms / 1000)
            tps = tps_ms / 1000
            date_str = datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
            line = f"{time_s:>9.3f} | {moves:>5} | {tps:>6.3f} | {date_str}"
            
            # Check if adding this line would exceed 2000 chars in the final message
            candidate_rows = table_lines + [line]
            candidate_text = "\n".join(candidate_rows)
            full_candidate = f"```\n{header}\n{candidate_text}\n```"
            
            if len(full_candidate) > 2000:
                break
            
            table_lines.append(line)
        
        total_solves = len(rows)
        shown_solves = len(table_lines)
        
        filter_info = []
        if time_limit is not None:
            filter_info.append(f"Time < {time_limit}s")
        if moves_limit is not None:
            filter_info.append(f"Moves < {moves_limit}")
        if tps_limit is not None:
            filter_info.append(f"TPS > {tps_limit}")
        if hours_limit is not None:
            filter_info.append(f"Last {hours_limit}h")
        
        metadata = f"Filters: {', '.join(filter_info) if filter_info else 'None'}"
        if shown_solves < total_solves:
            metadata += f" | Showing {shown_solves}/{total_solves} solves (truncated to fit Discord)"
        else:
            metadata += f" | Total: {total_solves} solves"
        
        embed = discord.Embed(
            title=f"🔥 Best Solves ({pbtype}) — {width}x{height}",
            color=discord.Color.green()
        )
        
        embed.description = (
            f"```\n{header}\n" + "\n".join(table_lines) + "\n```\n"
            f"{metadata}"
        )
        
        await interaction.followup.send(embed=embed, ephemeral=False)

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}", ephemeral=False)
    finally:
        if 'conn' in locals():
            conn.close()

@client.tree.command(description="[Admin only] Get your personal best solve for a specific puzzle size in slidysim exe")
@app_commands.describe(
    size="Puzzle size in NxM format (e.g., 4x5, 10x18, 5x5)",
    pbtype="Type of personal best to retrieve",
    time_limit="Optional maximum time in seconds",
    moves_limit="Optional maximum moves",
    hours_limit="Optional time window in hours (e.g., 24 for last day)",
    create_video="Also generate an MP4 replay video (may take a moment)",
    quality="Render quality: 1 (High, default) or 2 (Ultra)",
    compression="Video compression CRF 10–40, lower = better quality (default: 18)",
    fps="Output framerate 1–240 (default: 60)",
    force_fringe="Force fringe color pattern"
)
@app_commands.choices(
    quality=[
        app_commands.Choice(name="1 — High (default)", value=1),
        app_commands.Choice(name="2 — Ultra", value=2),
    ]
)
async def admin_getpb_exe(
    interaction: discord.Interaction,
    size: str,
    pbtype: Literal["time", "moves", "tps"] = "time",
    time_limit: float = None,
    moves_limit: int = None,
    hours_limit: int = None,
    create_video: bool = False,
    quality: int = 1,
    compression: int = 18,
    fps: int = 60,
    force_fringe: bool = False
):
    await interaction.response.defer(ephemeral=False)
    
    try:
        if not (1 <= fps <= 240):
            await interaction.followup.send("FPS must be between 1 and 240.", ephemeral=True)
            return
        if not (10 <= compression <= 40):
            await interaction.followup.send("Compression must be between 10 and 40.", ephemeral=True)
            return

        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        try:
            width, height = map(int, size.lower().split('x'))
        except:
            await interaction.followup.send(
                "Invalid size format. Please use NxM format (e.g., 4x5, 10x18).",
                ephemeral=False
            )
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        timestamp_cutoff = None
        if hours_limit is not None:
            timestamp_cutoff = int(timemodule.time() - (hours_limit * 3600)) * 1000
        
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
        
        if timestamp_cutoff is not None:
            query += " AND b.timestamp >= ?"
            params.append(timestamp_cutoff)
            
        if time_limit is not None:
            query += " AND a.time < ?"
            params.append(int(time_limit * 1000))
            
        if moves_limit is not None:
            query += " AND a.moves < ?"
            params.append(moves_limit * 1000)
        
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
            
        column_names = [
            'id', 'time', 'moves', 'tps', 'scramble', 'solution', 
            'move_times_start_id', 'move_times_end_id', 'timestamp', 'width', 'height'
        ]
        row_map = dict(zip(column_names, solve_row))
        
        starting_point = row_map['move_times_start_id']
        ending_point = row_map['move_times_end_id']
        cursor.execute(
            "SELECT time FROM move_times WHERE id >= ? AND id <= ?", 
            (starting_point, ending_point)
        )
        sequence = [row[0] for row in cursor.fetchall()]
        
        width = row_map['width']
        height = row_map['height']
        time = row_map['time'] / 1000
        moves = int(row_map['moves'] / 1000)
        tps = row_map['tps'] / 1000
        scramble = row_map['scramble']
        solution = row_map['solution']
        timestamp = datetime.fromtimestamp(row_map['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        
        slidy_url = "https://slidysim.github.io/replay?r=" + compress_array_to_string([solution, row_map['tps'], scramble, sequence])
        try:
            splits_data = getsplits(slidy_url)
        except Exception:
            splits_data = "splits are failed"

        url_length = len(slidy_url)
        extra_note = ""

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

        pb_type_display = {
            "time": f"Fastest Time: {time:.3f}s",
            "moves": f"Fewest Moves: {moves}",
            "tps": f"Highest TPS: {tps:.2f}"
        }[pbtype]

        time_window_info = f" (last {hours_limit} hours)" if hours_limit else ""

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

        video_file = None
        video_tmpdir = None
        if create_video:
            msg = await interaction.followup.send("🎥 Generating replay video...", ephemeral=False)
            try:
                video_file, video_tmpdir = await generate_replay_video(
                    msg, slidy_url,
                    quality=quality,
                    compression=compression,
                    fps=fps,
                    force_fringe=force_fringe
                )
            except Exception as e:
                await msg.edit(content=f"❌ Video generation failed: {e}")
                video_file = None

        if use_button:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View on SlidySim", url=final_link, style=discord.ButtonStyle.link))
            if video_file:
                await interaction.followup.send(embed=embed, view=view, file=video_file, ephemeral=False)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        else:
            if video_file:
                await interaction.followup.send(content=f"# [View on SlidySim]({final_link})", embed=embed, file=video_file, ephemeral=False)
            else:
                await interaction.followup.send(content=f"# [View on SlidySim]({final_link})", embed=embed, ephemeral=False)

        if video_tmpdir:
            import shutil
            shutil.rmtree(video_tmpdir, ignore_errors=True)

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}", ephemeral=False)
    finally:
        if 'conn' in locals():
            conn.close()

@client.tree.command(description="[Admin only] Get latest slidysim exe solve")
async def admin_latest_exe(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    try:
        if interaction.user.id != YOUR_USER_ID:
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(single_solves)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        cursor.execute("SELECT * FROM single_solves ORDER BY id DESC LIMIT 1")
        highest_single_solve_row = cursor.fetchone()
        
        if not highest_single_solve_row:
            await interaction.followup.send("No solves found in database", ephemeral=False)
            return
            
        row_map = dict(zip(column_names, highest_single_solve_row))
        
        starting_point = row_map['move_times_start_id']
        cursor.execute(f"SELECT time FROM move_times WHERE id >= {starting_point}")
        sequence = [row[0] for row in cursor.fetchall()]
        
        width = row_map['width']
        height = row_map['height']
        time = row_map['time'] / 1000
        moves = int(row_map['moves'] / 1000)
        tps = row_map['tps'] / 1000
        scramble = row_map['scramble']
        solution = row_map['solution']
        
        slidy_url = "https://slidysim.github.io/replay?r=" + compress_array_to_string([solution, row_map['tps'], scramble, sequence])
        try:
            splits_data = getsplits(slidy_url)
        except Exception:
            splits_data = "splits are failed"

        url_length = len(slidy_url)
        timestamp = str(int(timemodule.time()))
        extra_note = ""

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

        try:
            splits_data = getsplits(file_content)
        except Exception:
            splits_data = "splits are failed"

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


@client.tree.command(description="Generate a replay link from your solution or replay URL")
@app_commands.describe(
    solution_or_url="Solution string (e.g., R2ULDLU2R3D3L3UR2U2L2) or a SlidySim replay URL (starts with https://)",
    file="Optional .txt file containing the solution or a replay URL",
    scramble="Optional scramble string (e.g., '7 1 0 3/5 9 2 8/...')",
    size="Optional puzzle size (e.g., '4x4', '3x3')",
    tps="Optional TPS value (do not use with time)",
    time="Optional solve time in seconds (e.g., 0.909) — do not use with tps",
    movetimes="Optional comma-separated move times in ms (e.g., 0,16,50,90326947,...)",
    create_video="Also generate an MP4 replay video (only for solutions < 2000 moves)",
    quality="Render quality: 1 (High, default) or 2 (Ultra)",
    compression="Video compression CRF 10–40, lower = better quality but larger file (default: 18)",
    fps="Output framerate 1–240 (default: 60)",
    force_fringe="Force fringe color pattern instead of auto-detecting grids"
)
@app_commands.choices(
    quality=[
        app_commands.Choice(name="1 — High (default)", value=1),
        app_commands.Choice(name="2 — Ultra", value=2),
    ]
)
async def makereplay(
    interaction: discord.Interaction,
    solution_or_url: str = None,
    file: discord.Attachment = None,
    scramble: str = None,
    size: str = None,
    tps: float = None,
    time: float = None,
    movetimes: str = None,
    create_video: bool = False,
    quality: int = 1,
    compression: int = 18,
    fps: int = 60,
    force_fringe: bool = False
):
    await interaction.response.defer(ephemeral=False)

    try:
        if not (1 <= fps <= 240):
            await interaction.followup.send("FPS must be between 1 and 240.", ephemeral=True)
            return
        if not (10 <= compression <= 40):
            await interaction.followup.send("Compression must be between 10 and 40.", ephemeral=True)
            return

        if tps is not None and time is not None:
            await interaction.followup.send("Provide either tps or time, not both.", ephemeral=True)
            return

        if file and solution_or_url:
            await interaction.followup.send("Provide either a file or solution text, not both.", ephemeral=True)
            return

        is_url_input = False

        if file:
            if not file.filename.endswith('.txt'):
                await interaction.followup.send("Please upload a .txt file.", ephemeral=True)
                return
            content = await file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            raw = content.strip()
            if raw.startswith(('http://', 'https://')):
                is_url_input = True
                replay_url = raw
            else:
                solution = raw
        elif solution_or_url:
            raw = solution_or_url.strip()
            if raw.startswith(('http://', 'https://')):
                is_url_input = True
                replay_url = raw
            else:
                solution = raw
        else:
            await interaction.followup.send("You must provide a solution text, a replay URL, or upload a .txt file.", ephemeral=True)
            return

        if is_url_input:
            url_solution, url_tps, url_scramble, url_movetimes = parse_replay_url(replay_url)
            solution = url_solution
            if tps is None:
                tps = url_tps
            if scramble is None:
                scramble = url_scramble
            if isinstance(url_movetimes, list) and movetimes is None:
                movetimes = url_movetimes
        else:
            parsed_size = None
            if size:
                parts = size.lower().split('x')
                if len(parts) == 2:
                    try:
                        parsed_size = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        await interaction.followup.send(f"Invalid size format: '{size}'. Use e.g. '4x4'.", ephemeral=True)
                        return
                else:
                    await interaction.followup.send(f"Invalid size format: '{size}'. Use e.g. '4x4'.", ephemeral=True)
                    return

            parsed_movetimes = -1
            if movetimes:
                try:
                    parsed_movetimes = [int(x.strip()) for x in movetimes.split(',')]
                except ValueError:
                    await interaction.followup.send("Invalid movetimes format. Provide comma-separated integers (ms).", ephemeral=True)
                    return

            gen = ReplayGenerator()
            kwargs = {}
            if parsed_size:
                kwargs['size'] = parsed_size
            if scramble:
                kwargs['scramble'] = scramble
            if parsed_movetimes != -1:
                kwargs['movetimes'] = parsed_movetimes
            if tps is not None:
                kwargs['tps'] = tps
            if time is not None:
                kwargs['time'] = time

            try:
                replay_url = gen.generate_simple_replay(solution, **kwargs)
            except Exception as e:
                await interaction.followup.send(f"DEBUG generate_simple_replay fail: {type(e).__name__}: {e}", ephemeral=True)
                return

        try:
            splits_data = getsplits(replay_url)
        except Exception as e:
            await interaction.followup.send(f"DEBUG getsplits fail: {type(e).__name__}: {e}", ephemeral=True)
            splits_data = "splits are failed"

        # Video generation
        video_file = None
        video_tmpdir = None
        if create_video:
            sol_expanded = expand_solution(solution)
            if len(sol_expanded) < 2000:
                msg = await interaction.followup.send("🎥 Generating replay video...", ephemeral=False)
                try:
                    video_file, video_tmpdir = await generate_replay_video(
                        msg, replay_url,
                        quality=quality,
                        compression=compression,
                        fps=fps,
                        force_fringe=force_fringe
                    )
                except Exception as e:
                    await msg.edit(content=f"❌ Video generation failed: {e}")

        url_length = len(replay_url)
        link_md = f"[Replay]({replay_url})"

        async def _try_send(content=None, file=None):
            kw = {}
            if content is not None:
                kw['content'] = content
            if file is not None:
                kw['file'] = file
            try:
                return await interaction.followup.send(**kw)
            except Exception as e:
                await interaction.followup.send(f"DEBUG send fail: {type(e).__name__}: {e}", ephemeral=True)
                return None

        if url_length <= 1950:
            if splits_data and splits_data not in ("Invalid splits data", "splits are failed"):
                content = f"```\n{splits_data}\n```\n{link_md}"
            else:
                content = link_md
            if len(content) <= 2000:
                await _try_send(content=content, file=video_file)
            else:
                f = discord.File(io.BytesIO(content.encode('utf-8')), filename="replay_result.txt")
                await _try_send(content="Result too large for message — see attached file.", file=f)
                if video_file:
                    await _try_send(file=video_file)
        else:
            file_content_str = f"Replay URL (too long for direct link):\n{replay_url}"
            f = discord.File(io.BytesIO(file_content_str.encode('utf-8')), filename="replay_url.txt")
            if splits_data and splits_data not in ("Invalid splits data", "splits are failed"):
                await _try_send(content=f"```\n{splits_data}\n```", file=f)
            else:
                await _try_send(content="Replay URL too long for a direct link — see attached file.", file=f)
            if video_file:
                await _try_send(file=video_file)

        if video_tmpdir:
            import shutil
            shutil.rmtree(video_tmpdir, ignore_errors=True)

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)


@client.tree.command(description="[Admin only] Get a short URL one-click button from Replay File or URL")
@app_commands.describe(
    file="Optional .txt file containing the replay URL",
    url="Optional replay URL directly (alternative to file)",
    metadata="Optional metadata text for the embed title",
    create_video="Also generate an MP4 replay video (may take a moment)",
    quality="Render quality: 1 (High, default) or 2 (Ultra)",
    compression="Video compression CRF 10–40, lower = better quality (default: 18)",
    fps="Output framerate 1–240 (default: 60)",
    force_fringe="Force fringe color pattern"
)
@app_commands.choices(
    quality=[
        app_commands.Choice(name="1 — High (default)", value=1),
        app_commands.Choice(name="2 — Ultra", value=2),
    ]
)
async def admin_replay(
    interaction: discord.Interaction,
    file: discord.Attachment = None,
    url: str = None,
    metadata: str = None,
    create_video: bool = False,
    quality: int = 1,
    compression: int = 18,
    fps: int = 60,
    force_fringe: bool = False
):
    ALLOWED_USER_IDS = [YOUR_USER_ID]

    if not (1 <= fps <= 240):
        await interaction.response.send_message("FPS must be between 1 and 240.", ephemeral=True)
        return
    if not (10 <= compression <= 40):
        await interaction.response.send_message("Compression must be between 10 and 40.", ephemeral=True)
        return

    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    if not file and not url:
        await interaction.response.send_message("Provide a file or a replay URL.", ephemeral=True)
        return

    if file and url:
        await interaction.response.send_message("Provide either a file or a URL, not both.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    if url:
        file_content = url
        filename_ts = str(int(timemodule.time()))
        filename = f"{filename_ts}_url.txt"
    else:
        if not file.filename.endswith('.txt'):
            await interaction.followup.send("Please upload a .txt file.", ephemeral=True)
            return
        filename_ts = str(int(timemodule.time()))
        filename = f"{filename_ts}.txt"
        file_content = (await file.read()).decode('utf-8')

    try:
        slidy_url = save_replay_and_generate_url(file_content, filename)
    except Exception as e:
        await interaction.followup.send(f"Error saving file or pushing to Git: {str(e)}", ephemeral=True)
        return

    try:
        splits_data = getsplits(file_content)
    except Exception:
        splits_data = "splits are failed"

    embed = discord.Embed(
        title=f"🌟 {metadata or 'Replay Link'} 🌟",
        description=f"```\n{splits_data}\n```*Replay may take a minute to activate.*" if splits_data != "Invalid splits data" else "*Replay may take a minute to activate.*",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Click the button below to view.")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="View on SlidySim", url=slidy_url, style=discord.ButtonStyle.link))

    video_file = None
    video_tmpdir = None
    if create_video:
        msg = await interaction.followup.send("🎥 Generating replay video...", ephemeral=False)
        try:
            video_file, video_tmpdir = await generate_replay_video(
                msg, file_content,
                quality=quality,
                compression=compression,
                fps=fps,
                force_fringe=force_fringe
            )
        except Exception as e:
            await msg.edit(content=f"❌ Video generation failed: {e}")

    if video_file:
        await interaction.followup.send(embed=embed, view=view, file=video_file, ephemeral=False)
    else:
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    if video_tmpdir:
        import shutil
        shutil.rmtree(video_tmpdir, ignore_errors=True)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

client.run(token)
