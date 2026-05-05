#!/usr/bin/env python3
"""
Power ranking script.
Usage: python power.py [modern|classic|fmc]
"""

import sys
import json
import math
import requests
import lzma
import io

# ======================== CONSTANTS from JS ========================
BASE_URL = "https://91.184.253.245.nip.io"
GUEST_TOKEN = "Basic R3Vlc3Q6NGJvaHBwNzd6Y2N4aXJ6eDljdmhiaw=="

DISPLAY_TYPE_MAP = {
    1: "Adjacent sum", 2: "Adjacent tiles", 3: "Chess", 4: "Fading tiles",
    5: "Fringe minimal", 6: "Incremental vectors", 7: "Inverse permutation",
    8: "Inverse vectors", 9: "Last move", 10: "Manhattan", 11: "Maximal unsolved",
    12: "Minesweeper", 13: "Minimal", 14: "Minimal unsolved", 15: "RGB",
    16: "Row minimal", 17: "Rows and columns", 18: "Standard",
    19: "Vanish on solved", 20: "Vectors", 21: "Cyclic", 22: "Divisible",
    23: "Vertical multi-tile", 24: "Rows", 25: "Square fringe",
    26: "Split square fringe", 27: "Checkerboard"
}
PB_TYPE_MAP = {1: "time", 2: "move", 3: "tps", 4: "FMC", 5: "FMC MTM"}
CONTROL_TYPE_MAP = {
    0: "Keyboard", 1: "Mouse", 2: "both", 3: "unique", 4: "Click", 5: "Touch"
}
SOLVE_TYPE_MAP = {
    1: "Standard", 2: "2-N relay", 3: "BLD", 4: "Everything-up-to relay",
    5: "Height relay", 6: "Width relay"
}
RENAME_MAP = {
    'ivy': 'daanbe', 'skye': 'iota', 'eggben': 'ben1996123', 'eskiu': 'sq',
    'HashPanda': 'Rafael', 'wiser': 'wiserboblouis', 'garyx': 'gr21xx',
    'ekimmy': 'ekim', 'ap_web': 'ap', 'juunas': 'asdfghqwerty',
    'minsie': 'MegaminX', '554': 'yzx'
}

# ----- Category lists for each power mode -----
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

