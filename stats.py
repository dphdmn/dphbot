import subprocess
import sys
import json
import math
import re
from datetime import datetime
from power_data import *

# ============================================================
#  Shared helpers
# ============================================================

def _run_power(power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    display_id, display_name = _map_name(DISPLAY_TYPE_MAP, display_type)
    if display_id is None:
        raise ValueError(f"Unknown display_type: '{display_type}'. Available: {', '.join(DISPLAY_TYPE_MAP.values())}")
    control_id, control_name = _map_name(CONTROL_TYPE_MAP, control_type)
    if control_id is None:
        raise ValueError(f"Unknown control_type: '{control_type}'. Available: {', '.join(CONTROL_TYPE_MAP.values())}")
    pb_id = None
    pb_lower = pb_type.lower().strip()
    for id_, name in PB_TYPE_MAP.items():
        if name.lower().strip() == pb_lower:
            pb_id = id_
            break
    if pb_id is None:
        raise ValueError(f"Unknown pb_type: '{pb_type}'. Available: {', '.join(PB_TYPE_MAP.values())}")
    cmd = [sys.executable, "power.py", str(display_id), str(control_id), str(pb_id), power_system.lower().strip()]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    with open("power.txt", "r", encoding="utf-8") as f:
        power_data = json.load(f)
    with open("merged_leaderboard.txt", "r", encoding="utf-8") as f:
        merged_data = json.load(f)
    return power_data, merged_data, display_name, control_name

def _map_name(mapping, value):
    value_lower = value.lower().strip()
    for id_, name in mapping.items():
        if name.lower().strip() == value_lower:
            return id_, name
    for id_, name in mapping.items():
        if value_lower in name.lower().strip():
            return id_, name
    return None, None

def parse_puzzle_size(puzzle_str):
    parts = puzzle_str.lower().split('x')
    if len(parts) == 1:
        return int(parts[0]), int(parts[0])
    elif len(parts) != 2:
        raise ValueError("Puzzle size must be NxM, e.g. 4x4")
    return int(parts[0]), int(parts[1])

def format_score(ms, score_type="time"):
    if ms is None or ms == -1:
        return "-"
    if score_type == "move":
        val = ms / 1000.0
        if ms % 1000 == 0:
            return str(int(val))
        else:
            return f"{val:.3f}"
    else:
        total_sec = ms / 1000.0
        hours = int(total_sec // 3600)
        minutes = int((total_sec % 3600) // 60)
        seconds = total_sec % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:06.3f}"
        elif minutes > 0:
            return f"{minutes}:{seconds:06.3f}"
        else:
            return f"{seconds:.3f}"

def format_date(timestamp_ms):
    if timestamp_ms is None:
        return "Unknown"
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
    return dt.strftime("%d.%m.%Y")

def find_player_in_power(power_data, username_substring):
    for row in power_data:
        if username_substring.lower() in row[0].lower():
            return row
    return None

def find_tier_by_name(tiers, tier_substring):
    matches = []
    for t in tiers:
        if tier_substring.lower() in t['name'].lower():
            matches.append(t)
    return matches

def get_score_tier_for_category(time_val, tier_idx, tiers):
    if time_val == -1 or time_val is None:
        return tiers[0]
    for i in range(len(tiers)-1, -1, -1):
        if tier_idx < len(tiers[i]['times']) and time_val <= tiers[i]['times'][tier_idx]:
            return tiers[i]
    return tiers[0]

def get_category_id(width, height, gameMode, avglen):
    if gameMode == "Standard":
        if avglen == 1:
            return "single"
        else:
            return f"ao{avglen}"
    elif gameMode.startswith("Marathon"):
        num = gameMode.split(" ")[1]
        return f"x{num}"
    elif gameMode == "2-N relay":
        return "relay"
    elif gameMode == "Everything-up-to relay":
        return "eut"
    elif gameMode == "Width relay":
        return "wrel"
    elif gameMode == "Height relay":
        return "hrel"
    else:
        return gameMode  # BLD etc.

def get_all_categories_for_puzzle(N, M):
    cats = []
    for avglen in [1, 5, 12, 25, 50, 100]:
        cats.append((get_category_id(N, M, "Standard", avglen), "Standard", avglen))
    for mlen in [10, 25, 42, 50, 100]:
        cats.append((get_category_id(N, M, f"Marathon {mlen}", 1), f"Marathon {mlen}", 1))
    # Explicit relay types
    for mode in ["2-N relay", "Everything-up-to relay", "Width relay", "Height relay", "BLD"]:
        cats.append((get_category_id(N, M, mode, 1), mode, 1))
    return cats

def get_max_category_width():
    # include possible marathon IDs
    base = ["single", "ao5", "ao12", "ao25", "ao50", "ao100",
            "x10", "x25", "x42", "x50", "x100",
            "relay", "eut", "wrel", "hrel", "BLD"]
    return max(len(c) for c in base)

def _get_metric_functions(pb_type):
    if pb_type in ("time", "fmc", "fmc mtm"):
        def get_primary(s): return s['time']
        def is_better(a, b): return a < b
        def fmt_primary(v): return format_score(v, "time")
        def fmt_secondary(s):
            moves = format_score(s['moves'], "move") if s['moves'] and s['moves'] != -1 else "-"
            tps = f"{s['tps']/1000:.3f}" if s['tps'] and s['tps'] != -1 else "-"
            return f"({moves}/{tps})"
    elif pb_type == "move":
        def get_primary(s): return s['moves']
        def is_better(a, b): return a < b
        def fmt_primary(v): return format_score(v, "move")
        def fmt_secondary(s):
            time = format_score(s['time'], "time") if s['time'] and s['time'] != -1 else "-"
            tps = f"{s['tps']/1000:.3f}" if s['tps'] and s['tps'] != -1 else "-"
            return f"({time}/{tps})"
    elif pb_type == "tps":
        def get_primary(s): return s['tps']
        def is_better(a, b): return a > b
        def fmt_primary(v): return f"{v/1000:.3f}" if v and v != -1 else "-"
        def fmt_secondary(s):
            time = format_score(s['time'], "time") if s['time'] and s['time'] != -1 else "-"
            moves = format_score(s['moves'], "move") if s['moves'] and s['moves'] != -1 else "-"
            return f"({time}/{moves})"
    else:
        raise ValueError(f"Unknown pb_type: {pb_type}")
    return get_primary, is_better, fmt_primary, fmt_secondary

def _pad_columns(rows):
    if not rows:
        return []
    ncols = max(len(row) for row in rows)
    widths = [0] * ncols
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    out = []
    for row in rows:
        padded = [cell.ljust(widths[i]) for i, cell in enumerate(row)]
        out.append(" | ".join(padded))
    return out

# ============================================================
#  Marathon & relay type helper (for numwrs / lb30)
# ============================================================

def _resolve_relay_type(relay_str):
    """Convert a user‑supplied relay_type string to a canonical gameMode name.
       Returns (gameMode_name, is_marathon, marathon_number)"""
    raw = relay_str.lower().strip()
    # Marathon pattern: "marathon N" or "xN"
    m = re.match(r'^x(\d+)$', raw)
    if m:
        return f"Marathon {m.group(1)}", True, int(m.group(1))
    m = re.match(r'^marathon\s*(\d+)$', raw)
    if m:
        return f"Marathon {m.group(1)}", True, int(m.group(1))

    # Try exact match in SOLVE_TYPE_MAP
    for id_, name in SOLVE_TYPE_MAP.items():
        if name.lower().strip() == raw:
            return name, False, None
    # partial match
    for id_, name in SOLVE_TYPE_MAP.items():
        if raw in name.lower().strip():
            return name, False, None
    return None, False, None

# ============================================================
#  Command: getpb
# ============================================================

def get_pb(username_substring, puzzle_size,
           power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    if pb_type.lower() == "moves":
        pb_type = "move"
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ("move", "fmc", "fmc mtm"):
        pb_type = "move"
    power_data, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)
    player_row = find_player_in_power(power_data, username_substring)
    if not player_row:
        return f"No player matching '{username_substring}' found."
    player_name = player_row[0]
    get_primary, _, fmt_primary, fmt_secondary = _get_metric_functions(pb_type)

    best_scores = {}
    for s in merged_data:
        if player_name.lower() in s['nameFilter'].lower():
            key = (s['width'], s['height'], s['gameMode'], s['avglen'])
            if key not in best_scores:
                best_scores[key] = s
            else:
                cur = best_scores[key]
                if pb_type == "tps":
                    if s['tps'] > cur['tps']: best_scores[key] = s
                elif pb_type == "move":
                    if s['moves'] < cur['moves']: best_scores[key] = s
                else:
                    if s['time'] < cur['time']: best_scores[key] = s

    all_cats = get_all_categories_for_puzzle(N, M)

    puzzle_str = f"{N}x{M}"
    max_cat_w = get_max_category_width()
    max_puz_w = len(puzzle_str)
    rows = []  # (puzzle_str, cat_id, primary_str, secondary_str, date_str, tier_annotation)
    for cat_id, gameMode, avglen in all_cats:
        key = (N, M, gameMode, avglen)
        if key not in best_scores: continue
        score = best_scores[key]
        primary_val = get_primary(score)
        primary_str = fmt_primary(primary_val)
        secondary_str = fmt_secondary(score)
        date_str = format_date(score.get('timestamp'))
        tier_annotation = ""
        if (pb_type == "time" and power_system in ("classic", "modern")) or \
           (pb_type == "move" and power_system == "fmc"):
            for idx, cat in enumerate(categories):
                if cat['width'] == N and cat['height'] == M and cat['gameMode'] == gameMode and cat['avglen'] == avglen:
                    current_tier = get_score_tier_for_category(primary_val, idx, tiers)
                    if current_tier['name'] != 'Unranked':
                        tier_annotation = f"({current_tier['name']})"
                        tier_idx = tiers.index(current_tier)
                        if tier_idx < len(tiers) - 1:
                            next_tier = tiers[tier_idx + 1]
                            next_req = next_tier['times'][idx]
                            if pb_type == "time":
                                next_req_str = format_score(next_req, "time")
                            else:
                                next_req_str = str(int(next_req))
                            tier_annotation += f"({next_tier['name']}={next_req_str})"
                    break
        rows.append((puzzle_str, cat_id, primary_str, secondary_str, date_str, tier_annotation))

    if not rows:
        return f"No {pb_type} PBs found for {player_name} on {puzzle_size}."

    # Calculate max combined score block width for alignment
    score_blocks = [f"{prim} {sec}" for _, _, prim, sec, _, _ in rows]
    max_score_w = max(len(b) for b in score_blocks)

    lines = []
    for puz, cat, prim, sec, date, tier in rows:
        score_blk = f"{prim} {sec}"
        extra = f"{date} {tier}".strip()
        lines.append(f"{puz.ljust(max_puz_w)} {cat.ljust(max_cat_w)} | {score_blk.ljust(max_score_w)} | {extra}")

    header = f"{puzzle_str} {pb_type.upper()} PBs for {player_name}"
    info = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return header + "\n" + info + "\n" + "\n".join(lines)

# ============================================================
#  Command: getwr
# ============================================================

def get_wr(puzzle_size,
           power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    if pb_type.lower() == "moves":
        pb_type = "move"
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ("move", "fmc", "fmc mtm"):
        pb_type = "move"
    power_data, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)
    get_primary, is_better, fmt_primary, fmt_secondary = _get_metric_functions(pb_type)
    all_cats = get_all_categories_for_puzzle(N, M)

    puzzle_str = f"{N}x{M}"
    max_cat_w = get_max_category_width()
    max_puz_w = len(puzzle_str)
    rows = []
    for cat_id, gameMode, avglen in all_cats:
        relevant = [s for s in merged_data if s['width'] == N and s['height'] == M
                    and s['gameMode'] == gameMode and s['avglen'] == avglen]
        if not relevant: continue
        best_score = None
        best_val = None
        for s in relevant:
            val = get_primary(s)
            if val is None or val == -1: continue
            if best_val is None or is_better(val, best_val):
                best_val = val
                best_score = s
        if not best_score: continue
        primary_str = fmt_primary(best_val)
        secondary_str = fmt_secondary(best_score)
        holder = best_score.get('nameFilter', 'Unknown')
        date_str = format_date(best_score.get('timestamp'))
        tier_annotation = ""
        if (pb_type == "time" and power_system in ("classic", "modern")) or \
           (pb_type == "move" and power_system == "fmc"):
            for idx, cat in enumerate(categories):
                if cat['width'] == N and cat['height'] == M and cat['gameMode'] == gameMode and cat['avglen'] == avglen:
                    current_tier = get_score_tier_for_category(best_val, idx, tiers)
                    if current_tier['name'] != 'Unranked':
                        tier_annotation = f"({current_tier['name']})"
                        tier_idx = tiers.index(current_tier)
                        if tier_idx < len(tiers) - 1:
                            next_tier = tiers[tier_idx + 1]
                            next_req = next_tier['times'][idx]
                            if pb_type == "time":
                                next_req_str = format_score(next_req, "time")
                            else:
                                next_req_str = str(int(next_req))
                            tier_annotation += f"({next_tier['name']}={next_req_str})"
                    break
        rows.append((puzzle_str, cat_id, primary_str, secondary_str, holder, date_str, tier_annotation))

    if not rows:
        return f"No world records found for {puzzle_size} in {pb_type}."

    score_blocks = [f"{prim} {sec}" for _, _, prim, sec, _, _, _ in rows]
    max_score_w = max(len(b) for b in score_blocks)

    lines = []
    for puz, cat, prim, sec, holder, date, tier in rows:
        score_blk = f"{prim} {sec}"
        extra = f"by {holder}  {date} {tier}".strip()
        lines.append(f"{puz.ljust(max_puz_w)} {cat.ljust(max_cat_w)} | {score_blk.ljust(max_score_w)} | {extra}")

    header = f"{puzzle_str} {pb_type.upper()} World Records"
    info = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return header + "\n" + info + "\n" + "\n".join(lines)

# ============================================================
#  Command: numwrs
# ============================================================

def numwrs(display_type="Standard", control_type="unique", pb_type="time",
           filter_type="NxM singles", relay_type="Standard", power_system="modern"):
    if pb_type.lower() == "moves":
        pb_type = "move"
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ("move", "fmc", "fmc mtm"):
        pb_type = "move"
    power_data, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    get_primary, is_better, _, _ = _get_metric_functions(pb_type)

    # Resolve relay_type (with marathon support)
    game_mode_filter, is_marathon, mara_num = _resolve_relay_type(relay_type)
    if game_mode_filter is None:
        raise ValueError(f"Unknown relay_type: '{relay_type}'. Available: Standard, 2-N relay, "
                         f"Everything-up-to relay, Width relay, Height relay, BLD, Marathon N, xN")

    all_cats = {}
    for s in merged_data:
        key = (s['width'], s['height'], s['gameMode'], s['avglen'])
        all_cats.setdefault(key, []).append(s)
    # remove 2x2 if needed
    all_cats = {k: v for k, v in all_cats.items() if not (k[0] == 2 and k[1] == 2)}

    valid = {}
    for key, scores in all_cats.items():
        if any(get_primary(s) in (None, -1, 0) for s in scores):
            continue
        if pb_type == "move" and any(s.get('moves', 1000) == 1000 for s in scores):
            continue
        valid[key] = scores

    # Apply filter_type
    filter_lower = filter_type.lower().strip()
    if filter_lower == "nxm singles":
        valid = {k: v for k, v in valid.items() if k[3] == 1}
    elif filter_lower == "square averages":
        valid = {k: v for k, v in valid.items() if k[0] == k[1]}

    # Apply relay filter
    if is_marathon:
        # only categories with gameMode == "Marathon {num}"
        target_gm = f"Marathon {mara_num}"
        valid = {k: v for k, v in valid.items() if k[2] == target_gm}
    else:
        valid = {k: v for k, v in valid.items() if k[2] == game_mode_filter}

    # Best per category
    category_best = {}
    for key, scores in valid.items():
        best_s, best_v, best_ts = None, None, float('inf')
        for s in scores:
            v = get_primary(s)
            if v is None: continue
            ts = s.get('timestamp', float('inf'))
            if best_s is None or is_better(v, best_v) or (v == best_v and ts < best_ts):
                best_s, best_v, best_ts = s, v, ts
        if best_s:
            category_best[key] = (best_s, best_v, best_ts)

    player_wrs = {}
    for best_s, _, _ in category_best.values():
        name = best_s.get('nameFilter', 'Unknown')
        player_wrs[name] = player_wrs.get(name, 0) + 1
    sorted_players = sorted(player_wrs.items(), key=lambda x: (-x[1], x[0]))
    if not sorted_players:
        return "No world records found with the given filters."

    rows = [[str(rank), name, str(cnt)] for rank, (name, cnt) in enumerate(sorted_players, 1)]
    lines = _pad_columns(rows)
    total = sum(v for _, v in sorted_players)
    lines.append(f"Total: {total} WRs")
    info = f"[Display: {display_name} | Control: {control_name} | PB: {pb_type}]"
    filter_desc = f"[Filter: {filter_type}"
    if is_marathon:
        filter_desc += f" | Relay: Marathon {mara_num}"
    else:
        filter_desc += f" | Relay: {game_mode_filter}"
    filter_desc += "]"
    return "\n".join(lines) + "\n" + info + "\n" + filter_desc

# ============================================================
#  Command: rank
# ============================================================

def get_rank(username_substring, power_system="modern",
             display_type="Standard", control_type="unique", pb_type="time"):
    if pb_type.lower() in ("tps", "fmc", "fmc mtm"):
        pb_type = "move"
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type != "move":
        pb_type = "move"
    power_data, _, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    player_row = find_player_in_power(power_data, username_substring)
    if not player_row:
        return f"No player matching '{username_substring}' found."
    player_name = player_row[0]
    rank = player_row[1]
    total_power = player_row[2]
    times = player_row[3:]
    score_tiers_indices = []
    for i, t in enumerate(times):
        if i >= len(categories): break
        if t == -1 or t is None:
            score_tiers_indices.append(0)
        else:
            tier = get_score_tier_for_category(t, i, tiers)
            score_tiers_indices.append(tiers.index(tier))
    true_tier_idx = min(score_tiers_indices) if score_tiers_indices else 0
    true_tier_name = tiers[true_tier_idx]['name']
    final_tier_idx = 0
    for i in range(len(tiers)-1, -1, -1):
        if total_power >= tiers[i]['limit'] and any(idx >= i for idx in score_tiers_indices):
            final_tier_idx = i
            break
    final_tier_name = tiers[final_tier_idx]['name']
    next_rank_info = ""
    if final_tier_idx < len(tiers) - 1:
        next_tier = tiers[final_tier_idx + 1]
        power_needed = next_tier['limit']
        if total_power >= power_needed:
            next_rank_info = f" ({next_tier['name']} = At least 1 {next_tier['name']} score)"
        else:
            next_rank_info = f" ({next_tier['name']} = {power_needed})"
    info = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return (f"({power_system.capitalize()} Power): {player_name} is in position {rank} "
            f"with {total_power} power ({final_tier_name}, True {true_tier_name}){next_rank_info}\n{info}")

# ============================================================
#  Command: getreq
# ============================================================

def get_req(tier_substring, power_system, puzzle_size):
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)
    matched_tiers = find_tier_by_name(tiers, tier_substring)
    if not matched_tiers:
        return f"No tier matching '{tier_substring}' found."
    puzzle_str = f"{N}x{M}"
    max_cat_w = get_max_category_width()
    max_puz_w = len(puzzle_str)
    rows = []
    for idx, cat in enumerate(categories):
        if cat['width'] != N or cat['height'] != M: continue
        cat_id = cat['id'].split(' ', 1)[1] if ' ' in cat['id'] else cat['id']
        reqs = []
        for t in matched_tiers:
            req_val = t['times'][idx]
            if power_system == "fmc":
                reqs.append(str(int(req_val)))
            else:
                reqs.append(format_score(req_val, "time"))
        rows.append((puzzle_str, cat_id, '  '.join(reqs)))
    if not rows:
        return f"No categories for {puzzle_size} in {power_system}."
    lines = [f"{puz.ljust(max_puz_w)} {cat.ljust(max_cat_w)} | {req}" for puz, cat, req in rows]
    tier_names = " | ".join(t['name'] for t in matched_tiers)
    header = f"Requirements for {tier_names} {puzzle_str}"
    return header + "\n" + "\n".join(lines)

# ============================================================
#  NEW: top25 with Rank, Player, Power, Tier, True Tier
# ============================================================

def top25(power_system="modern", display_type="Standard", control_type="unique"):
    if power_system == "fmc":
        pb_type = "move"
    else:
        pb_type = "time"
    power_data, _, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    def get_player_tiers(row):
        name, rank, total_power = row[0], row[1], row[2]
        times = row[3:]
        score_tiers_indices = []
        for i, t in enumerate(times):
            if i >= len(categories): break
            if t == -1 or t is None:
                score_tiers_indices.append(0)
            else:
                tier = get_score_tier_for_category(t, i, tiers)
                score_tiers_indices.append(tiers.index(tier))
        true_tier_idx = min(score_tiers_indices) if score_tiers_indices else 0
        true_tier = "True " + tiers[true_tier_idx]['name']
        final_tier_idx = 0
        for i in range(len(tiers)-1, -1, -1):
            if total_power >= tiers[i]['limit'] and any(idx >= i for idx in score_tiers_indices):
                final_tier_idx = i
                break
        final_tier = tiers[final_tier_idx]['name']
        return final_tier, true_tier

    top = power_data[:25]
    if not top:
        return "No players found."
    rows = []
    for player in top:
        rank = player[1]
        name = player[0]
        total_power = player[2]
        tier, true_tier = get_player_tiers(player)
        rows.append([str(rank), name, str(total_power), tier, true_tier])
    lines = _pad_columns(rows)
    info = f"[Power: {power_system.capitalize()} | Display: {display_name} | Control: {control_name}]"
    return "\n".join(lines) + "\n" + info

# ============================================================
#  REWORKED bestscores / worstscores
# ============================================================

def _player_scores(username, power_system, display_type, control_type, best=True):
    if power_system == "fmc":
        pb_type = "move"
    else:
        pb_type = "time"
    _, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    get_primary, is_better, fmt_primary, fmt_secondary = _get_metric_functions(pb_type)

    user_scores = {}
    for s in merged_data:
        if username.lower() not in s['nameFilter'].lower():
            continue
        key = (s['width'], s['height'], s['gameMode'], s['avglen'])
        if key not in user_scores:
            user_scores[key] = s
        else:
            cur = user_scores[key]
            cur_val = get_primary(cur)
            new_val = get_primary(s)
            if best:
                if new_val is not None and (cur_val is None or is_better(new_val, cur_val)):
                    user_scores[key] = s
            else:
                if pb_type == "tps":
                    if new_val is not None and (cur_val is None or new_val < cur_val):
                        user_scores[key] = s
                else:
                    if new_val is not None and (cur_val is None or new_val > cur_val):
                        user_scores[key] = s

    if not user_scores:
        return f"No scores found for {username}."

    tier_order_map = {t['name']: i for i, t in enumerate(tiers)}
    entries = []
    for (W, H, gameMode, avglen), score in user_scores.items():
        idx = None
        for i, cat in enumerate(categories):
            if cat['width'] == W and cat['height'] == H and cat['gameMode'] == gameMode and cat['avglen'] == avglen:
                idx = i
                break
        if idx is None:
            continue
        val = get_primary(score)
        if val is None or val == -1:
            continue
        achieved_tier = None
        for t in reversed(tiers):
            if idx < len(t['times']) and val <= t['times'][idx]:
                achieved_tier = t
                break
        if achieved_tier is None:
            achieved_tier = tiers[0]
        limit = achieved_tier['times'][idx]
        if limit == 0:
            continue
        ahead = (limit - val) / limit * 100
        entries.append((tier_order_map[achieved_tier['name']], ahead, W, H, gameMode, avglen, val, score, achieved_tier['name']))

    entries.sort(key=lambda e: (-e[0], -e[1] if best else e[1]))

    output_lines = []
    current_tier_name = None
    tier_lines = []
    for tier_ord, ahead, W, H, gameMode, avglen, val, score, tier_name in entries:
        if tier_name != current_tier_name:
            if tier_lines:
                output_lines.extend(_pad_columns(tier_lines))
                tier_lines = []
            current_tier_name = tier_name
            output_lines.append(f"\n=== {tier_name} ===")
        cat_id = get_category_id(W, H, gameMode, avglen)
        primary_str = fmt_primary(val)
        secondary_str = fmt_secondary(score)
        score_disp = f"{primary_str} {secondary_str}"
        puzzle_str = f"{W}x{H}"
        ahead_str = f"{ahead:+.2f}%"
        tier_lines.append([puzzle_str, cat_id, score_disp, ahead_str])
    if tier_lines:
        output_lines.extend(_pad_columns(tier_lines))

    if not any("===" in l for l in output_lines):
        return f"No ranked scores for {username} in {power_system}."
    info = f"\n[Power: {power_system.capitalize()} | Display: {display_type} | Control: {control_type}]"
    return "\n".join(output_lines) + info

def bestscores(username, power_system="modern", display_type="Standard", control_type="unique"):
    return _player_scores(username, power_system, display_type, control_type, best=True)

def worstscores(username, power_system="modern", display_type="Standard", control_type="unique"):
    return _player_scores(username, power_system, display_type, control_type, best=False)

# ============================================================
#  lb30
# ============================================================

def lb30(puzzle_size="4x4", relay_type="Standard", avglen="single",
         display_type="Standard", control_type="unique", pb_type="time"):
    avglen_str = avglen.lower().strip()
    if avglen_str == "single":
        avglen_num = 1
    elif avglen_str.startswith("ao"):
        avglen_num = int(avglen_str[2:])
    else:
        raise ValueError("avglen must be 'single' or 'aoNN'")

    # Resolve relay type (with marathon support)
    game_mode, is_marathon, mara_num = _resolve_relay_type(relay_type)
    if game_mode is None:
        raise ValueError(f"Unknown relay_type: '{relay_type}'. Available: Standard, 2-N relay, "
                         "Everything-up-to relay, Width relay, Height relay, BLD, Marathon N, xN")

    N, M = parse_puzzle_size(puzzle_size)
    _, merged_data, display_name, control_name = _run_power("modern", display_type, control_type, pb_type)
    get_primary, is_better, fmt_primary, fmt_secondary = _get_metric_functions(pb_type)

    entries = [s for s in merged_data
               if s['width'] == N and s['height'] == M
               and s['gameMode'] == game_mode and s['avglen'] == avglen_num
               and get_primary(s) not in (None, -1, 0)]
    if not entries:
        return f"No scores found for {puzzle_size} {game_mode} {avglen_str}."
    reverse_sort = (pb_type == "tps")
    entries.sort(key=lambda s: get_primary(s), reverse=reverse_sort)
    top = entries[:30]
    if not top:
        return "No valid scores."
    best_val = get_primary(top[0])
    if best_val == 0:
        return "Best score is 0, cannot compute percentages."
    rows = []
    for rank, s in enumerate(top, 1):
        player = s.get('nameFilter', 'Unknown')
        val = get_primary(s)
        primary_str = fmt_primary(val)
        secondary_str = fmt_secondary(s)
        score_disp = f"{primary_str} {secondary_str}"
        if pb_type == "tps":
            perc = (val / best_val) * 100
        else:
            perc = (best_val / val) * 100
        perc_str = f"{perc:.3f}%"
        rows.append([str(rank), player, score_disp, perc_str])
    lines = _pad_columns(rows)
    info = f"[{puzzle_size} | {game_mode} | {avglen_str} | Display: {display_name} | Control: {control_name} | PB: {pb_type}]"
    return "\n".join(lines) + "\n" + info

# ============================================================
#  CLI (unchanged, keeping all entry points)
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "getpb":
        if len(sys.argv) < 4:
            print("Usage: python stats.py getpb <username> <puzzleSize> [powerSystem=modern] [displayType=Standard] [controlType=unique] [pbType=time]")
            sys.exit(1)
        username = sys.argv[2]
        puzzle = sys.argv[3]
        power = sys.argv[4] if len(sys.argv) > 4 else "modern"
        display = sys.argv[5] if len(sys.argv) > 5 else "Standard"
        control = sys.argv[6] if len(sys.argv) > 6 else "unique"
        pb = sys.argv[7] if len(sys.argv) > 7 else "time"
        print(get_pb(username, puzzle, power, display, control, pb))

    elif cmd == "getwr":
        if len(sys.argv) < 3:
            print("Usage: python stats.py getwr <puzzleSize> [powerSystem=modern] [displayType=Standard] [controlType=unique] [pbType=time]")
            sys.exit(1)
        puzzle = sys.argv[2]
        power = sys.argv[3] if len(sys.argv) > 3 else "modern"
        display = sys.argv[4] if len(sys.argv) > 4 else "Standard"
        control = sys.argv[5] if len(sys.argv) > 5 else "unique"
        pb = sys.argv[6] if len(sys.argv) > 6 else "time"
        print(get_wr(puzzle, power, display, control, pb))

    elif cmd == "numwrs":
        if len(sys.argv) < 2:
            print("Usage: python stats.py numwrs [displayType=Standard] [controlType=unique] [pbType=time] [filterType=NxM singles] [relayType=Standard] [powerSystem=modern]")
            sys.exit(1)
        display = sys.argv[2] if len(sys.argv) > 2 else "Standard"
        control = sys.argv[3] if len(sys.argv) > 3 else "unique"
        pb = sys.argv[4] if len(sys.argv) > 4 else "time"
        filter_type = sys.argv[5] if len(sys.argv) > 5 else "NxM singles"
        relay = sys.argv[6] if len(sys.argv) > 6 else "Standard"
        power = sys.argv[7] if len(sys.argv) > 7 else "modern"
        print(numwrs(display, control, pb, filter_type, relay, power))

    elif cmd == "rank":
        if len(sys.argv) < 3:
            print("Usage: python stats.py rank <username> [powerSystem=modern] [displayType=Standard] [controlType=unique] [pbType=time]")
            sys.exit(1)
        username = sys.argv[2]
        power = sys.argv[3] if len(sys.argv) > 3 else "modern"
        display = sys.argv[4] if len(sys.argv) > 4 else "Standard"
        control = sys.argv[5] if len(sys.argv) > 5 else "unique"
        pb = sys.argv[6] if len(sys.argv) > 6 else "time"
        print(get_rank(username, power, display, control, pb))

    elif cmd == "getreq":
        if len(sys.argv) < 5:
            print("Usage: python stats.py getreq <tiername> <powerSystem> <puzzleSize>")
            sys.exit(1)
        tiername = sys.argv[2]
        power = sys.argv[3]
        puzzle = sys.argv[4]
        print(get_req(tiername, power, puzzle))

    elif cmd == "top25":
        if len(sys.argv) < 2:
            print("Usage: python stats.py top25 [powerSystem=modern] [displayType=Standard] [controlType=unique]")
            sys.exit(1)
        power = sys.argv[2] if len(sys.argv) > 2 else "modern"
        display = sys.argv[3] if len(sys.argv) > 3 else "Standard"
        control = sys.argv[4] if len(sys.argv) > 4 else "unique"
        print(top25(power, display, control))

    elif cmd == "bestscores":
        if len(sys.argv) < 3:
            print("Usage: python stats.py bestscores <username> [powerSystem=modern] [displayType=Standard] [controlType=unique]")
            sys.exit(1)
        username = sys.argv[2]
        power = sys.argv[3] if len(sys.argv) > 3 else "modern"
        display = sys.argv[4] if len(sys.argv) > 4 else "Standard"
        control = sys.argv[5] if len(sys.argv) > 5 else "unique"
        print(bestscores(username, power, display, control))

    elif cmd == "worstscores":
        if len(sys.argv) < 3:
            print("Usage: python stats.py worstscores <username> [powerSystem=modern] [displayType=Standard] [controlType=unique]")
            sys.exit(1)
        username = sys.argv[2]
        power = sys.argv[3] if len(sys.argv) > 3 else "modern"
        display = sys.argv[4] if len(sys.argv) > 4 else "Standard"
        control = sys.argv[5] if len(sys.argv) > 5 else "unique"
        print(worstscores(username, power, display, control))

    elif cmd == "lb30":
        if len(sys.argv) < 2:
            print("Usage: python stats.py lb30 [puzzleSize=4x4] [relayType=Standard] [avglen=single] [displayType=Standard] [controlType=unique] [pbType=time]")
            sys.exit(1)
        puzzle = sys.argv[2] if len(sys.argv) > 2 else "4x4"
        relay = sys.argv[3] if len(sys.argv) > 3 else "Standard"
        avglen = sys.argv[4] if len(sys.argv) > 4 else "single"
        display = sys.argv[5] if len(sys.argv) > 5 else "Standard"
        control = sys.argv[6] if len(sys.argv) > 6 else "unique"
        pb = sys.argv[7] if len(sys.argv) > 7 else "time"
        print(lb30(puzzle, relay, avglen, display, control, pb))

    else:
        print("Unknown command. Use getpb, getwr, numwrs, rank, getreq, top25, bestscores, worstscores, or lb30.")