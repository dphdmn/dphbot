import subprocess
import sys
import json
import math

# ====================== LOAD DATA ======================
def load_merged_leaderboard():
    """Always fetch fresh leaderboard data with default parameters."""
    print("Fetching fresh leaderboard data...")
    # Default: display_type=18 (Standard), control_type=3 (unique), pb_type=1 (time)
    subprocess.run([sys.executable, "fetch.py", "18", "3", "1"], check=True)
    with open("merged_leaderboard.txt", "r", encoding="utf-8") as f:
        return json.load(f)

def load_power_data(power_system="modern"):
    """Always generate fresh power data for the given system."""
    print(f"Generating fresh {power_system} power data...")
    subprocess.run([sys.executable, "power.py", power_system], check=True)
    with open("power.txt", "r", encoding="utf-8") as f:
        return json.load(f)

# ====================== MAP POWER SYSTEM TO FILE ======================
POWER_FILE_MAP = {
    "modern": "power.txt",
    "classic": "power.txt",  # power.py saves to power.txt regardless
    "fmc": "power.txt",
}

# ====================== CONSTANTS ======================
# Maps control type string (as used in function arguments) to the exact field value.
CONTROL_MAP = {
    "unique": None,   # no filter
    "keyboard": "Keyboard",
    "mouse": "Mouse",
    "click": "Click",
    "touch": "Touch"
}

# Categories for each power system (order must match power.txt rows)
MODERN_CATEGORIES = [
    {"id":"3x3 ao12","width":3,"height":3,"avglen":12,"gameMode":"Standard"},
    {"id":"3x3 ao50","width":3,"height":3,"avglen":50,"gameMode":"Standard"},
    {"id":"3x3 ao100","width":3,"height":3,"avglen":100,"gameMode":"Standard"},
    {"id":"3x3 x42","width":3,"height":3,"avglen":1,"gameMode":"Marathon 42"},
    {"id":"4x4 ao5","width":4,"height":4,"avglen":5,"gameMode":"Standard"},
    {"id":"4x4 ao12","width":4,"height":4,"avglen":12,"gameMode":"Standard"},
    {"id":"4x4 ao50","width":4,"height":4,"avglen":50,"gameMode":"Standard"},
    {"id":"4x4 ao100","width":4,"height":4,"avglen":100,"gameMode":"Standard"},
    {"id":"4x4 x10","width":4,"height":4,"avglen":1,"gameMode":"Marathon 10"},
    {"id":"5x5 single","width":5,"height":5,"avglen":1,"gameMode":"Standard"},
    {"id":"5x5 ao5","width":5,"height":5,"avglen":5,"gameMode":"Standard"},
    {"id":"5x5 ao12","width":5,"height":5,"avglen":12,"gameMode":"Standard"},
    {"id":"5x5 ao50","width":5,"height":5,"avglen":50,"gameMode":"Standard"},
    {"id":"6x6 single","width":6,"height":6,"avglen":1,"gameMode":"Standard"},
    {"id":"6x6 ao5","width":6,"height":6,"avglen":5,"gameMode":"Standard"},
    {"id":"6x6 ao12","width":6,"height":6,"avglen":12,"gameMode":"Standard"},
    {"id":"6x6 relay","width":6,"height":6,"avglen":1,"gameMode":"2-N relay"},
    {"id":"7x7 single","width":7,"height":7,"avglen":1,"gameMode":"Standard"},
    {"id":"7x7 ao5","width":7,"height":7,"avglen":5,"gameMode":"Standard"},
    {"id":"7x7 ao12","width":7,"height":7,"avglen":12,"gameMode":"Standard"},
    {"id":"7x7 relay","width":7,"height":7,"avglen":1,"gameMode":"2-N relay"},
    {"id":"8x8 single","width":8,"height":8,"avglen":1,"gameMode":"Standard"},
    {"id":"8x8 ao5","width":8,"height":8,"avglen":5,"gameMode":"Standard"},
    {"id":"9x9 single","width":9,"height":9,"avglen":1,"gameMode":"Standard"},
    {"id":"9x9 ao5","width":9,"height":9,"avglen":5,"gameMode":"Standard"},
    {"id":"10x10 single","width":10,"height":10,"avglen":1,"gameMode":"Standard"},
    {"id":"10x10 ao5","width":10,"height":10,"avglen":5,"gameMode":"Standard"},
    {"id":"12x12 single","width":12,"height":12,"avglen":1,"gameMode":"Standard"},
    {"id":"16x16 single","width":16,"height":16,"avglen":1,"gameMode":"Standard"},
    {"id":"20x20 single","width":20,"height":20,"avglen":1,"gameMode":"Standard"},
]

