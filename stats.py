import subprocess
import sys
import json
import math
from datetime import datetime
from power_data import *

# ====================== HELPER: Run power.py ======================
def _run_power(power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    """Run power.py to generate both power.txt and merged_leaderboard.txt.
    Returns (power_data, merged_data, display_name, control_name)."""
    
    # Convert display_type - try exact match first, then substring
    display_id = None
    display_name = None
    display_name_lower = display_type.lower().strip()
    
    # First try exact match
    for id_, name in DISPLAY_TYPE_MAP.items():
        if name.lower().strip() == display_name_lower:
            display_id = id_
            display_name = name
            break
    
    # If no exact match, try substring
    if display_id is None:
        for id_, name in DISPLAY_TYPE_MAP.items():
            if display_name_lower in name.lower().strip():
                display_id = id_
                display_name = name
                break
    
    if display_id is None:
        available = ", ".join(DISPLAY_TYPE_MAP.values())
        raise ValueError(f"Unknown display_type: '{display_type}'. Available: {available}")
    
    # Convert control_type - try exact match first, then substring
    control_id = None
    control_name = None
    control_name_lower = control_type.lower().strip()
    
    # First try exact match
    for id_, name in CONTROL_TYPE_MAP.items():
        if name.lower().strip() == control_name_lower:
            control_id = id_
            control_name = name
            break
    
    # If no exact match, try substring
    if control_id is None:
        for id_, name in CONTROL_TYPE_MAP.items():
            if control_name_lower in name.lower().strip():
                control_id = id_
                control_name = name
                break
    
    if control_id is None:
        available = ", ".join(CONTROL_TYPE_MAP.values())
        raise ValueError(f"Unknown control_type: '{control_type}'. Available: {available}")
    
    # Convert pb_type - case insensitive exact match
    pb_id = None
    pb_type_lower = pb_type.lower().strip()
    for id_, name in PB_TYPE_MAP.items():
        if name.lower().strip() == pb_type_lower:
            pb_id = id_
            break
    if pb_id is None:
        available = ", ".join(PB_TYPE_MAP.values())
        raise ValueError(f"Unknown pb_type: '{pb_type}'. Available: {available}")
    
    # CORRECT ORDER: display, control, pb, power_system
    cmd = [sys.executable, "power.py", str(display_id), str(control_id), str(pb_id), power_system.lower().strip()]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    with open("power.txt", "r", encoding="utf-8") as f:
        power_data = json.load(f)
    with open("merged_leaderboard.txt", "r", encoding="utf-8") as f:
        merged_data = json.load(f)
    
    return power_data, merged_data, display_name, control_name

# ====================== HELPER FUNCTIONS ======================
def parse_puzzle_size(puzzle_str):
    parts = puzzle_str.lower().split('x')
    if len(parts) == 1:
        return int(parts[0]), int(parts[0])
    elif len(parts) != 2:
        raise ValueError("Puzzle size must be NxM, egg, 4x4")
    return int(parts[0]), int(parts[1])

def format_score(ms, score_type="time"):
    """Format a stored value for display.
    Moves are stored as *1000 in data, so we divide by 1000.
    - 'time': shows with optional hh:mm:ss and ms to 3 decimal places
    - 'move': shows as integer if fractional part is zero, else with 3 decimals
    """
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
    """Convert millisecond timestamp to DD.MM.YYYY format."""
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

def get_best_scores_for_user(merged_data, username):
    user_scores = [s for s in merged_data if username.lower() in s['nameFilter'].lower()]
    best = {}
    for s in user_scores:
        key = (s['width'], s['height'], s['gameMode'], s['avglen'])
        if key not in best:
            best[key] = s
        else:
            cur = best[key]
            if s['leaderboardType'] == 'tps' and s['tps'] > cur['tps']:
                best[key] = s
            elif s['leaderboardType'] == 'move' and s['moves'] < cur['moves']:
                best[key] = s
            elif s['leaderboardType'] in ('time', 'FMC', 'FMC MTM') and s['time'] < cur['time']:
                best[key] = s
    return best

def get_category_id(width, height, gameMode, avglen):
    """Get category ID string (without puzzle prefix for alignment)."""
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
    else:
        return gameMode

def get_all_categories_for_puzzle(N, M):
    categories = []
    for avglen in [1, 5, 12, 25, 50, 100]:
        categories.append((get_category_id(N, M, "Standard", avglen), "Standard", avglen))
    for mlen in [10, 25, 42, 50, 100]:
        categories.append((get_category_id(N, M, f"Marathon {mlen}", 1), f"Marathon {mlen}", 1))
    categories.append((get_category_id(N, M, "2-N relay", 1), "2-N relay", 1))
    categories.append((get_category_id(N, M, "Everything-up-to relay", 1), "Everything-up-to relay", 1))
    return categories

def get_max_category_width():
    """Get the maximum width needed for category alignment."""
    cats = ["single", "ao5", "ao12", "ao25", "ao50", "ao100", 
            "x10", "x25", "x42", "x50", "x100", "relay", "eut"]
    return max(len(c) for c in cats)+1

def format_aligned_line(puzzle_str, cat_id, value_str, holder_name="", date_str="", tier_annotation=""):
    """Format a line with proper alignment between puzzle size and category."""
    max_puzzle_width = len(puzzle_str)
    max_cat_width = get_max_category_width()
    
    puzzle_padded = puzzle_str.ljust(max_puzzle_width)
    cat_padded = cat_id.ljust(max_cat_width)
    
    line = f"{puzzle_padded} {cat_padded}: {value_str}"
    
    if holder_name:
        line += f" by {holder_name}"
    
    if date_str and date_str != "Unknown":
        line += f" [{date_str}]"
    
    if tier_annotation:
        line += tier_annotation
    
    return line

# ====================== FUNCTION: getPB ======================
def get_pb(username_substring, puzzle_size, power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    # Replace "moves" with "move"
    if pb_type.lower() == "moves":
        pb_type = "move"
    
    # Force move <-> fmc relationship
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ["move", "fmc", "fmc mtm"]:
        pb_type = "move"
    
    power_data, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)
    
    player_row = find_player_in_power(power_data, username_substring)
    if not player_row:
        return f"No player matching '{username_substring}' found."
    player_name = player_row[0]
    
    best_scores = get_best_scores_for_user(merged_data, player_name)
    all_cats = get_all_categories_for_puzzle(N, M)
    
    # Determine primary value, secondary format based on pb_type
    if pb_type == "time" or pb_type == "fmc" or pb_type == "fmc mtm":
        def get_primary(score):
            return score['time']
        def format_primary(val):
            return format_score(val, "time")
        def format_secondary(score):
            moves = format_score(score['moves'], "move") if score['moves'] and score['moves'] != -1 else "-"
            tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            return f"({moves}/{tps})"
    elif pb_type == "move":
        def get_primary(score):
            return score['moves']
        def format_primary(val):
            return format_score(val, "move")
        def format_secondary(score):
            time = format_score(score['time'], "time") if score['time'] and score['time'] != -1 else "-"
            tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            return f"({time}/{tps})"
    elif pb_type == "tps":
        def get_primary(score):
            return score['tps']
        def format_primary(val):
            return f"{val/1000:.3f}" if val and val != -1 else "-"
        def format_secondary(score):
            time = format_score(score['time'], "time") if score['time'] and score['time'] != -1 else "-"
            moves = format_score(score['moves'], "move") if score['moves'] and score['moves'] != -1 else "-"
            return f"({time}/{moves})"
    else:
        def get_primary(score):
            return score['time']
        def format_primary(val):
            return format_score(val, "time")
        def format_secondary(score):
            return ""
    
    puzzle_str = f"{N}x{M}"
    lines = []
    
    for cat_id, gameMode, avglen in all_cats:
        key = (N, M, gameMode, avglen)
        if key not in best_scores:
            continue
        
        score = best_scores[key]
        primary_val = get_primary(score)
        primary_str = format_primary(primary_val)
        secondary_str = format_secondary(score)
        value_str = f"{primary_str} {secondary_str}".strip()
        
        # Get date
        date_str = format_date(score.get('timestamp'))
        
        # Add tier annotation for time pb_type on classic/modern systems
        # OR for move pb_type on fmc system
        tier_annotation = ""
        if (pb_type == "time" and power_system in ["classic", "modern"]) or \
           (pb_type == "move" and power_system == "fmc"):
            for idx, cat in enumerate(categories):
                if cat['width'] == N and cat['height'] == M and cat['gameMode'] == gameMode and cat['avglen'] == avglen:
                    current_tier = get_score_tier_for_category(primary_val, idx, tiers)
                    if current_tier['name'] != 'Unranked':
                        tier_annotation = f" ({current_tier['name']})"
                        tier_idx = tiers.index(current_tier)
                        if tier_idx < len(tiers) - 1:
                            next_tier = tiers[tier_idx + 1]
                            next_req = next_tier['times'][idx]
                            if pb_type == "time":
                                next_req_str = format_score(next_req, "time")
                            else:  # move for fmc - tier requirements are raw move counts
                                next_req_str = str(int(next_req))
                            tier_annotation += f"({next_tier['name']}={next_req_str})"
                    break
        
        line = format_aligned_line(puzzle_str, cat_id, value_str, date_str=date_str, tier_annotation=tier_annotation)
        lines.append(line)
    
    if not lines:
        return f"No {pb_type} PBs found for {player_name} on {puzzle_size}."
    
    header = f"{puzzle_str} {pb_type.upper()} PBs for {player_name}"
    info_line = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return header + "\n" + info_line + "\n" + "\n".join(lines)


# ====================== FUNCTION: getWR ======================
def get_wr(puzzle_size, power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    """Get world records (best among all users) for the given puzzle size and settings."""
    # Normalize pb_type as in get_pb
    if pb_type.lower() == "moves":
        pb_type = "move"
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ["move", "fmc", "fmc mtm"]:
        pb_type = "move"

    power_data, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)

    # The same category list as in get_pb
    all_cats = get_all_categories_for_puzzle(N, M)

    # Same format helpers
    if pb_type == "time" or pb_type == "fmc" or pb_type == "fmc mtm":
        def get_primary(score):
            return score['time']
        def is_better(new_val, old_val):
            return new_val < old_val
        def format_primary(val):
            return format_score(val, "time")
        def format_secondary(score):
            moves = format_score(score['moves'], "move") if score['moves'] and score['moves'] != -1 else "-"
            tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            return f"({moves}/{tps})"
    elif pb_type == "move":
        def get_primary(score):
            return score['moves']
        def is_better(new_val, old_val):
            return new_val < old_val
        def format_primary(val):
            return format_score(val, "move")
        def format_secondary(score):
            time = format_score(score['time'], "time") if score['time'] and score['time'] != -1 else "-"
            tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            return f"({time}/{tps})"
    elif pb_type == "tps":
        def get_primary(score):
            return score['tps']
        def is_better(new_val, old_val):
            return new_val > old_val   # higher is better for TPS
        def format_primary(val):
            return f"{val/1000:.3f}" if val and val != -1 else "-"
        def format_secondary(score):
            time = format_score(score['time'], "time") if score['time'] and score['time'] != -1 else "-"
            moves = format_score(score['moves'], "move") if score['moves'] and score['moves'] != -1 else "-"
            return f"({time}/{moves})"
    else:
        def get_primary(score):
            return score['time']
        def is_better(new_val, old_val):
            return new_val < old_val
        def format_primary(val):
            return format_score(val, "time")
        def format_secondary(score):
            return ""

    puzzle_str = f"{N}x{M}"
    lines = []
    
    for cat_id, gameMode, avglen in all_cats:
        # Filter all scores for this category
        relevant = [s for s in merged_data if s['width'] == N and s['height'] == M and s['gameMode'] == gameMode and s['avglen'] == avglen]
        if not relevant:
            continue

        # Find the best one
        best_score = None
        best_val = None
        for score in relevant:
            val = get_primary(score)
            if val is None or val == -1:
                continue
            if best_val is None or is_better(val, best_val):
                best_val = val
                best_score = score

        if not best_score:
            continue

        primary_str = format_primary(best_val)
        secondary_str = format_secondary(best_score)
        value_str = f"{primary_str} {secondary_str}".strip()

        # Add holder's name and date
        holder_name = best_score.get('nameFilter', 'Unknown')
        date_str = format_date(best_score.get('timestamp'))
        
        # Tier annotation (same logic as get_pb)
        tier_annotation = ""
        if (pb_type == "time" and power_system in ["classic", "modern"]) or \
           (pb_type == "move" and power_system == "fmc"):
            for idx, cat in enumerate(categories):
                if cat['width'] == N and cat['height'] == M and cat['gameMode'] == gameMode and cat['avglen'] == avglen:
                    current_tier = get_score_tier_for_category(best_val, idx, tiers)
                    if current_tier['name'] != 'Unranked':
                        tier_annotation = f" ({current_tier['name']})"
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

        line = format_aligned_line(puzzle_str, cat_id, value_str, holder_name, date_str, tier_annotation)
        lines.append(line)

    if not lines:
        return f"No world records found for {puzzle_size} in {pb_type}."

    header = f"{puzzle_str} {pb_type.upper()} World Records"
    info_line = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return header + "\n" + info_line + "\n" + "\n".join(lines)


# ====================== FUNCTION: numwrs ======================
def numwrs(display_type="Standard", control_type="unique", pb_type="time", 
           filter_type="NxM singles", relay_type="Standard", power_system="modern"):
    """
    Count world records per player.
    
    Args:
        display_type, control_type, pb_type: Standard filters
        filter_type: "NxM singles" (default) - only singles (avglen==1), any NxM
                     "Square averages" - only NxN puzzles, any avglen
        relay_type: Filter by gameMode (default "Standard" from SOLVE_TYPE_MAP)
        power_system: Power system to use
    """
    # Normalize pb_type
    if pb_type.lower() == "moves":
        pb_type = "move"
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ["move", "fmc", "fmc mtm"]:
        pb_type = "move"
    
    power_data, merged_data, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    
    # Convert relay_type to gameMode string
    game_mode_filter = None
    if relay_type is not None:
        relay_lower = str(relay_type).lower().strip()
        # Try exact match first
        for id_, name in SOLVE_TYPE_MAP.items():
            if name.lower().strip() == relay_lower:
                game_mode_filter = name
                break
        # Try substring match
        if game_mode_filter is None:
            for id_, name in SOLVE_TYPE_MAP.items():
                if relay_lower in name.lower().strip():
                    game_mode_filter = name
                    break
    
    # Define comparison functions based on pb_type
    if pb_type == "time" or pb_type == "fmc" or pb_type == "fmc mtm":
        def get_primary(score):
            return score['time']
        def is_better(new_val, old_val):
            return new_val < old_val
        def is_invalid_score(val):
            return val == 0 or val == -1 or val is None
    elif pb_type == "move":
        def get_primary(score):
            return score['moves']
        def is_better(new_val, old_val):
            return new_val < old_val
        def is_invalid_score(val):
            return val == 1000 or val == 0 or val == -1 or val is None
    elif pb_type == "tps":
        def get_primary(score):
            return score['tps']
        def is_better(new_val, old_val):
            return new_val > old_val
        def is_invalid_score(val):
            return val == 0 or val == -1 or val is None
    
    # First, group ALL scores by category
    all_categories = {}
    for score in merged_data:
        key = (score['width'], score['height'], score['gameMode'], score['avglen'])
        if key not in all_categories:
            all_categories[key] = []
        all_categories[key].append(score)
    
    # Filter out 2x2 puzzles completely
    all_categories = {k: v for k, v in all_categories.items() if not (k[0] == 2 and k[1] == 2)}
    
    # Filter out categories that have ANY 0.000s or 1 move record
    valid_categories = {}
    for key, scores in all_categories.items():
        has_invalid = False
        for score in scores:
            val = get_primary(score)
            if is_invalid_score(val):
                has_invalid = True
                break
        
        if not has_invalid:
            valid_categories[key] = scores
    
    # Apply filter_type
    filter_type_lower = filter_type.lower().strip()
    if filter_type_lower == "nxm singles":
        # Only singles (avglen==1), any puzzle size
        valid_categories = {k: v for k, v in valid_categories.items() if k[3] == 1}
    elif filter_type_lower == "square averages":
        # Only NxN puzzles (width == height), any avglen
        valid_categories = {k: v for k, v in valid_categories.items() if k[0] == k[1]}
    
    # Apply relay_type filter
    if game_mode_filter:
        valid_categories = {k: v for k, v in valid_categories.items() if k[2] == game_mode_filter}
    
    # Now find the best score per category (earliest timestamp wins ties)
    category_best = {}
    for key, scores in valid_categories.items():
        best_score = None
        best_val = None
        best_ts = float('inf')
        
        for score in scores:
            val = get_primary(score)
            if val is None or val == -1:
                continue
            
            timestamp = score.get('timestamp', float('inf'))
            
            if best_score is None:
                best_score = score
                best_val = val
                best_ts = timestamp
            elif is_better(val, best_val):
                best_score = score
                best_val = val
                best_ts = timestamp
            elif val == best_val and timestamp < best_ts:
                # Tied value, earlier timestamp wins
                best_score = score
                best_val = val
                best_ts = timestamp
        
        if best_score is not None:
            category_best[key] = (best_score, best_val, best_ts)
    
    # Count WRs per player
    player_wrs = {}
    for key, (score, val, timestamp) in category_best.items():
        player_name = score.get('nameFilter', 'Unknown')
        player_wrs[player_name] = player_wrs.get(player_name, 0) + 1
    
    # Sort by count (descending), then alphabetically
    sorted_players = sorted(player_wrs.items(), key=lambda x: (-x[1], x[0]))
    
       # Format output
    lines = []
    max_name_len = max(len(name) for name, _ in sorted_players) if sorted_players else 15
    max_name_len = max(max_name_len, 8)
    
    for player_name, wr_count in sorted_players:
        padded_name = player_name.ljust(max_name_len + 2)
        lines.append(f"{padded_name}: {wr_count}")
    
    # Add total count
    total_wrs = sum(count for _, count in sorted_players)
    lines.append("─" * (max_name_len + 10))
    lines.append(f"{'Total'.ljust(max_name_len + 2)}: {total_wrs}")
    
    if not lines:
        return f"No world records found for the given filters.\n[Display: {display_name} | Control: {control_name} | PB: {pb_type} | Power: {power_system.capitalize()}]\n[Filter: {filter_type} | Relay: {relay_type}]"
    
    filter_desc = f"Filter: {filter_type}"
    if game_mode_filter:
        filter_desc += f" | Relay: {game_mode_filter}"
    
    header = f"World Record Counts"
    info_line = f"[Display: {display_name} | Control: {control_name} | PB: {pb_type}]"
    filter_line = f"[{filter_desc}]"
    
    return header + "\n" + "\n".join(lines) + "\n" + info_line + "\n" + filter_line


# ====================== FUNCTION: rank ======================
def get_rank(username_substring, power_system="modern", display_type="Standard", control_type="unique", pb_type="time"):
    if pb_type.lower() == "tps":
        pb_type = "time"
    if pb_type.lower() == "fmc":
        pb_type = "move"
    if pb_type.lower() == "fmc mtm":
        pb_type = "move"        
    if pb_type.lower() == "moves":
        pb_type = "move"
    
    if pb_type == "move":
        power_system = "fmc"
    elif power_system == "fmc" and pb_type not in ["move"]:
        pb_type = "move"
        
    power_data, _, display_name, control_name = _run_power(power_system, display_type, control_type, pb_type)
    categories, tiers = POWER_SYSTEMS[power_system]
    
    player_row = find_player_in_power(power_data, username_substring)
    if not player_row:
        return f"No player matching '{username_substring}' found in power rankings."
    
    player_name = player_row[0]
    rank = player_row[1]
    total_power = player_row[2]
    times = player_row[3:]
    
    score_tiers_indices = []
    for i, t in enumerate(times):
        if i >= len(categories):
            break
        if t == -1 or t is None:
            score_tiers_indices.append(0)
        else:
            tier = get_score_tier_for_category(t, i, tiers)
            score_tiers_indices.append(tiers.index(tier))
    
    true_tier_idx = min(score_tiers_indices) if score_tiers_indices else 0
    true_tier_name = tiers[true_tier_idx]['name']
    
    final_tier_idx = 0
    for i in range(len(tiers)-1, -1, -1):
        if total_power >= tiers[i]['limit']:
            if any(idx >= i for idx in score_tiers_indices):
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
    
    info_line = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return f"({power_system.capitalize()} Power): {player_name} is in position {rank} with {total_power} power ({final_tier_name}, True {true_tier_name}){next_rank_info}\n{info_line}"

# ====================== FUNCTION: getreq ======================
def get_req(tier_substring, power_system, puzzle_size):
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)
    
    matched_tiers = find_tier_by_name(tiers, tier_substring)
    if not matched_tiers:
        return f"No tier matching '{tier_substring}' found in {power_system}."
    
    puzzle_str = f"{N}x{M}"
    lines = []
    
    for cat in categories:
        if cat['width'] == N and cat['height'] == M:
            cat_idx = categories.index(cat)
            cat_id = cat['id'].split(' ', 1)[1] if ' ' in cat['id'] else cat['id']
            
            reqs = []
            for t in matched_tiers:
                req_val = t['times'][cat_idx]
                if power_system == "fmc":
                    req_str = str(int(req_val))
                else:
                    req_str = format_score(req_val, "time")
                reqs.append(req_str)
            
            line = format_aligned_line(puzzle_str, cat_id, ' '.join(reqs))
            lines.append(line)
    
    if not lines:
        return f"No categories found for {puzzle_size} in {power_system}."
    
    tier_names = " ".join(t['name'] for t in matched_tiers)
    header = f"Requirements for {tier_names} {puzzle_str}"
    return header + "\n" + "\n".join(lines)

# ====================== CLI ======================
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
    else:
        print("Unknown command. Use getpb, getwr, numwrs, rank, or getreq.")