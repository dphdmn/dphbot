import subprocess
import sys
import json
import math
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
    if len(parts) != 2:
        raise ValueError("Puzzle size must be NxM, e.g., 4x4")
    return int(parts[0]), int(parts[1])

def format_time_ms(ms, score_type="time"):
    if ms is None or ms == -1:
        return "-"
    if score_type == "move":
        return str(int(ms))
    return f"{ms/1000:.3f}"

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
    if gameMode == "Standard":
        if avglen == 1:
            return f"{width}x{height} single"
        else:
            return f"{width}x{height} ao{avglen}"
    elif gameMode.startswith("Marathon"):
        num = gameMode.split(" ")[1]
        return f"{width}x{height} x{num}"
    elif gameMode == "2-N relay":
        return f"{width}x{height} relay"
    elif gameMode == "Everything-up-to relay":
        return f"{width}x{height} eut"
    else:
        return f"{width}x{height} {gameMode}"

def get_all_categories_for_puzzle(N, M):
    categories = []
    for avglen in [1, 5, 12, 25, 50, 100]:
        categories.append((get_category_id(N, M, "Standard", avglen), "Standard", avglen))
    for mlen in [10, 25, 42, 50, 100]:
        categories.append((get_category_id(N, M, f"Marathon {mlen}", 1), f"Marathon {mlen}", 1))
    categories.append((get_category_id(N, M, "2-N relay", 1), "2-N relay", 1))
    categories.append((get_category_id(N, M, "Everything-up-to relay", 1), "Everything-up-to relay", 1))
    return categories

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
            return f"{val/1000:.3f}" if val and val != -1 else "-"
        def format_secondary(score):
            moves = f"{score['moves']/1000:.3f}" if score['moves'] and score['moves'] != -1 else "-"
            tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            return f"({moves}/{tps})"
    elif pb_type == "move":
        def get_primary(score):
            return score['moves']
        def format_primary(val):
            return f"{val/1000:.3f}" if val and val != -1 else "-"
        def format_secondary(score):
            time = f"{score['time']/1000:.3f}" if score['time'] and score['time'] != -1 else "-"
            tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            return f"({time}/{tps})"
    elif pb_type == "tps":
        def get_primary(score):
            return score['tps']
        def format_primary(val):
            return f"{val/1000:.3f}" if val and val != -1 else "-"
        def format_secondary(score):
            time = f"{score['time']/1000:.3f}" if score['time'] and score['time'] != -1 else "-"
            moves = f"{score['moves']/1000:.3f}" if score['moves'] and score['moves'] != -1 else "-"
            return f"({time}/{moves})"
    else:
        def get_primary(score):
            return score['time']
        def format_primary(val):
            return str(int(val)) if val and val != -1 else "-"
        def format_secondary(score):
            return ""
    
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
                            next_req_str = f"{next_req/1000:.3f}"
                            tier_annotation += f"({next_tier['name']}={next_req_str})"
                    break
        
        line = f"{cat_id:<20}: {value_str}{tier_annotation}"
        lines.append(line)
    
    if not lines:
        return f"No {pb_type} PBs found for {player_name} on {puzzle_size}."
    
    header = f"{N}x{M} {pb_type.upper()} PBs for {player_name}"
    info_line = f"[Display: {display_name} | Control: {control_name} | Power: {power_system.capitalize()}]"
    return header + "\n" + info_line + "\n" + "\n".join(lines)


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
    
    # Force move <-> fmc relationship
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
    
    lines = []
    for cat in categories:
        if cat['width'] == N and cat['height'] == M:
            cat_idx = categories.index(cat)
            reqs = []
            for t in matched_tiers:
                req_val = t['times'][cat_idx]
                if power_system == "fmc":
                    req_str = str(int(req_val))
                else:
                    req_str = f"{req_val/1000:.3f}"
                reqs.append(req_str)
            line = f"{cat['id']}: {' '.join(reqs)}"
            lines.append(line)
    
    if not lines:
        return f"No categories found for {puzzle_size} in {power_system}."
    
    tier_names = " ".join(t['name'] for t in matched_tiers)
    header = f"Requirements for {tier_names} {N}x{M}"
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
        print("Unknown command. Use getpb, rank, or getreq.")