CLASSIC_CATEGORIES = [
    {"id":"3x3 ao5","width":3,"height":3,"avglen":5,"gameMode":"Standard"},
    {"id":"3x3 ao12","width":3,"height":3,"avglen":12,"gameMode":"Standard"},
    {"id":"3x3 ao50","width":3,"height":3,"avglen":50,"gameMode":"Standard"},
    {"id":"3x3 ao100","width":3,"height":3,"avglen":100,"gameMode":"Standard"},
    {"id":"3x3 x10","width":3,"height":3,"avglen":1,"gameMode":"Marathon 10"},
    {"id":"3x3 x42","width":3,"height":3,"avglen":1,"gameMode":"Marathon 42"},
    {"id":"4x4 single","width":4,"height":4,"avglen":1,"gameMode":"Standard"},
    {"id":"4x4 ao5","width":4,"height":4,"avglen":5,"gameMode":"Standard"},
    {"id":"4x4 ao12","width":4,"height":4,"avglen":12,"gameMode":"Standard"},
    {"id":"4x4 ao50","width":4,"height":4,"avglen":50,"gameMode":"Standard"},
    {"id":"4x4 ao100","width":4,"height":4,"avglen":100,"gameMode":"Standard"},
    {"id":"4x4 x10","width":4,"height":4,"avglen":1,"gameMode":"Marathon 10"},
    {"id":"4x4 x42","width":4,"height":4,"avglen":1,"gameMode":"Marathon 42"},
    {"id":"4x4 relay","width":4,"height":4,"avglen":1,"gameMode":"2-N relay"},
    {"id":"5x5 single","width":5,"height":5,"avglen":1,"gameMode":"Standard"},
    {"id":"5x5 ao5","width":5,"height":5,"avglen":5,"gameMode":"Standard"},
    {"id":"5x5 ao12","width":5,"height":5,"avglen":12,"gameMode":"Standard"},
    {"id":"5x5 ao50","width":5,"height":5,"avglen":50,"gameMode":"Standard"},
    {"id":"5x5 relay","width":5,"height":5,"avglen":1,"gameMode":"2-N relay"},
    {"id":"6x6 single","width":6,"height":6,"avglen":1,"gameMode":"Standard"},
    {"id":"6x6 ao5","width":6,"height":6,"avglen":5,"gameMode":"Standard"},
    {"id":"6x6 ao12","width":6,"height":6,"avglen":12,"gameMode":"Standard"},
    {"id":"6x6 relay","width":6,"height":6,"avglen":1,"gameMode":"2-N relay"},
    {"id":"7x7 single","width":7,"height":7,"avglen":1,"gameMode":"Standard"},
    {"id":"7x7 ao5","width":7,"height":7,"avglen":5,"gameMode":"Standard"},
    {"id":"7x7 relay","width":7,"height":7,"avglen":1,"gameMode":"2-N relay"},
    {"id":"8x8 single","width":8,"height":8,"avglen":1,"gameMode":"Standard"},
    {"id":"8x8 ao5","width":8,"height":8,"avglen":5,"gameMode":"Standard"},
    {"id":"9x9 single","width":9,"height":9,"avglen":1,"gameMode":"Standard"},
    {"id":"10x10 single","width":10,"height":10,"avglen":1,"gameMode":"Standard"},
]

