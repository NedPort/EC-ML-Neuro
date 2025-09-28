#%%
import os
import re
import scipy.io as sio
import pandas as pd
import numpy as np

#%%
# Directory
indir = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\mat\processed"

# Initialize storage
subject_data = {}

# Loop over .mat files
for file in os.listdir(indir):
    if file.endswith(".mat"):
        filepath = os.path.join(indir, file)

        # Extract subject number from filename (digits after SL_)
        match = re.search(r"SL_(\d+)", file)
        if not match:
            continue
        subject = match.group(1)

        # Decide hbo/coe
        if "oxy" in file.lower():
            suffix1 = "_hbo"
        elif "coe" in file.lower():
            suffix1 = "_coe"
        else:
            continue

        # Decide to/from
        if file.lower().endswith("_to.mat"):
            suffix2 = "_to"
        elif file.lower().endswith("_from.mat"):
            suffix2 = "_from"
        else:
            continue

        # Load .mat file
        mat = sio.loadmat(filepath)

        # Extract first non-meta key
        arr = None
        for key in mat.keys():
            if not key.startswith("__"):
                arr = mat[key]
                break
        if arr is None:
            continue

        arr = np.array(arr).flatten()

        # Create feature dict
        row = {}
        for i, val in enumerate(arr[:46]):  # 46 channels
            row[f"Ch{i+1}{suffix1}{suffix2}"] = val

        # Add to subject dictionary
        if subject not in subject_data:
            subject_data[subject] = {}
        subject_data[subject].update(row)

# Build DataFrame
df = pd.DataFrame.from_dict(subject_data, orient="index").reset_index()
df.rename(columns={"index": "subject"}, inplace=True)

print(df.head())

# %%

# Path to your CSV
csv_path = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\BCBL_RS4_participant-info_rearranged.csv"

#%%
# Read the CSV
info_df = pd.read_csv(csv_path, header=None)  # no headers in your screenshot
info_df.columns = ["subject", "status"]      # rename columns

#%%
# Make sure subject is string in both
df["subject"] = df["subject"].astype(str)
info_df["subject"] = info_df["subject"].astype(str)

# Merge
df = df.merge(info_df, on="subject", how="left")

# Reorder so status is right after subject
cols = ["subject", "status"] + [c for c in df.columns if c not in ["subject", "status"]]
df = df[cols]

#%%

# Add new column based on status
df["group"] = np.where(df["status"] == 1, "bi", "mono")

#%%
# Reorder so status is right after subject
cols = ["subject", "status", "group"] + [c for c in df.columns if c not in ["subject", "status"]]
df = df[cols]
df


# %%
import os
# Convert all columns after the first 3 to numeric (if possible)
df.iloc[:, 3:] = df.iloc[:, 3:].apply(pd.to_numeric, errors='coerce')

df.iloc[:,3:] = df.iloc[:, 3:] - 6
out_path = os.path.join(indir, "fnirs_statistics.csv")
df.to_csv(out_path, index=False)

print(f"Saved file to: {out_path}")

# %%
