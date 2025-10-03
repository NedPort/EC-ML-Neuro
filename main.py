#%%
import os
import re
import scipy.io as sio
import pandas as pd
import numpy as np

indir = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\mat\processed"

# Collect data by subject
subject_dict = {}

for fname in os.listdir(indir):
    if fname.endswith("_results.mat"):
        fpath = os.path.join(indir, fname)
        data = sio.loadmat(fpath)
        
        # Extract vectors
        to_restricted   = np.ravel(data['to_restricted'])
        from_restricted = np.ravel(data['from_restricted'])
        to_first14      = np.ravel(data['to_first14'])
        from_first14    = np.ravel(data['from_first14'])
        to_last14       = np.ravel(data['to_last14'])
        from_last14     = np.ravel(data['from_last14'])
        
        # Concatenate into one vector
        vec = np.concatenate([
            to_restricted, from_restricted,
            to_first14, from_first14,
            to_last14, from_last14
        ])
        
        # Determine modality
        if "hbo" in fname.lower() or "oxy" in fname.lower():
            modality = "hbo"
        elif "coe" in fname.lower():
            modality = "coe"
        else:
            modality = "unknown"
        
        # Extract subject_id (first 4–5 digit sequence, ignores trailing letters)
        match = re.search(r"\d{4,5}", fname)
        subject_id = match.group(0) if match else fname
        
        # Store vectors
        if subject_id not in subject_dict:
            subject_dict[subject_id] = {}
        subject_dict[subject_id][modality] = vec

# Build columns
channels = [f"ch{i}" for i in range(1, 47)]
base_cols = []
for ch in channels:
    base_cols += [f"{ch}_freq_to", f"{ch}_freq_from",
                  f"{ch}_period1_to", f"{ch}_period1_from",
                  f"{ch}_period3_to", f"{ch}_period3_from"]

colnames_hbo = [c + "_hbo" for c in base_cols]
colnames_coe = [c + "_coe" for c in base_cols]

# Build DataFrame
rows = []
subject_ids = []
for subj, mods in subject_dict.items():
    row = []
    row.extend(mods.get("hbo", [np.nan]*len(colnames_hbo)))
    row.extend(mods.get("coe", [np.nan]*len(colnames_coe)))
    rows.append(row)
    subject_ids.append(subj)

df = pd.DataFrame(rows, columns=colnames_hbo + colnames_coe)
df.insert(0, "subject_id", subject_ids)

# Merge with participant info
csv_path = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\BCBL_RS4_participant-info_rearranged.csv"
info_df = pd.read_csv(csv_path, header=None, names=["subject_id", "status"],
                      dtype={"subject_id": str, "status": "Int64"})
info_df["subject_id"] = info_df["subject_id"].astype(str)

df["subject_id"] = df["subject_id"].astype(str)
df = df.merge(info_df, on="subject_id", how="left")

# Add group column
df["group"] = df["status"].map({1: "bi", 2: "mono", 3: "mono"}).fillna("unknown")

# ✅ Subtract 6 from all numeric feature columns
numeric_cols = [c for c in df.columns if c not in ["subject_id", "status", "group"]]
df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce") - 6



# Save
out_path = os.path.join(indir, "subjects_connectivity_features_wide.csv")
df.to_csv(out_path, index=False)
print(f"✅ Saved wide-format dataset to {out_path}")

# %%
