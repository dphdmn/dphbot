#!/usr/bin/env python3
"""
fetch.py

Usage: python fetch_and_merge.py <displayType> <controlType> <pbType>

All arguments are numeric IDs (as defined in the JavaScript maps).
Output: merged_leaderboard.txt  (JSON string of the merged score list)
"""

import sys
import json
import time
import requests
import lzma
import io
import os
from power_data import *

# ---------- helper functions ----------

def get_game_mode(solve_type, marathon_length):
    """Convert solve_type + marathon_length to a readable game mode string."""
    if solve_type in SOLVE_TYPE_MAP:
        return SOLVE_TYPE_MAP[solve_type]
    if solve_type is not None and solve_type >= 7:
        return f"Marathon {marathon_length}"
    return "Unknown"

def apply_rename(name):
    """Replace old usernames with new ones according to RENAME_MAP."""
    for new_name, old_name in RENAME_MAP.items():
        if name == old_name:
            return new_name
    return name

def parse_scores_text(text, display_type_str, pb_type_str, is_archive=False):
    """
    Parse the semicolon-separated score text returned by the API or archive.
    Returns a list of score dictionaries ready for merging.
    """
    lines = [line for line in text.split(';') if line.strip()]
    if not lines:
        return []

    # first line = user map (id:username pairs)
    user_map_line = lines[0]
    usermap = {}
    if user_map_line:
        for pair in user_map_line.split(','):
            if ':' in pair:
                username, uid = pair.split(':', 1)
                usermap[uid] = username

    score_fields = [
        'size_n', 'size_m', 'pb_type', 'control_type', 'userid',
        'solve_type', 'marathon_length', 'average_type', 'time',
        'moves', 'tps', 'timestamp', 'solution_available', 'videolink'
    ]

    scores = []
    for line in lines[1:]:
        values = line.split(',')
        if len(values) < len(score_fields):
            continue

        raw = {}
        for i, field in enumerate(score_fields):
            if field == "videolink":
                raw[field] = values[i] if values[i] and values[i] != '-1' else None
            elif field == "solution_available" and is_archive:
                raw[field] = False
            else:
                try:
                    raw[field] = int(values[i]) if values[i] else None
                except ValueError:
                    raw[field] = None

        size_n = raw['size_n']
        size_m = raw['size_m']
        control = raw['control_type']
        solve_type = raw['solve_type']
        marathon_len = raw['marathon_length']
        game_mode = get_game_mode(solve_type, marathon_len)

        userid = str(raw['userid']) if raw['userid'] is not None else ''
        name = usermap.get(userid, userid)
        name = apply_rename(name)

        scores.append({
            'width': size_n,
            'height': size_m,
            'leaderboardType': pb_type_str,
            'controls': CONTROL_TYPE_MAP.get(control, str(control)),
            'gameMode': game_mode,
            'displayType': display_type_str,
            'nameFilter': name,
            'avglen': raw['average_type'],
            'time': raw['time'],
            'moves': raw['moves'],
            'tps': raw['tps'],
            'timestamp': raw['timestamp'],
            'solve_data_available': raw['solution_available'],
            'videolink': raw['videolink']
        })

    return scores

def get_category_key(score):
    """Build a unique key for a category, as in the JS function."""
    return f"{score['width']}-{score['height']}-{score['leaderboardType']}-{score['controls']}-{score['gameMode']}-{score['displayType']}-{score['nameFilter']}-{score['avglen']}"

def is_better(web, live, leaderboard_type):
    """
    Determine if web score is strictly better than live score.
    Implements the same logic as JS isBetter().
    Returns False if web has no valid score (-1).
    Returns True if live has no valid score (-1) but web does.
    """
    # Map type to the value getter and comparison direction
    if leaderboard_type == "tps":
        get_val = lambda s: s.get('tps', -1)
        higher_is_better = True
    elif leaderboard_type == "move":
        get_val = lambda s: s.get('moves', -1)
        higher_is_better = False
    else:  # "time", "FMC", "FMC MTM"
        get_val = lambda s: s.get('time', -1)
        higher_is_better = False

    web_val = get_val(web)
    live_val = get_val(live)

    # Handle -1 (no valid score) cases
    if web_val == -1 or web_val is None:
        return False
    if live_val == -1 or live_val is None:
        return True

    if higher_is_better:
        return web_val > live_val
    else:
        return web_val < live_val


def merge_web_pbs(live_data, web_data):
    """
    Merge live and web scores, preferring the better one.
    Marks each score with an 'isWeb' boolean.
    """
    merged = {}
    for s in live_data:
        s['isWeb'] = False
        merged[get_category_key(s)] = s

    for w in web_data:
        key = get_category_key(w)
        if key not in merged or is_better(w, merged[key], w['leaderboardType']):
            w['isWeb'] = True
            merged[key] = w
        # If live score is better, it stays in the map with isWeb: False

    return list(merged.values())

# ---------- main fetching functions ----------

def fetch_live_scores(display_type, control_type, pb_type):
    if (control_type > 3):
        return ""
    if (pb_type > 3):
        return ""
    """POST to the live API and return the raw text response."""
    url = f"{BASE_URL}/api/getScores"
    payload = {
        "display_type": display_type,
        "control_type": control_type,
        "pb_type": pb_type
    }
    headers = {
        "Authorization": GUEST_TOKEN,
        "Content-Type": "application/json"
    }
    resp = requests.post(url, json=payload, headers=headers)
    print(display_type, control_type)
    resp.raise_for_status()
    return resp.text

