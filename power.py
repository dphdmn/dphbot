#!/usr/bin/env python3
"""
Power ranking script.
Usage: python power.py <displayType> <controlType> <pbType> <mode>
Example: python power.py 18 3 1 modern

This script will first call fetch.py to update the merged leaderboard,
then calculate power rankings from the resulting file.
"""

import sys
import json
import math
import os
import subprocess
from power_data import *

# ======================== FETCH & LOAD FUNCTIONS ========================
def update_merged_leaderboard(display_type, control_type, pb_type):
    """Call fetch.py to update merged_leaderboard.txt with the given parameters."""
    print(f"Updating merged leaderboard (display={display_type}, control={control_type}, pb={pb_type})...")
    result = subprocess.run(
        [sys.executable, "fetch.py", str(display_type), str(control_type), str(pb_type)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Error running fetch.py:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(result.stdout)

def load_merged_scores(filepath):
    """Load merged scores from a JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {filepath} not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}", file=sys.stderr)
        sys.exit(1)

# ======================== POWER CALCULATION ========================
def get_score_tier(time, index, tiers):
    for i in range(len(tiers)-1, -1, -1):
        if time <= tiers[i]['times'][index]:
            return tiers[i]
    return tiers[0]

def calculate_dynamic_power(player_times_ms):
    """
    player_times_ms : list of 30 times in milliseconds (matching DYNAMIC_CATEGORIES).
    Returns total dynamic power (integer, floor of sum).
    """
    total = 0
    tiers_order = [
        "Beginner", "Bronze", "Silver", "Gold", "Platinum",
        "Diamond", "Master", "Grandmaster", "Nova", "Ascended",
        "Aleph", "Gamma"
    ]

    for idx, cat in enumerate(DYNAMIC_CATEGORIES):
        time_ms = player_times_ms[idx]
        if time_ms is None or time_ms <= 0:
            continue
        time_s = time_ms / 1000.0
        if time_s < 0.001:
            continue

        # get thresholds and gains in order from worst (Beginner) to best (Gamma)
        thresholds = [DYNAMIC_DATA[tier]["times"][cat] for tier in tiers_order]
        gains = [DYNAMIC_DATA[tier]["gain"] for tier in tiers_order]

        # Find the highest index (best tier) whose threshold is still >= time_s
        upper_idx = 0
        while upper_idx + 1 < len(thresholds) and time_s <= thresholds[upper_idx + 1]:
            upper_idx += 1

        # Now upper_idx is the tier that time_s beats (time_s <= its threshold)
        extrema_time0 = thresholds[upper_idx]
        extrema_power0 = gains[upper_idx]

        if upper_idx == len(thresholds) - 1:
            # Beyond all defined tiers – extrapolate towards 0 time
            extrema_time1 = 1e-3
            extrema_power1 = 50000
        else:
            extrema_time1 = thresholds[upper_idx + 1]
            extrema_power1 = gains[upper_idx + 1]

        # Linear interpolation
        ratio = (extrema_time0 - time_s) / (extrema_time0 - extrema_time1) if extrema_time0 != extrema_time1 else 0
        power = extrema_power0 + (extrema_power1 - extrema_power0) * ratio
        total += math.floor(power)

    return total

def calculate_player_power(saved_player_scores, tiers, fmc=False):
    # saved_player_scores: list of {name, scores: [score_info, ...]}
    # score_info is the original leaderboard entry with 'time' and 'moves'
    players = []
    fun_tiers = ['Gamma+', 'G++', 'Egg']  # only relevant for old power, but we check globally anyway
    is_old_power = False  # will be set if any score hits a fun tier (only used for old power)
    for player in saved_player_scores:
        player_times = []
        total_power = 0
        highest_score_tiers = []
        for idx, score_info in enumerate(player['scores']):
            if fmc:
                val = score_info.get('moves', -1)
            else:
                val = score_info.get('time', -1)
            if val is None or val <= 0:
                player_times.append(-1)
                highest_score_tiers.append(tiers[0])
            else:
                player_times.append(val)
                tier = get_score_tier(val, idx, tiers)
                added_power = tier['power']
                if tier['name'] in fun_tiers:
                    added_power = 10101  # force 10101 for fun tiers
                    is_old_power = True
                total_power += added_power
                highest_score_tiers.append(tier)
        # Dynamic fallback only for old power when total == 303030
        if total_power == 303030 and is_old_power:
            total_power = calculate_dynamic_power(player_times)
        # Determine final tier based on total power and at least one score tier
        supposed_tier_idx = 0
        for i in range(len(tiers)-1, -1, -1):
            if total_power >= tiers[i]['limit']:
                supposed_tier_idx = i
                break
        final_tier_idx = supposed_tier_idx
        while final_tier_idx >= 0:
            current_tier = tiers[final_tier_idx]
            if any(tiers.index(st) >= final_tier_idx for st in highest_score_tiers):
                break
            final_tier_idx -= 1
        if final_tier_idx < 0:
            final_tier_idx = 0
        players.append({
            'name': player['name'],
            'totalPower': total_power,
            'times': player_times,
            'finalTierIndex': final_tier_idx
        })
    # Sort: higher tier first, then higher power
    players.sort(key=lambda p: (-p['finalTierIndex'], -p['totalPower']))
    return players

# ======================== MAIN ========================
if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: python power.py <displayType> <controlType> <pbType> <mode>", file=sys.stderr)
        print("Example: python power.py 18 3 1 modern", file=sys.stderr)
        sys.exit(1)
    
    try:
        display_type = int(sys.argv[1])
        control_type = int(sys.argv[2])
        pb_type = int(sys.argv[3])
    except ValueError:
        print("displayType, controlType, and pbType must be integers.", file=sys.stderr)
        sys.exit(1)
    
    mode = sys.argv[4].lower()
    if mode == 'modern':
        categories = MODERN_CATEGORIES
        tiers = MODERN_TIERS
        fmc = False
    elif mode == 'classic':
        categories = OLD_CATEGORIES
        tiers = OLD_TIERS
        fmc = False
    elif mode == 'fmc':
        categories = FMC_CATEGORIES
        tiers = FMC_TIERS
        fmc = True
    else:
        print("Unknown mode. Use modern, classic, or fmc.", file=sys.stderr)
        sys.exit(1)

    # Step 1: Update merged leaderboard by calling fetch.py
    update_merged_leaderboard(display_type, control_type, pb_type)

    # Step 2: Load merged scores from combination-specific file
    combo_file = f"merged_leaderboards/{display_type}_{control_type}_{pb_type}.txt"
    print(f"Loading merged scores from {combo_file}...")
    all_scores = load_merged_scores(combo_file)
    print(f"Loaded {len(all_scores)} total merged scores.")

    # Step 3: Build best-per-player-per-category structure
    category_best = {}  # cat_index -> {playername -> best_score}
    for idx, cat in enumerate(categories):
        cat_best = {}
        for s in all_scores:
            if (s['width'] == cat['width'] and s['height'] == cat['height']
                and s['avglen'] == cat['avglen'] and s['gameMode'] == cat['gameMode']):
                name = s['nameFilter']
                val = s['moves'] if fmc else s['time']
                if name not in cat_best:
                    cat_best[name] = s
                else:
                    old_val = cat_best[name]['moves'] if fmc else cat_best[name]['time']
                    if val < old_val:
                        cat_best[name] = s
        category_best[idx] = cat_best

    # Step 4: Collect all player names
    all_players = set()
    for cat_best in category_best.values():
        all_players.update(cat_best.keys())
    
    # Step 5: Build player scores in fixed order
    saved_player_scores = []
    for name in all_players:
        scores = []
        for idx in range(len(categories)):
            scores.append(category_best[idx].get(name, {'time': -1, 'moves': -1}))
        saved_player_scores.append({'name': name, 'scores': scores})

    # Step 6: Calculate power
    print(f"Calculating power rankings for {len(saved_player_scores)} players...")
    power_data = calculate_player_power(saved_player_scores, tiers, fmc)

    # Step 7: Output as array of [name, rank, power, ...times]
    output = []
    for i, p in enumerate(power_data):
        row = [p['name'], i+1, p['totalPower']] + p['times']
        output.append(row)

    # Step 8: Write to file
    output_path = "power.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)
    print(f"Power rankings written to {output_path}")
    print(f"Top 10 players:")
    for row in output[:10]:
        print(f"  {row[1]}. {row[0]} - Power: {row[2]}")