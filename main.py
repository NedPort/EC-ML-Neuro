import os
import scipy.io as sio
import pandas as pd
import numpy as np

indir = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\mat\processed"

# Collect rows for all subjects
rows = []
subject_names = []

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
        
        # Concatenate into one row
        row = np.concatenate([
            to_restricted, from_restricted,
            to_first14, from_first14,
            to_last14, from_last14
        ])
        
        rows.append(row)
        subject_names.append(fname.replace("_results.mat", ""))

# Build column names
channels = [f"ch{i}" for i in range(1, 47)]

colnames = []
colnames += [f"{ch}_freq_to" for ch in channels]
colnames += [f"{ch}_freq_from" for ch in channels]
colnames += [f"{ch}_period1_to" for ch in channels]
colnames += [f"{ch}_period1_from" for ch in channels]
colnames += [f"{ch}_period3_to" for ch in channels]
colnames += [f"{ch}_period3_from" for ch in channels]

# Create DataFrame
df = pd.DataFrame(rows, columns=colnames)
df.insert(0, "subject", subject_names)

# --- Build subject_id from filename (first 4-digit token like 4216) ---
df["subject_id"] = df["subject"].str.extract(r'(?<!\d)(\d{4})(?!\d)').astype(str)

# --- Read participant info (ID, status) ---
csv_path = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\BCBL_RS4_participant-info_rearranged.csv"
info_df = pd.read_csv(csv_path, header=None, names=["subject_id", "status"],
                      dtype={"subject_id": str, "status": "Int64"})

# --- Merge on subject_id ---
df = df.merge(info_df, on="subject_id", how="left")

# Optional: quick sanity check
print("Unmatched after merge:", df["status"].isna().sum())
print(df.loc[df["status"].isna(), ["subject", "subject_id"]].head())

# --- Group label ---
df["group"] = df["status"].map({1: "mono", 2: "bi", 3: "other"}).fillna("unknown")

# --- Reorder columns (keep both names if you like) ---
lead_cols = ["subject", "subject_id", "status", "group"]
df = df[lead_cols + [c for c in df.columns if c not in lead_cols]]

# --- Numeric columns + save ---
df.iloc[:, 4:] = df.iloc[:, 4:].apply(pd.to_numeric, errors="coerce")
out_path = os.path.join(indir, "subjects_connectivity_features.csv")
if os.path.exists(out_path):
    try:
        os.remove(out_path)
    except PermissionError:
        out_path = os.path.join(indir, "subjects_connectivity_features_new.csv")
df.to_csv(out_path, index=False)
print(f"Saved to {out_path}")