FMC_CATEGORIES = [
    {"id":"3x3 ao50","width":3,"height":3,"avglen":50,"gameMode":"Standard"},
    {"id":"3x3 ao100","width":3,"height":3,"avglen":100,"gameMode":"Standard"},
    {"id":"4x4 ao12","width":4,"height":4,"avglen":12,"gameMode":"Standard"},
    {"id":"4x4 ao50","width":4,"height":4,"avglen":50,"gameMode":"Standard"},
    {"id":"4x4 ao100","width":4,"height":4,"avglen":100,"gameMode":"Standard"},
    {"id":"5x5 ao5","width":5,"height":5,"avglen":5,"gameMode":"Standard"},
    {"id":"5x5 ao12","width":5,"height":5,"avglen":12,"gameMode":"Standard"},
    {"id":"6x6 single","width":6,"height":6,"avglen":1,"gameMode":"Standard"},
    {"id":"6x6 ao5","width":6,"height":6,"avglen":5,"gameMode":"Standard"},
    {"id":"7x7 single","width":7,"height":7,"avglen":1,"gameMode":"Standard"},
    {"id":"7x7 ao5","width":7,"height":7,"avglen":5,"gameMode":"Standard"},
    {"id":"8x8 single","width":8,"height":8,"avglen":1,"gameMode":"Standard"},
    {"id":"9x9 single","width":9,"height":9,"avglen":1,"gameMode":"Standard"},
    {"id":"10x10 single","width":10,"height":10,"avglen":1,"gameMode":"Standard"},
    {"id":"16x16 single","width":16,"height":16,"avglen":1,"gameMode":"Standard"},
]