def get_latest_web_archive_filename():
    """
    Query the GitHub repository for the latest archive file that contains 'web'.
    Returns the filename (without path) or None.
    """
    url = "https://api.github.com/repos/dphdmn/slidyarch/contents/archives"
    resp = requests.get(url)
    resp.raise_for_status()
    files = resp.json()
    # filter .lzma files containing 'web'
    candidates = [f['name'] for f in files if f['name'].endswith('.lzma') and 'web' in f['name']]
    candidates.sort(reverse=True)
    return candidates[0] if candidates else None

def fetch_and_decompress_archive(filename):
    """
    Download an archive from GitHub raw, decompress it, and parse the JSON.
    Returns the whole archive dict or raises.
    """
    raw_url = f"https://raw.githubusercontent.com/dphdmn/slidyarch/main/archives/{filename}"
    resp = requests.get(raw_url)
    resp.raise_for_status()
    # The JS uses xzwasm (XZ compression). Python's lzma supports XZ.
    try:
        with lzma.open(io.BytesIO(resp.content), 'rt', format=lzma.FORMAT_XZ) as f:
            decompressed = f.read()
    except lzma.LZMAError:
        # fallback: try auto detection
        with lzma.open(io.BytesIO(resp.content), 'rt') as f:
            decompressed = f.read()
    return json.loads(decompressed)

def get_archive_scores(display_type, control_type, pb_type):
    """
    Fetch the latest web archive, extract the combination for the given IDs,
    and return the raw semicolon-separated text (or empty string if not found).
    """
    filename = get_latest_web_archive_filename()
    if not filename:
        print("No web archive found.", file=sys.stderr)
        return ""

    archive = fetch_and_decompress_archive(filename)
    key = f"{display_type}_{control_type}_{pb_type}"
    return archive.get("data", {}).get(key, "")

# ---------- helper functions ----------

# ---------- configuration ----------
MERGED_FOLDER = "merged_leaderboards"


def get_combo_filename(display_type, control_type, pb_type):
    """Generate filename for a specific combination."""
    return f"{display_type}_{control_type}_{pb_type}.txt"


def get_latest_log_mtime(logs_dir):
    """Get the modification time of the most recent log file in the logs directory."""
    if not os.path.exists(logs_dir):
        return None
    
    latest_time = 0
    for filename in os.listdir(logs_dir):
        if filename.endswith('.log'):
            filepath = os.path.join(logs_dir, filename)
            mtime = os.path.getmtime(filepath)
            if mtime > latest_time:
                latest_time = mtime
    
    return latest_time if latest_time > 0 else None


def should_fetch_combo(logs_dir, combo_path):
    """Check if we need to fetch this combination based on log file changes."""
    latest_log_mtime = get_latest_log_mtime(logs_dir)
    if latest_log_mtime is None:
        print("No log files found. Proceeding with fetch.")
        return True
    
    if not os.path.exists(combo_path):
        print(f"No existing file for this combination. Proceeding with fetch.")
        return True
    
    combo_mtime = os.path.getmtime(combo_path)
    if combo_mtime >= latest_log_mtime:
        print(f"Combination file is newer than latest log (combo: {combo_mtime}, log: {latest_log_mtime}). Skipping fetch.")
        return False
    else:
        print(f"Log files changed since last combo fetch. Log mtime: {latest_log_mtime}, Combo mtime: {combo_mtime}")
        return True


def main():
    if len(sys.argv) != 4:
        print("Usage: python fetch_and_merge.py <displayType> <controlType> <pbType>", file=sys.stderr)
        sys.exit(1)

    try:
        display_type = int(sys.argv[1])
        control_type = int(sys.argv[2])
        pb_type = int(sys.argv[3])
    except ValueError:
        print("All arguments must be integers.", file=sys.stderr)
        sys.exit(1)

    # Convert numbers to their string representations
    display_type_str = DISPLAY_TYPE_MAP.get(display_type, str(display_type))
    pb_type_str = PB_TYPE_MAP.get(pb_type, str(pb_type))
    control_type_str = CONTROL_TYPE_MAP.get(control_type, str(control_type))

    print(f"Fetching: display={display_type_str} ({display_type}), "
          f"control={control_type_str} ({control_type}), pb={pb_type_str} ({pb_type})")

    # Configure paths
    logs_dir = r"C:\coding\slidywebdata\logs"
    os.makedirs(MERGED_FOLDER, exist_ok=True)
    combo_filename = get_combo_filename(display_type, control_type, pb_type)
    combo_path = os.path.join(MERGED_FOLDER, combo_filename)
    
    # Check if we need to fetch scores for this combination
    if not should_fetch_combo(logs_dir, combo_path):
        print(f"Using existing file: {combo_path}")
        sys.exit(0)

    # 1. Fetch live scores
    try:
        live_text = fetch_live_scores(display_type, control_type, pb_type)
        live_scores = parse_scores_text(live_text, display_type_str, pb_type_str, is_archive=False)
        print(f"Live scores fetched: {len(live_scores)} entries.")
    except Exception as e:
        print(f"Failed to fetch live scores: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Fetch web archive scores
    try:
        archive_text = get_archive_scores(display_type, control_type, pb_type)
        web_scores = parse_scores_text(archive_text, display_type_str, pb_type_str, is_archive=True) if archive_text else []
        print(f"Web archive scores fetched: {len(web_scores)} entries.")
    except Exception as e:
        print(f"Warning: Could not load archive data ({e}). Proceeding without archive.", file=sys.stderr)
        web_scores = []

    # 3. Merge
    if web_scores:
        merged = merge_web_pbs(live_scores, web_scores)
        print(f"Merged total: {len(merged)} entries (live + web).")
    else:
        for s in live_scores:
            s['isWeb'] = False
        merged = live_scores

    # 4. Output to combination-specific file
    with open(combo_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False)
    print(f"Written merged leaderboard to {combo_path}")

if __name__ == "__main__":
    main()