OLD_CATEGORIES = [
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

# ----- Tier definitions (time values are in milliseconds, moves for FMC) -----
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

# Old power tiers (30 categories)
OLD_TIERS = [
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

# FMC tiers (15 categories, moves)
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

# Dynamic power tiers (used only for old power when fallback triggers)
DYNAMIC_DATA = {
    "Beginner": {"gain":1, "times":{"3x3 ao5":4.3,"3x3 ao12":6.3,"3x3 ao50":7.7,"3x3 ao100":8.2,"3x3 x10":105,"3x3 x42":540,"4x4 single":12,"4x4 ao5":20,"4x4 ao12":23,"4x4 ao50":28,"4x4 ao100":29,"4x4 x10":310,"4x4 x42":1450,"4x4 relay":28.5,"5x5 single":42,"5x5 ao5":60,"5x5 ao12":65,"5x5 ao50":70,"5x5 relay":90,"6x6 single":100,"6x6 ao5":125,"6x6 ao12":140,"6x6 relay":240,"7x7 single":185,"7x7 ao5":230,"7x7 relay":460,"8x8 single":307,"8x8 ao5":355,"9x9 single":460,"10x10 single":666}},
    "Bronze": {"gain":3, "times":{"3x3 ao5":2.8,"3x3 ao12":4.1,"3x3 ao50":5.0,"3x3 ao100":5.3,"3x3 x10":68,"3x3 x42":350,"4x4 single":7.5,"4x4 ao5":13,"4x4 ao12":15,"4x4 ao50":18.5,"4x4 ao100":19,"4x4 x10":200,"4x4 x42":950,"4x4 relay":18.5,"5x5 single":27,"5x5 ao5":38.5,"5x5 ao12":41,"5x5 ao50":46,"5x5 relay":59,"6x6 single":65,"6x6 ao5":82,"6x6 ao12":92,"6x6 relay":155,"7x7 single":120,"7x7 ao5":150,"7x7 relay":300,"8x8 single":200,"8x8 ao5":230,"9x9 single":300,"10x10 single":430}},
    "Silver": {"gain":7, "times":{"3x3 ao5":1.8,"3x3 ao12":2.65,"3x3 ao50":3.2,"3x3 ao100":3.45,"3x3 x10":44,"3x3 x42":230,"4x4 single":5,"4x4 ao5":8.5,"4x4 ao12":10,"4x4 ao50":12,"4x4 ao100":12.5,"4x4 x10":130,"4x4 x42":625,"4x4 relay":12,"5x5 single":17,"5x5 ao5":25,"5x5 ao12":26.5,"5x5 ao50":30,"5x5 relay":38,"6x6 single":42,"6x6 ao5":53,"6x6 ao12":60,"6x6 relay":100,"7x7 single":78,"7x7 ao5":98,"7x7 relay":195,"8x8 single":130,"8x8 ao5":150,"9x9 single":195,"10x10 single":280}},
    "Gold": {"gain":20, "times":{"3x3 ao5":1.45,"3x3 ao12":2.1,"3x3 ao50":2.55,"3x3 ao100":2.75,"3x3 x10":35,"3x3 x42":185,"4x4 single":4,"4x4 ao5":6.75,"4x4 ao12":8,"4x4 ao50":9.5,"4x4 ao100":10,"4x4 x10":105,"4x4 x42":500,"4x4 relay":9.5,"5x5 single":14,"5x5 ao5":20,"5x5 ao12":21,"5x5 ao50":24,"5x5 relay":30,"6x6 single":33,"6x6 ao5":42,"6x6 ao12":48,"6x6 relay":80,"7x7 single":62,"7x7 ao5":78,"7x7 relay":155,"8x8 single":103,"8x8 ao5":120,"9x9 single":155,"10x10 single":215}},
    "Platinum": {"gain":50, "times":{"3x3 ao5":1.15,"3x3 ao12":1.7,"3x3 ao50":2.05,"3x3 ao100":2.2,"3x3 x10":27.5,"3x3 x42":148,"4x4 single":3.25,"4x4 ao5":5.4,"4x4 ao12":6.5,"4x4 ao50":7.6,"4x4 ao100":8,"4x4 x10":83,"4x4 x42":400,"4x4 relay":7.6,"5x5 single":11,"5x5 ao5":15.5,"5x5 ao12":17,"5x5 ao50":19.5,"5x5 relay":23.5,"6x6 single":26,"6x6 ao5":33,"6x6 ao12":38,"6x6 relay":63,"7x7 single":49,"7x7 ao5":62,"7x7 relay":125,"8x8 single":82,"8x8 ao5":97,"9x9 single":125,"10x10 single":180}},
    "Diamond": {"gain":150, "times":{"3x3 ao5":1.0,"3x3 ao12":1.5,"3x3 ao50":1.8,"3x3 ao100":1.9,"3x3 x10":24,"3x3 x42":130,"4x4 single":2.85,"4x4 ao5":4.7,"4x4 ao12":5.7,"4x4 ao50":6.7,"4x4 ao100":7.05,"4x4 x10":73,"4x4 x42":350,"4x4 relay":6.7,"5x5 single":9.5,"5x5 ao5":13.5,"5x5 ao12":15,"5x5 ao50":17,"5x5 relay":20.5,"6x6 single":22.5,"6x6 ao5":29,"6x6 ao12":33,"6x6 relay":55,"7x7 single":43,"7x7 ao5":54,"7x7 relay":110,"8x8 single":72,"8x8 ao5":85,"9x9 single":110,"10x10 single":155}},
    "Master": {"gain":400, "times":{"3x3 ao5":0.9,"3x3 ao12":1.3,"3x3 ao50":1.6,"3x3 ao100":1.65,"3x3 x10":21,"3x3 x42":115,"4x4 single":2.5,"4x4 ao5":4.1,"4x4 ao12":5.0,"4x4 ao50":5.9,"4x4 ao100":6.2,"4x4 x10":64,"4x4 x42":305,"4x4 relay":5.9,"5x5 single":8.2,"5x5 ao5":11.5,"5x5 ao12":13.1,"5x5 ao50":15,"5x5 relay":18.2,"6x6 single":20,"6x6 ao5":25.5,"6x6 ao12":29,"6x6 relay":48,"7x7 single":38,"7x7 ao5":47,"7x7 relay":97,"8x8 single":63,"8x8 ao5":74,"9x9 single":96,"10x10 single":135}},
    "Grandmaster": {"gain":1000, "times":{"3x3 ao5":0.8,"3x3 ao12":1.15,"3x3 ao50":1.4,"3x3 ao100":1.45,"3x3 x10":18.5,"3x3 x42":100,"4x4 single":2.2,"4x4 ao5":3.6,"4x4 ao12":4.4,"4x4 ao50":5.2,"4x4 ao100":5.45,"4x4 x10":56,"4x4 x42":270,"4x4 relay":5.2,"5x5 single":7.2,"5x5 ao5":10,"5x5 ao12":11.5,"5x5 ao50":13,"5x5 relay":16,"6x6 single":17.5,"6x6 ao5":22.5,"6x6 ao12":25.5,"6x6 relay":42,"7x7 single":33,"7x7 ao5":41,"7x7 relay":85,"8x8 single":55,"8x8 ao5":65,"9x9 single":84,"10x10 single":120}},
    "Nova": {"gain":3000, "times":{"3x3 ao5":0.7,"3x3 ao12":1.0,"3x3 ao50":1.25,"3x3 ao100":1.3,"3x3 x10":16.5,"3x3 x42":88,"4x4 single":1.9,"4x4 ao5":3.2,"4x4 ao12":3.85,"4x4 ao50":4.55,"4x4 ao100":4.8,"4x4 x10":50,"4x4 x42":240,"4x4 relay":4.6,"5x5 single":6.3,"5x5 ao5":9.0,"5x5 ao12":10.4,"5x5 ao50":11.5,"5x5 relay":14,"6x6 single":15.5,"6x6 ao5":20.0,"6x6 ao12":22.5,"6x6 relay":37,"7x7 single":29,"7x7 ao5":36,"7x7 relay":75,"8x8 single":48,"8x8 ao5":57,"9x9 single":74,"10x10 single":106}},
    "Ascended": {"gain":6666, "times":{"3x3 ao5":0.62,"3x3 ao12":0.85,"3x3 ao50":1.1,"3x3 ao100":1.15,"3x3 x10":14.5,"3x3 x42":78,"4x4 single":1.7,"4x4 ao5":2.8,"4x4 ao12":3.4,"4x4 ao50":4.0,"4x4 ao100":4.25,"4x4 x10":44,"4x4 x42":215,"4x4 relay":4.1,"5x5 single":5.6,"5x5 ao5":8.1,"5x5 ao12":9.2,"5x5 ao50":10.2,"5x5 relay":12.5,"6x6 single":13.5,"6x6 ao5":17.5,"6x6 ao12":20.0,"6x6 relay":32.5,"7x7 single":25.5,"7x7 ao5":32,"7x7 relay":66,"8x8 single":42,"8x8 ao5":50,"9x9 single":65,"10x10 single":93}},
    "Aleph": {"gain":8080, "times":{"3x3 ao5":0.55,"3x3 ao12":0.75,"3x3 ao50":0.95,"3x3 ao100":1.0,"3x3 x10":13,"3x3 x42":70,"4x4 single":1.5,"4x4 ao5":2.5,"4x4 ao12":3.0,"4x4 ao50":3.5,"4x4 ao100":3.7,"4x4 x10":38,"4x4 x42":185,"4x4 relay":3.6,"5x5 single":5.0,"5x5 ao5":7.1,"5x5 ao12":8.1,"5x5 ao50":9.0,"5x5 relay":11,"6x6 single":12,"6x6 ao5":15.5,"6x6 ao12":17.2,"6x6 relay":28,"7x7 single":22.5,"7x7 ao5":28,"7x7 relay":57,"8x8 single":38,"8x8 ao5":45,"9x9 single":57,"10x10 single":81}},
    "Gamma": {"gain":10101, "times":{"3x3 ao5":0.45,"3x3 ao12":0.65,"3x3 ao50":0.85,"3x3 ao100":0.9,"3x3 x10":11.5,"3x3 x42":62,"4x4 single":1.35,"4x4 ao5":2.2,"4x4 ao12":2.65,"4x4 ao50":3.1,"4x4 ao100":3.3,"4x4 x10":33.5,"4x4 x42":165,"4x4 relay":3.2,"5x5 single":4.5,"5x5 ao5":6.2,"5x5 ao12":7.2,"5x5 ao50":8.0,"5x5 relay":9.7,"6x6 single":10.6,"6x6 ao5":13.5,"6x6 ao12":15.0,"6x6 relay":25,"7x7 single":20,"7x7 ao5":24.5,"7x7 relay":50,"8x8 single":33.5,"8x8 ao5":40,"9x9 single":50,"10x10 single":72}},
}

# Categories order for dynamic sum (same as old power category IDs)
DYNAMIC_CATEGORIES = [
    "3x3 ao5","3x3 ao12","3x3 ao50","3x3 ao100","3x3 x10","3x3 x42",
    "4x4 single","4x4 ao5","4x4 ao12","4x4 ao50","4x4 ao100","4x4 x10","4x4 x42","4x4 relay",
    "5x5 single","5x5 ao5","5x5 ao12","5x5 ao50","5x5 relay",
    "6x6 single","6x6 ao5","6x6 ao12","6x6 relay",
    "7x7 single","7x7 ao5","7x7 relay",
    "8x8 single","8x8 ao5","9x9 single","10x10 single"
]

# ======================== FETCHING FUNCTIONS ========================
def get_game_mode(solve_type, marathon_length):
    if solve_type in SOLVE_TYPE_MAP:
        return SOLVE_TYPE_MAP[solve_type]
    if solve_type is not None and solve_type >= 7:
        return f"Marathon {marathon_length}"
    return "Unknown"

def apply_rename(name):
    for new_name, old_name in RENAME_MAP.items():
        if name == old_name:
            return new_name
    return name

def parse_scores_text(text, display_type_str, pb_type_str, is_archive=False):
    lines = [line for line in text.split(';') if line.strip()]
    if not lines:
        return []
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

def fetch_live_scores(display_type, control_type, pb_type):
    url = f"{BASE_URL}/api/getScores"
    payload = {"display_type": display_type, "control_type": control_type, "pb_type": pb_type}
    headers = {"Authorization": GUEST_TOKEN, "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.text

def get_latest_web_archive_filename():
    url = "https://api.github.com/repos/dphdmn/slidyarch/contents/archives"
    resp = requests.get(url)
    resp.raise_for_status()
    files = resp.json()
    candidates = [f['name'] for f in files if f['name'].endswith('.lzma') and 'web' in f['name']]
    candidates.sort(reverse=True)
    return candidates[0] if candidates else None

def fetch_and_decompress_archive(filename):
    raw_url = f"https://raw.githubusercontent.com/dphdmn/slidyarch/main/archives/{filename}"
    resp = requests.get(raw_url)
    resp.raise_for_status()
    try:
        with lzma.open(io.BytesIO(resp.content), 'rt', format=lzma.FORMAT_XZ) as f:
            decompressed = f.read()
    except lzma.LZMAError:
        with lzma.open(io.BytesIO(resp.content), 'rt') as f:
            decompressed = f.read()
    return json.loads(decompressed)

def get_archive_scores(display_type, control_type, pb_type):
    filename = get_latest_web_archive_filename()
    if not filename:
        return ""
    archive = fetch_and_decompress_archive(filename)
    key = f"{display_type}_{control_type}_{pb_type}"
    return archive.get("data", {}).get(key, "")

def get_merged_scores(display_type, control_type, pb_type):
    display_type_str = DISPLAY_TYPE_MAP.get(display_type, str(display_type))
    pb_type_str = PB_TYPE_MAP.get(pb_type, str(pb_type))
    live_text = fetch_live_scores(display_type, control_type, pb_type)
    live_scores = parse_scores_text(live_text, display_type_str, pb_type_str, is_archive=False)
    try:
        archive_text = get_archive_scores(display_type, control_type, pb_type)
        web_scores = parse_scores_text(archive_text, display_type_str, pb_type_str, is_archive=True) if archive_text else []
    except Exception:
        web_scores = []
    
    # Merge: keep best per category based on leaderboardType
    merged = {}
    for s in live_scores:
        key = f"{s['width']}-{s['height']}-{s['leaderboardType']}-{s['controls']}-{s['gameMode']}-{s['displayType']}-{s['nameFilter']}-{s['avglen']}"
        s['isWeb'] = False
        merged[key] = s
    
    for w in web_scores:
        key = f"{w['width']}-{w['height']}-{w['leaderboardType']}-{w['controls']}-{w['gameMode']}-{w['displayType']}-{w['nameFilter']}-{w['avglen']}"
        if key not in merged:
            w['isWeb'] = True
            merged[key] = w
        else:
            live = merged[key]
            lb_type = w['leaderboardType']
            
            # Determine which metric to compare and direction
            if lb_type == 'tps':
                # Higher TPS is better
                if w['tps'] > live['tps']:
                    w['isWeb'] = True
                    merged[key] = w
            elif lb_type == 'move':
                # Lower moves is better
                if w['moves'] < live['moves']:
                    w['isWeb'] = True
                    merged[key] = w
            else:  # 'time', 'FMC', 'FMC MTM'
                # Lower time is better
                if w['time'] < live['time']:
                    w['isWeb'] = True
                    merged[key] = w
    
    return list(merged.values())

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
    if len(sys.argv) != 2:
        print("Usage: python power.py [modern|classic|fmc]")
        sys.exit(1)
    mode = sys.argv[1].lower()
    if mode == 'modern':
        categories = MODERN_CATEGORIES
        tiers = MODERN_TIERS
        pb_type = 1  # time
        fmc = False
    elif mode == 'classic':
        categories = OLD_CATEGORIES
        tiers = OLD_TIERS
        pb_type = 1
        fmc = False
    elif mode == 'fmc':
        categories = FMC_CATEGORIES
        tiers = FMC_TIERS
        pb_type = 2  # move
        fmc = True
    else:
        print("Unknown mode. Use modern, classic, or fmc.")
        sys.exit(1)

    print("Fetching scores...")
    all_scores = get_merged_scores(display_type=18, control_type=3, pb_type=pb_type)

    # Build best-per-player-per-category structure
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

    # Collect all player names
    all_players = set()
    for cat_best in category_best.values():
        all_players.update(cat_best.keys())
    # Build player scores in fixed order
    saved_player_scores = []
    for name in all_players:
        scores = []
        for idx in range(len(categories)):
            scores.append(category_best[idx].get(name, {'time': -1, 'moves': -1}))
        saved_player_scores.append({'name': name, 'scores': scores})

    # Calculate power
    power_data = calculate_player_power(saved_player_scores, tiers, fmc)

    # Output as array of [name, rank, power, ...times]
    output = []
    for i, p in enumerate(power_data):
        row = [p['name'], i+1, p['totalPower']] + p['times']
        output.append(row)

    # 4. Output to file
    output_path = "power.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)