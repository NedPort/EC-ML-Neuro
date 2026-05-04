import numpy as np
# ---------------------------
# Read file
# ---------
def SourceDetectorExtractor(file_path):
    S_names, D_names = [], []
    S_coords, D_coords = [], []

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()

            if not line or ":" not in line:
                continue

            name, values = line.split(":")
            parts = values.strip().split()

            # Ensure it has x y z
            if len(parts) < 3:
                continue

            x, y, z = map(float, parts[:3])

            if name.startswith("s"):
                S_names.append(name)
                S_coords.append([x, y, z])

            elif name.startswith("d"):
                D_names.append(name)
                D_coords.append([x, y, z])

    # Convert to numpy
    S_coords = np.array(S_coords)
    D_coords = np.array(D_coords)

    return S_names, D_names, S_coords, D_coords

###  We can define this function to generate the neighbors_SD.txt file 
# with the specified content. This way, we can ensure that the file is 
# created correctly before we attempt to read it in our main code.  
#   
def neighborfilegeneration():
    neighbors_text = """s1  : d1, d2, d3, d4
s2  : d1, d5, d11, d13
s3  : d2, d6, d12, d14
s4  : d2, d3, d10, d12
s5  : d2, d4, d14, d16
s6  : d1, d3, d9, d11
s7  : d1, d4, d13, d15
s8  : d3, d7, d9, d10
s9  : d4, d8, d15, d16
s10 : d8, d17, d18
s11 : d8, d16, d17, d20
s12 : d8, d15, d18, d19
s13 : d13, d15, d19, d21
s14 : d14, d16, d20, d22
s15 : d5, d13, d21
s16 : d6, d14, d22
s17 : d9, d11
s18 : d12, d10
s19 : d7, d9
s20 : d7, d10
s21 : d5, d11
s22 : d6, d12
"""

    with open("neighbors_SD.txt", "w") as f:
        f.write(neighbors_text)

    print("Saved as neighbors_SD.txt")


# ---------------------------
# 1. Load coordinates (probe_reg.txt)
# ---------------------------
def probcoordinates(file_path, file_path_neighbors):
    S_dict = {}
    D_dict = {}

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue

            name, values = line.split(":")
            parts = values.strip().split()

            if len(parts) < 3:
                continue

            coord = np.array(list(map(float, parts[:3])))

            if name.startswith("s"):
                S_dict[name] = coord
            elif name.startswith("d"):
                D_dict[name] = coord

# ---------------------------
# 2. Load neighbors (neighbors_SD.txt)
# ---------------------------
    neighbors = {}

    with open(file_path_neighbors, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            name, rest = line.split(":")
            detectors = [d.strip() for d in rest.split(",")]

            neighbors[name.strip()] = detectors

# ---------------------------
# 3. Compute distances
# ---------------------------
    print("\nDistances per source:\n")

    for s_name, d_list in neighbors.items():
        s_coord = S_dict[s_name]

        print(f"{s_name}:")

        for d_name in d_list:
            d_coord = D_dict[d_name]
            dist = np.linalg.norm(s_coord - d_coord)

            print(f"  {s_name} ↔ {d_name} : {dist:.2f} mm")

        print()
    return S_dict,D_dict,neighbors


# ---------------------------
# Parameters (based on paper)
# ---------------------------
def badpairsdetection(S_dict, D_dict, neighbors):
    LOW = 25
    HIGH = 35

    bad_pairs = []

    for s_name, d_list in neighbors.items():
        s_coord = S_dict[s_name]

        for d_name in d_list:
            d_coord = D_dict[d_name]
            dist = np.linalg.norm(s_coord - d_coord)

            if dist < LOW or dist > HIGH:
                bad_pairs.append((s_name, d_name, dist))

    return bad_pairs
