import sqlite3
from pathlib import Path
from datetime import datetime

def get_best_solves(marathon_length, width, height, db_path):
    """Get all solves with their splits for a specific marathon length"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all solves matching the criteria
    cursor.execute(
        """SELECT * FROM solves 
        WHERE width = ? AND height = ?
        AND solve_type = 'Marathon' AND marathon_length = ? 
        AND display_type='Standard' 
        AND scrambler='Random permutation'
        AND completed = 1""", 
        (width, height, marathon_length)
    )
    solves = cursor.fetchall()
    
    results = []
    for solve in solves:
        # Get all singles for this solve
        cursor.execute(
            "SELECT * FROM single_solves WHERE id BETWEEN ? AND ?",
            (solve['single_start_id'], solve['single_end_id'])
        )
        singles = cursor.fetchall()
        
        if len(singles) != marathon_length:
            continue  # Skip incomplete solves
        
        # Calculate cumulative times
        times = [single['time'] for single in singles]
        cumulative_times = []
        total_time = 0
        for time in times:
            total_time += time
            cumulative_times.append(total_time / 1000)  # Convert to seconds
        
        results.append({
            'timestamp': solve['timestamp'],
            'fulltime': solve['time'],
            'times': cumulative_times
        })
    
    conn.close()
    return results

def get_best_across_all(lengths_range, width, height, db_path):
    """Find best splits across all specified marathon lengths"""
    best_splits = {}
    
    for length in lengths_range:
        solves = get_best_solves(length, width, height, db_path)
        if not solves:
            continue  # Skip if no solves found for this length
        
        # For each split position (x1, x2, etc.)
        for split_pos in range(length):
            x_num = split_pos + 1
            
            # Find the best time for this split position across all solves
            for solve in solves:
                time = solve['times'][split_pos]
                timestamp = solve['timestamp']
                fulltime = solve['fulltime']
                
                if x_num not in best_splits or time < best_splits[x_num]['time']:
                    best_splits[x_num] = {
                        'time': time,
                        'marathon_length': length,
                        'timestamp': timestamp,
                        'fulltime': fulltime
                    }
    
    return best_splits

def format_timestamp(timestamp_ms):
    """Convert millisecond timestamp to readable date"""
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def print_best_splits(best_splits, max_x=42):
    """Print the best splits in a nice format"""
    if not best_splits:
        print("No valid solves found in the database")
        return
    
    print(f"\n{'Split':<6}{'Time':<12}{'From':<12}{'Date':<20}")
    print("-" * 50)
    
    for x_num in sorted(best_splits.keys()):
        if x_num > max_x:
            continue
        
        split = best_splits[x_num]
        print(f"x{x_num:<5}{split['time']:.3f}s{' from x'+str(split['marathon_length']):<12} {split['fulltime']/1000:.5g} {format_timestamp(split['timestamp'])}")

def getMarathons(width, height, db_path=r'solves.db'):
    """
    Get best marathon splits for all lengths (2-100) for the specified width and height.
    
    Args:
        width (int): The width of the puzzle (N in NxM)
        height (int): The height of the puzzle (M in NxM)
        db_path (str): Path to the SQLite database file (default: 'solves.db')
    
    Returns:
        dict: A dictionary containing the best splits information
    """
    best_splits = get_best_across_all(range(2, 101), width, height, db_path)
    return best_splits

if __name__ == "__main__":
    import sys
    if len(sys.argv) not in [3, 4]:
        print("Usage: python marathon.py <width> <height> [db_path]")
        print("Example: python marathon.py 6 6")
        print("Example: python marathon.py 6 6 'C:\\path\\to\\solves.db'")
        sys.exit(1)
    
    try:
        width = int(sys.argv[1])
        height = int(sys.argv[2])
        db_path = sys.argv[3] if len(sys.argv) == 4 else r'solves.db'
        
        best_splits = getMarathons(width, height, db_path)
        print(f"Best splits across all marathon lengths (2-100) for {width}x{height}:")
        print_best_splits(best_splits)
    except ValueError:
        print("Error: Width and height must be positive integers")