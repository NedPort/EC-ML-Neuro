import numpy as np
import torch
from tqdm import tqdm
from torch import nn
from statsmodels.tsa.api import VAR
from numpy.linalg import inv, norm, eigvals
from scipy.signal import detrend
import os, glob, re
import scipy.io
from shared.utils import compute_multi_freq_gpdc_continuous
from config import RAW_DIR, PROCESSED_DIR



os.makedirs(PROCESSED_DIR, exist_ok=True)

files = sorted(glob.glob(os.path.join(RAW_DIR, "Filtered_*.mat")))

for fpath in files:
    fname = os.path.basename(fpath)
    m = re.search(r"S(\d+)", fname, flags=re.IGNORECASE)
    sid = f"S{m.group(1)}" if m else os.path.splitext(fname)[0]

    
    data = scipy.io.loadmat(fpath)
    HbO_filtered = data["HbO_filtered"]  # shape [T, C]
    if HbO_filtered.shape[0] < HbO_filtered.shape[1]:
        HbO_filtered = HbO_filtered.T  # ensure [T, C]

    # per-subject save path for GPDC
    save_path = os.path.join(PROCESSED_DIR, f"{sid}_gpdc_30s_p12.npy")

    gpdc, stable = compute_multi_freq_gpdc_continuous(
        X=HbO_filtered,
        fs=100.0,
        window_size=3000,  # 30 s
        order=12,
        overlap=0.5,  # adjust if needed
        freqs=np.arange(0.10, 0.20, 0.01),
        use_gpdc=True,
        save_path=save_path,
    )

    # save stability flags too
    np.save(os.path.join(PROCESSED_DIR, f"{sid}_stable.npy"), stable)
    print(f"{sid}: GPDC {gpdc.shape} | stable {stable.sum()}/{len(stable)} saved.")