# Tier definitions (only those needed for threshold lookups)
# Modern tiers (30 categories)
MODERN_TIERS = [
    {"name":"Unranked","power":0,"limit":0,"times":[86399999]*30},
    {"name":"Beginner","power":1,"limit":1,"times":[6500,7500,8000,335000,21000,23000,25000,26000,240000,45000,55000,60000,65000,85000,95000,100000,180000,120000,135000,145000,300000,180000,195000,260000,280000,360000,390000,720000,1500000,2820000]},
    {"name":"Bronze I","power":5,"limit":30,"times":[4000,4500,4800,210000,14700,16000,17500,18300,170000,30000,38000,42000,44000,55000,65000,70000,118000,87000,100000,109000,240000,135000,150000,190000,205000,280000,300000,500000,1140000,2160000]},
    {"name":"Bronze II","power":25,"limit":150,"times":[3100,3600,3900,170000,10800,12000,14000,14500,130000,22500,29000,32000,34000,45000,54000,58000,94000,70000,82000,90000,190000,110000,125000,160000,175000,230000,250000,420000,930000,1800000]},
    {"name":"Bronze III","power":50,"limit":400,"times":[2600,3000,3250,150000,8500,9700,11200,11700,105000,17500,23000,25000,27000,37000,44000,48000,76000,56000,66000,73000,145000,92000,105000,135000,150000,190000,210000,360000,780000,1500000]},
    {"name":"Silver I","power":125,"limit":1000,"times":[2200,2600,2800,133000,7000,8000,9300,9750,88000,14000,19000,21000,23000,31000,36000,40000,65000,49000,58000,64000,125000,80000,91000,120000,132000,160000,175000,310000,680000,1320000]},
    {"name":"Silver II","power":250,"limit":2500,"times":[1850,2250,2400,120000,5900,6800,8000,8400,76000,11500,15700,17500,20000,26500,32000,35000,55000,43000,52000,56000,110000,70000,80000,105000,117000,140000,155000,270000,600000,1140000]},
    {"name":"Silver III","power":400,"limit":4000,"times":[1650,2000,2150,110000,5200,6000,7000,7350,68000,10000,14000,15500,17000,23500,29000,31500,50000,39000,47500,51000,101000,63000,73000,96000,107000,125000,140000,240000,545000,1030000]},
    {"name":"Gold I","power":555,"limit":6666,"times":[1450,1750,1900,100000,4600,5350,6250,6500,61000,9300,12700,14200,15500,21000,26500,29000,45000,36000,44000,47000,94000,57000,67000,88000,98000,115000,130000,217000,495000,940000]},
    {"name":"Gold II","power":700,"limit":10000,"times":[1300,1600,1720,92000,4100,4850,5700,5950,56000,8400,11700,13000,14200,19000,24000,26500,41000,33500,41000,44000,87000,53000,62000,81000,90000,107000,120000,204000,460000,880000]},
    {"name":"Gold III","power":875,"limit":14000,"times":[1200,1500,1600,86000,3800,4500,5300,5550,52000,7700,10800,12000,13200,17500,22000,24200,38000,31000,38000,41000,81000,49000,58000,75000,84000,100000,110000,192000,435000,830000]},
    {"name":"Platinum I","power":1111,"limit":18500,"times":[1100,1400,1500,82000,3500,4200,4950,5150,48500,7100,10000,11000,12300,16000,20600,22500,35500,29000,35500,38000,75000,46000,54000,70000,79000,95000,105000,182000,411000,780000]},
    {"name":"Platinum II","power":1400,"limit":25000,"times":[1000,1300,1390,79000,3250,3900,4600,4800,45500,6600,9300,10300,11400,14700,19300,21000,33000,27000,33000,35500,70000,43000,50000,66000,75000,90000,100000,172000,388000,740000]},
    {"name":"Platinum III","power":1850,"limit":33333,"times":[900,1200,1280,76000,3050,3650,4300,4500,42500,6150,8600,9500,10600,13500,18000,19600,31000,25000,30500,33000,66000,40000,47000,62000,71000,85000,95000,163000,367000,700000]},
    {"name":"Diamond I","power":2500,"limit":50000,"times":[850,1100,1170,73000,2800,3400,4000,4200,40000,5700,8000,8900,9800,12500,17000,18500,29000,23500,28500,30500,63000,37500,44000,58500,67000,80000,90000,155000,345000,660000]},
    {"name":"Diamond II","power":3500,"limit":70000,"times":[800,1050,1120,70000,2670,3150,3750,3950,37500,5300,7500,8300,9200,11700,16100,17500,27400,22000,27000,29000,60000,35500,41500,55000,63000,76000,85000,147000,330000,630000]},
    {"name":"Diamond III","power":5000,"limit":100000,"times":[750,1000,1060,67500,2550,3000,3550,3720,36000,4900,7100,7900,8750,11000,15300,16700,26000,21000,25700,27500,57000,34000,39500,52000,60000,72000,81000,140000,317000,600000]},
    {"name":"Master I","power":6666,"limit":140000,"times":[710,950,1000,65000,2420,2850,3400,3550,34500,4500,6700,7500,8300,10300,14500,15800,24700,20000,24500,26300,54500,32500,38000,49500,57000,69000,77000,133000,304000,580000]},
    {"name":"Master II","power":8500,"limit":185000,"times":[670,900,950,62500,2300,2730,3250,3400,33000,4200,6350,7150,7900,9700,13700,15000,23500,19000,23500,25300,52000,31200,36500,47000,54000,66000,74000,126000,292000,560000]},
    {"name":"Master III","power":11500,"limit":250000,"times":[640,850,900,60000,2170,2600,3100,3230,31500,3900,6000,6800,7500,9250,12900,14100,22500,18200,22500,24200,49500,30000,35000,45000,51500,63000,71000,120000,280000,540000]},
    {"name":"Grandmaster I","power":16000,"limit":360000,"times":[610,800,850,57500,2050,2470,2950,3050,30500,3650,5700,6450,7150,8800,12200,13400,21600,17500,21600,23200,47500,28800,33800,43200,49500,60000,68000,115000,270000,520000]},
    {"name":"Grandmaster II","power":24000,"limit":525000,"times":[580,750,800,55500,1950,2350,2820,2920,29500,3400,5400,6100,6800,8400,11600,12800,20700,16700,20800,22300,45700,27600,32600,41500,47500,57500,65500,110000,260000,500000]},
    {"name":"Grandmaster III","power":33333,"limit":750000,"times":[550,700,750,53500,1850,2250,2700,2800,28500,3150,5100,5800,6500,8000,11000,12200,20000,16000,20000,21500,44000,26500,31500,40000,46000,55000,63000,105000,250000,480000]},
    {"name":"Ascended","power":50000,"limit":1000000,"times":[480,600,650,50000,1650,2000,2400,2500,26000,2600,4400,5200,5800,7000,9500,10700,18000,14000,18000,19500,40000,24000,28500,36000,42000,50000,58000,95000,225000,440000]},
]

