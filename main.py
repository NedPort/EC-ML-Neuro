

#%%
import os
import scipy.io as sio
import pandas as pd
import numpy as np

indir = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\mat\processed"
#%%
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
# restricted
colnames += [f"{ch}_freq_to" for ch in channels]
colnames += [f"{ch}_freq_from" for ch in channels]
# period1
colnames += [f"{ch}_period1_to" for ch in channels]
colnames += [f"{ch}_period1_from" for ch in channels]
# period3
colnames += [f"{ch}_period3_to" for ch in channels]
colnames += [f"{ch}_period3_from" for ch in channels]

# Create DataFrame
df = pd.DataFrame(rows, columns=colnames, index=subject_names)

# Save to CSV
out_csv = os.path.join(indir, "subjects_connectivity_features.csv")
df.to_csv(out_csv)

print(f"Saved DataFrame to {out_csv}")

# %%
