#%%
import numpy as np
from utils import (
    SourceDetectorExtractor,
    neighborfilegeneration,
    badpairsdetection,
    probcoordinates
)
#%%
file_path = "probe_reg.txt"
file_path_neighbors = "neighbors_SD_full.txt"

S_names, D_names, S_coords, D_coords = SourceDetectorExtractor(file_path)
# Quick check
print("Sources:", len(S_names))
print("Detectors:", len(D_names))

# neighborfilegeneration()
S_dict, D_dict, neighbors = probcoordinates(file_path, file_path_neighbors)
#%%
bad_pairs = badpairsdetection(S_dict, D_dict, neighbors)

for s, d, dist in bad_pairs:
    status = "TOO SHORT" if dist < 25 else "TOO LONG"
    print(f"{s} ↔ {d} : {dist:.2f} mm ---> {status}")

#%%