# Classic tiers (30 categories)
CLASSIC_TIERS = [
    {"name":"Unranked","power":0,"limit":0,"times":[86399999]*30},
    {"name":"Beginner","power":1,"limit":1,"times":[4300,6300,7700,8200,105000,540000,12000,20000,23000,28000,29000,310000,1450000,28500,42000,60000,65000,70000,90000,100000,125000,140000,240000,185000,230000,460000,307000,355000,460000,666000]},
    {"name":"Bronze","power":3,"limit":10,"times":[2800,4100,5000,5300,68000,350000,7500,13000,15000,18500,19000,200000,950000,18500,27000,38500,41000,46000,59000,65000,82000,92000,155000,120000,150000,300000,200000,230000,300000,430000]},
    {"name":"Silver","power":7,"limit":33,"times":[1800,2650,3200,3450,44000,230000,5000,8500,10000,12000,12500,130000,625000,12000,17500,25000,26500,30000,38000,42000,53000,60000,100000,78000,98000,195000,130000,150000,195000,280000]},
    {"name":"Gold","power":20,"limit":100,"times":[1450,2100,2550,2750,35000,185000,4000,6750,8000,9500,10000,105000,500000,9500,14000,20000,21000,24000,30000,33000,42000,48000,80000,62000,78000,155000,103000,120000,155000,225000]},
    {"name":"Platinum","power":50,"limit":500,"times":[1150,1700,2050,2200,27500,148000,3250,5400,6500,7600,8000,83000,400000,7600,11000,15500,17000,19500,23500,26000,33000,38000,63000,49000,62000,125000,82000,97000,125000,180000]},
    {"name":"Diamond","power":150,"limit":900,"times":[1000,1500,1800,1900,24000,130000,2850,4700,5700,6700,7050,73000,350000,6700,9500,13500,15000,17000,20500,22500,29000,33000,55000,43000,54000,110000,72000,85000,110000,155000]},
    {"name":"Master","power":400,"limit":4000,"times":[900,1300,1600,1650,21000,115000,2500,4100,5000,5900,6200,64000,305000,5900,8200,11500,13100,15000,18200,20000,25500,29000,48000,38000,47000,97000,63000,74000,96000,135000]},
    {"name":"Grandmaster","power":1000,"limit":12000,"times":[800,1150,1400,1450,18500,100000,2200,3600,4400,5200,5450,56000,270000,5200,7200,10000,11500,13000,16000,17500,22500,25500,42000,33000,41000,85000,55000,65000,84000,120000]},
    {"name":"Nova","power":3000,"limit":40000,"times":[700,1000,1250,1300,16500,88000,1900,3200,3850,4550,4800,50000,240000,4600,6300,9000,10400,11500,14000,15500,20000,22500,37000,29000,36000,75000,48000,57000,74000,106000]},
    {"name":"Ascended","power":6666,"limit":100000,"times":[620,850,1100,1150,14500,78000,1700,2800,3400,4000,4250,44000,215000,4100,5600,8100,9200,10200,12500,13500,17500,20000,32500,25500,32000,66000,42000,50000,65000,93000]},
    {"name":"Aleph","power":8080,"limit":208080,"times":[550,750,950,1000,13000,70000,1500,2500,3000,3500,3700,38000,185000,3600,5000,7100,8100,9000,11000,12000,15500,17200,28000,22500,28000,57000,38000,45000,57000,81000]},
    {"name":"Gamma","power":10101,"limit":256000,"times":[450,650,850,900,11500,62000,1350,2200,2650,3100,3300,33500,165000,3200,4500,6200,7200,8000,9700,10600,13500,15000,25000,20000,24500,50000,33500,40000,50000,72000]},
    {"name":"Gamma+","power":10101,"limit":303030,"times":[400,550,750,800,10500,56000,1000,1900,2350,2800,2950,30000,150000,2800,3750,5400,6300,7000,8000,9000,11500,13000,21000,16500,21000,44000,28000,34000,44000,60000]},
    {"name":"G++","power":"Dynamic","limit":9999999,"times":[350,500,650,700,9500,50000,800,1700,2100,2500,2650,27000,135000,2400,3000,4600,5500,6000,7000,7500,10000,11000,18000,14000,18000,38000,23000,28000,38000,50000]},
]

# FMC tiers (15 categories)
FMC_TIERS = [
    {"name":"Unranked","power":0,"limit":0,"times":[86399999]*15},
    {"name":"Beginner","power":2,"limit":1,"times":[35000,38000,110000,120000,125000,250000,275000,400000,500000,700000,850000,1100000,1600000,2200000,9000000]},
    {"name":"Bronze I","power":10,"limit":30,"times":[32500,34000,100000,110000,115000,230000,250000,360000,450000,630000,775000,1000000,1450000,2000000,8400000]},
    {"name":"Bronze II","power":50,"limit":150,"times":[31000,32500,95000,105000,110000,215000,235000,340000,425000,580000,715000,920000,1350000,1900000,7900000]},
    {"name":"Bronze III","power":100,"limit":400,"times":[30000,31000,90000,100000,105000,200000,220000,320000,400000,540000,675000,860000,1280000,1800000,7600000]},
    {"name":"Silver I","power":250,"limit":1000,"times":[29200,30200,86000,95000,100000,192000,210000,300000,385000,515000,640000,820000,1220000,1700000,7300000]},
    {"name":"Silver II","power":500,"limit":2500,"times":[28400,29400,82000,90000,95000,183000,200000,285000,370000,490000,615000,780000,1160000,1620000,7100000]},
    {"name":"Silver III","power":800,"limit":4000,"times":[27700,28600,78000,86000,90000,175000,192000,270000,355000,470000,590000,750000,1120000,1550000,6900000]},
    {"name":"Gold I","power":1110,"limit":6666,"times":[27000,27800,75000,83000,86000,168000,185000,260000,340000,450000,570000,720000,1080000,1500000,6700000]},
    {"name":"Gold II","power":1400,"limit":10000,"times":[26300,27100,72000,80000,83000,162000,178000,250000,325000,430000,550000,690000,1040000,1450000,6500000]},
    {"name":"Gold III","power":1750,"limit":14000,"times":[25600,26400,70000,77000,80000,156000,172000,240000,310000,410000,530000,660000,1000000,1400000,6300000]},
    {"name":"Platinum I","power":2222,"limit":18500,"times":[25000,25700,68000,75000,77000,150000,166000,230000,300000,390000,510000,630000,960000,1350000,6100000]},
    {"name":"Platinum II","power":2800,"limit":25000,"times":[24400,25100,66000,73000,75000,145000,160000,220000,290000,372000,490000,600000,920000,1300000,5900000]},
    {"name":"Platinum III","power":3700,"limit":33333,"times":[23800,24500,64500,71000,73000,140000,154000,210000,280000,355000,470000,580000,885000,1250000,5700000]},
    {"name":"Diamond I","power":5000,"limit":50000,"times":[23300,24000,63000,69000,71000,135000,148000,200000,270000,340000,450000,560000,850000,1200000,5550000]},
    {"name":"Diamond II","power":7000,"limit":70000,"times":[22800,23500,61500,67500,69000,130000,143000,190000,260000,325000,435000,540000,820000,1150000,5400000]},
    {"name":"Diamond III","power":10000,"limit":100000,"times":[22400,23100,60000,66000,67500,125000,138000,182000,250000,312000,420000,520000,790000,1120000,5250000]},
    {"name":"Master I","power":13333,"limit":140000,"times":[22000,22700,58500,64500,66000,121000,134000,175000,242000,300000,405000,500000,760000,1090000,5100000]},
    {"name":"Master II","power":17000,"limit":185000,"times":[21600,22300,57000,63000,64500,117000,130000,170000,236000,290000,390000,482000,740000,1060000,5000000]},
    {"name":"Master III","power":23000,"limit":250000,"times":[21300,22000,55500,61500,63000,114000,126000,165000,230000,281000,380000,465000,720000,1030000,4900000]},
    {"name":"Grandmaster I","power":32000,"limit":360000,"times":[21000,21600,54500,60000,61500,111000,123000,160000,222000,272000,370000,450000,700000,1000000,4800000]},
    {"name":"Grandmaster II","power":48000,"limit":525000,"times":[20700,21300,53500,58700,60000,108000,120000,155000,216000,263000,360000,437000,680000,970000,4700000]},
    {"name":"Grandmaster III","power":66666,"limit":750000,"times":[20500,21100,52500,57500,58500,105000,117000,150000,210000,255000,350000,425000,660000,940000,4600000]},
    {"name":"Ascended","power":100000,"limit":1000000,"times":[20000,20600,50000,55000,56000,100000,110000,140000,200000,240000,330000,400000,625000,880000,4400000]},
]

# Map power system name to (categories, tiers)
POWER_SYSTEMS = {
    "modern": (MODERN_CATEGORIES, MODERN_TIERS),
    "classic": (CLASSIC_CATEGORIES, CLASSIC_TIERS),
    "fmc": (FMC_CATEGORIES, FMC_TIERS),
}

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
def get_pb(username_substring, puzzle_size, power_system="modern"):
    merged = load_merged_leaderboard()
    power_data = load_power_data(power_system)
    categories, tiers = POWER_SYSTEMS[power_system]
    N, M = parse_puzzle_size(puzzle_size)
    
    player_row = find_player_in_power(power_data, username_substring)
    if not player_row:
        return f"No player matching '{username_substring}' found."
    player_name = player_row[0]
    
    best_scores = get_best_scores_for_user(merged, player_name)
    all_cats = get_all_categories_for_puzzle(N, M)
    
    is_fmc = (power_system == "fmc")
    
    lines = []
    for cat_id, gameMode, avglen in all_cats:
        key = (N, M, gameMode, avglen)
        if key not in best_scores:
            continue
        
        score = best_scores[key]
        
        if is_fmc:
            primary_val = score['moves']
            primary_str = f"{primary_val/1000:.3f}" if primary_val and primary_val != -1 else "-"
            secondary_time = f"{score['time']/1000:.3f}" if score['time'] and score['time'] != -1 else "-"
            secondary_tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            value_str = f"{primary_str} ({secondary_time}/{secondary_tps})"
        else:
            primary_val = score['time']
            primary_str = f"{primary_val/1000:.3f}" if primary_val and primary_val != -1 else "-"
            secondary_moves = f"{score['moves']/1000:.3f}" if score['moves'] and score['moves'] != -1 else "-"
            secondary_tps = f"{score['tps']/1000:.3f}" if score['tps'] and score['tps'] != -1 else "-"
            value_str = f"{primary_str} ({secondary_moves}/{secondary_tps})"
        
        tier_annotation = ""
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
        return f"No PBs found for {player_name} on {puzzle_size}."
    
    header = f"{N}x{M} PBs for {player_name}"
    return header + "\n" + "\n".join(lines)

# ====================== FUNCTION: rank ======================
def get_rank(username_substring, power_system="modern"):
    power_data = load_power_data(power_system)
    categories, tiers = POWER_SYSTEMS[power_system]
    
    player_row = find_player_in_power(power_data, username_substring)
    if not player_row:
        return f"No player matching '{username_substring}' found in power rankings."
    
    player_name = player_row[0]
    rank = player_row[1]
    total_power = player_row[2]
    times = player_row[3:]
    
    # Determine tier for each individual score
    score_tiers_indices = []
    for i, t in enumerate(times):
        if i >= len(categories):
            break
        if t == -1 or t is None:
            score_tiers_indices.append(0)
        else:
            tier = get_score_tier_for_category(t, i, tiers)
            score_tiers_indices.append(tiers.index(tier))
    
    # True tier: LOWEST tier among all scores (worst category holds you back)
    true_tier_idx = min(score_tiers_indices) if score_tiers_indices else 0
    true_tier_name = tiers[true_tier_idx]['name']
    
    # Final tier: based on total power, requiring at least one score at that tier
    final_tier_idx = 0
    for i in range(len(tiers)-1, -1, -1):
        if total_power >= tiers[i]['limit']:
            if any(idx >= i for idx in score_tiers_indices):
                final_tier_idx = i
                break
    
    final_tier_name = tiers[final_tier_idx]['name']
    
    # Next rank info
    next_rank_info = ""
    if final_tier_idx < len(tiers) - 1:
        next_tier = tiers[final_tier_idx + 1]
        power_needed = next_tier['limit']
        
        if total_power >= power_needed:
            next_rank_info = f" ({next_tier['name']} = At least 1 {next_tier['name']} score)"
        else:
            next_rank_info = f" ({next_tier['name']} = {power_needed})"
    
    # ALWAYS show true tier
    return f"({power_system.capitalize()} Power): {player_name} is in position {rank} with {total_power} power ({final_tier_name}, True {true_tier_name}){next_rank_info}"

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
            print("Usage: python stats.py getPB <username> <puzzleSize> [powerSystem=modern]")
            sys.exit(1)
        username = sys.argv[2]
        puzzle = sys.argv[3]
        power = sys.argv[4] if len(sys.argv) > 4 else "modern"
        print(get_pb(username, puzzle, power))
    elif cmd == "rank":
        if len(sys.argv) < 3:
            print("Usage: python stats.py rank <username> [powerSystem=modern]")
            sys.exit(1)
        username = sys.argv[2]
        power = sys.argv[3] if len(sys.argv) > 3 else "modern"
        print(get_rank(username, power))
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