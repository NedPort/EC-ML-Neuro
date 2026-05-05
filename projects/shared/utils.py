import numpy as np
import torch
from tqdm import tqdm
from torch import nn
from statsmodels.tsa.api import VAR
from numpy.linalg import inv, norm, eigvals
from scipy.signal import detrend
import os, glob, re
import scipy.io


# -----------------------------
# Helpers
# -----------------------------
def _preprocess_window(window_data):
    """Linear detrend + z-score, per channel."""
    X = detrend(window_data, axis=0, type="linear")
    mu = X.mean(axis=0, keepdims=True)
    sd = X.std(axis=0, keepdims=True)
    return (X - mu) / (sd + 1e-8)


def _spectral_radius_from_coefs(coefs):
    """Companion-matrix spectral radius (<1 => stable)."""
    p, C, _ = coefs.shape
    top = np.concatenate([coefs[k] for k in range(p)], axis=1)
    if p == 1:
        Acomp = top
    else:
        I = np.eye(C * (p - 1))
        Z = np.zeros((C * (p - 1), C))
        bottom = np.hstack([I, Z])
        Acomp = np.vstack([top, bottom])
    return np.max(np.abs(eigvals(Acomp)))


def fit_var(window_data, order, min_order=4, preprocess=True):
    """
    Fit VAR(order) on [T,C] window; try lower orders if unstable.
    Returns: coefs [p,C,C], Sigma_u [C,C], is_stable (bool), used_order (int)
    """
    X = _preprocess_window(window_data) if preprocess else np.asarray(window_data)
    used_order = int(order)
    last_res = None

    while used_order >= int(min_order):
        res = VAR(X).fit(used_order, trend="n")  # after z-score, no intercept
        # statsmodels' is_stable() may vary by version; verify with spectral radius too
        try:
            sm_stable = bool(res.is_stable())
        except Exception:
            sm_stable = True
        rho = _spectral_radius_from_coefs(res.coefs)
        is_stable = sm_stable and (rho < 0.999)

        if is_stable:
            return res.coefs, res.sigma_u, True, used_order

        last_res = res
        used_order -= 2  # fallback step

    # If none stable, return the last fit (flagged as unstable)
    res = last_res if last_res is not None else VAR(X).fit(int(min_order), trend="n")
    return res.coefs, res.sigma_u, False, int(min_order)


def A_of_f(coefs, f_hz, fs):
    """
    A(f) = I - sum_{k=1..p} A_k * exp(-j 2π f * k / fs)
    coefs: [p, C, C]
    """
    p, C, _ = coefs.shape
    z = np.exp(-1j * 2.0 * np.pi * f_hz * np.arange(1, p + 1) / fs)  # length p
    Af = np.eye(C, dtype=np.complex128)
    for k in range(p):
        Af -= coefs[k] * z[k]
    return Af  # complex [C,C]


def H_of_f(coefs, f_hz, fs):
    """Transfer function H(f) = A(f)^{-1}."""
    Af = A_of_f(coefs, f_hz, fs)
    return inv(Af)


def pdc_from_A(Af):
    """
    Column-normalized PDC:
    PDC_{i->j}(f) = |A_{j,i}(f)| / sqrt( sum_k |A_{k,i}(f)|^2 ).
    Returns [C,C] with i->j at [j,i].
    """
    C = Af.shape[0]
    out = np.zeros((C, C), dtype=np.float64)
    for i in range(C):  # source (column)
        col = Af[:, i]
        denom = norm(col)
        if denom != 0:
            out[:, i] = np.abs(col) / denom
    return out


def gpdc_from_A(Af, sigma_u):
    """
    GPDC: whiten columns by diag(Sigma_u)^{-1/2}, then column-normalize.
    Returns [C,C] with i->j at [j,i].
    """
    C = Af.shape[0]
    stds = np.sqrt(np.clip(np.diag(sigma_u), 1e-12, None))
    Afw = Af.copy()
    for i in range(C):
        Afw[:, i] = Af[:, i] / stds[i]
    out = np.zeros((C, C), dtype=np.float64)
    for i in range(C):
        denom = norm(Afw[:, i])
        if denom != 0:
            out[:, i] = np.abs(Afw[:, i]) / denom
    return out


# -----------------------------
# Main runner
# -----------------------------
def compute_multi_freq_gpdc_continuous(
    X,
    fs=100.0,
    window_size=3000,  # 30 s windows (set 6000 for 60 s)
    order=12,  # target order; fallback tries lower if unstable
    overlap=0.5,  # 50% overlap -> step = 15 s
    freqs=np.arange(0.10, 0.30, 0.005),
    use_gpdc=True,
    save_path="gpdc_multi_freq_continuous.npy",
):
    """
    X: numpy array [T, C] (continuous data)
    Returns: gpdc_all [W, F, C, C], stable_flags [W]
    """
    X = np.asarray(X)
    if X.ndim != 2:
        X = np.squeeze(X)
    if X.shape[0] < X.shape[1]:
        X = X.T  # ensure [T,C]

    T, C = X.shape
    step = int(window_size * (1.0 - overlap))
    if step <= 0:
        raise ValueError("overlap must be < 1.0")
    n_win = (T - window_size) // step + 1
    if n_win <= 0:
        raise ValueError("window_size too large for the series length")

    F = len(freqs)
    gpdc_all = np.zeros((n_win, F, C, C), dtype=np.float32)
    stable_flags = np.zeros(n_win, dtype=bool)

    for wi in tqdm(range(n_win), desc="Windows"):
        s = wi * step
        e = s + window_size
        wdat = X[s:e, :]

        coefs, sigma_u, is_stable, used_p = fit_var(
            wdat, order=order, min_order=4, preprocess=True
        )
        stable_flags[wi] = is_stable

        for fi, f in enumerate(freqs):
            Af = A_of_f(coefs, f_hz=f, fs=fs)
            M = gpdc_from_A(Af, sigma_u) if use_gpdc else pdc_from_A(Af)
            gpdc_all[wi, fi] = M.astype(np.float32)

    np.save(save_path, gpdc_all)
    return gpdc_all, stable_flags


# -----------------------------
# Preprocess
# -----------------------------
def _preprocess_window(window_data):
    # linear detrend + z-score per channel
    X = detrend(window_data, axis=0, type="linear")
    mu = X.mean(axis=0, keepdims=True)
    sd = X.std(axis=0, keepdims=True)
    return (X - mu) / (sd + 1e-8)


# -----------------------------
# VAR helpers
# -----------------------------
def _build_var_design(X, p):
    """
    X: [T, C] standardized window
    Returns:
      Y: [(T-p), C]
      Phi: [(T-p), C*p]  (lags stacked as [x_{t-1}, x_{t-2}, ..., x_{t-p}])
    """
    T, C = X.shape
    Y = X[p:, :]
    Phi = np.column_stack([X[p - k - 1 : T - k - 1, :] for k in range(p)])
    return Y, Phi


def _spectral_radius_from_coefs(coefs):
    """Companion-matrix spectral radius; <1 => stable."""
    p, C, _ = coefs.shape
    top = np.concatenate([coefs[k] for k in range(p)], axis=1)  # [C, C*p]
    if p == 1:
        Acomp = top
    else:
        I = np.eye(C * (p - 1))
        Z = np.zeros((C * (p - 1), C))
        Acomp = np.vstack([top, np.hstack([I, Z])])
    return np.max(np.abs(eigvals(Acomp)))


def fit_var_ridge(
    window_data, order, lam=1e-2, preprocess=True, enforce_stability=True
):
    """
    Ridge-regularized VAR(p) via closed-form ridge per equation.
    Returns: coefs [p,C,C], Sigma_u [C,C], is_stable (bool), used_order (int), rho (float)
    """
    X = _preprocess_window(window_data) if preprocess else np.asarray(window_data)
    T, C = X.shape
    p = int(order)

    # design
    Y, Phi = _build_var_design(X, p)  # Y: [N,C], Phi: [N,Cp]
    N = Y.shape[0]
    # ridge: (Phi^T Phi + lam I)^{-1} Phi^T Y
    I = np.eye(Phi.shape[1])
    K = np.linalg.solve(Phi.T @ Phi + lam * I, Phi.T @ Y)  # [C*p, C]

    # reshape into A_1..A_p (each [C,C])
    coefs = np.stack([K[c * C : (c + 1) * C, :].T for c in range(p)], axis=0)  # [p,C,C]

    # residuals and covariance
    Y_hat = Phi @ K
    E = Y - Y_hat
    Sigma_u = (E.T @ E) / max(N - C * p, 1)

    # stability check
    rho = _spectral_radius_from_coefs(coefs)
    is_stable = rho < 1.0

    # optional stability projection (scale all A_k by alpha)
    if enforce_stability and not is_stable and rho > 0:
        alpha = 0.98 / float(rho)  # pull just inside unit circle
        coefs = coefs * alpha
        rho = _spectral_radius_from_coefs(coefs)
        is_stable = rho < 1.0

    return coefs, Sigma_u, bool(is_stable), p, float(rho)


# -----------------------------
# Frequency-domain pieces
# -----------------------------
def A_of_f(coefs, f_hz, fs):
    """
    A(f) = I - sum_{k=1..p} A_k * exp(-j 2π f * k / fs)
    coefs: [p, C, C]
    """
    p, C, _ = coefs.shape
    z = np.exp(-1j * 2.0 * np.pi * f_hz * np.arange(1, p + 1) / fs)  # length p
    Af = np.eye(C, dtype=np.complex128)
    for k in range(p):
        Af -= coefs[k] * z[k]
    return Af


def pdc_from_A(Af):
    """
    Column-normalized PDC:
    PDC_{i->j}(f) = |A_{j,i}(f)| / sqrt( sum_k |A_{k,i}(f)|^2 ).
    Returns [C,C] with i->j at [j,i].
    """
    C = Af.shape[0]
    out = np.zeros((C, C), dtype=np.float64)
    for i in range(C):  # source (column)
        col = Af[:, i]
        denom = norm(col)
        if denom != 0:
            out[:, i] = np.abs(col) / denom
    return out


def gpdc_from_A(Af, sigma_u):
    """
    GPDC: whiten columns by diag(Sigma_u)^{-1/2}, then column-normalize.
    Returns [C,C] with i->j at [j,i].
    """
    C = Af.shape[0]
    stds = np.sqrt(np.clip(np.diag(sigma_u), 1e-12, None))
    Afw = Af.copy()
    for i in range(C):
        Afw[:, i] = Af[:, i] / stds[i]
    out = np.zeros((C, C), dtype=np.float64)
    for i in range(C):
        denom = norm(Afw[:, i])
        if denom != 0:
            out[:, i] = np.abs(Afw[:, i]) / denom
    return out


# -----------------------------
# Main runner (unchanged API)
# -----------------------------
def compute_multi_freq_gpdc_continuous(
    X,
    fs=100.0,
    window_size=6000,  # try 60 s windows
    order=8,  # start lower; ridge helps anyway
    overlap=0.5,  # 50% overlap
    freqs=np.arange(0.10, 0.20, 0.01),
    use_gpdc=True,
    save_path="gpdc_multi_freq_continuous.npy",
    lam=1e-2,  # ridge strength
    enforce_stability=True,  # project roots inside unit circle if needed
):
    """
    X: numpy array [T, C] (continuous data)
    Returns: gpdc_all [W, F, C, C], stable_flags [W]
    """
    X = np.asarray(X)
    if X.ndim != 2:
        X = np.squeeze(X)
    if X.shape[0] < X.shape[1]:
        X = X.T  # ensure [T,C]

    T, C = X.shape
    step = int(window_size * (1.0 - overlap))
    if step <= 0:
        raise ValueError("overlap must be < 1.0")
    n_win = (T - window_size) // step + 1
    if n_win <= 0:
        raise ValueError("window_size too large for the series length")

    F = len(freqs)
    gpdc_all = np.zeros((n_win, F, C, C), dtype=np.float32)
    stable_flags = np.zeros(n_win, dtype=bool)

    for wi in tqdm(range(n_win), desc="Windows"):
        s = wi * step
        e = s + window_size
        wdat = X[s:e, :]

        coefs, sigma_u, is_stable, used_p, rho = fit_var_ridge(
            wdat,
            order=order,
            lam=lam,
            preprocess=True,
            enforce_stability=enforce_stability,
        )
        stable_flags[wi] = is_stable

        for fi, f in enumerate(freqs):
            Af = A_of_f(coefs, f_hz=f, fs=fs)
            M = gpdc_from_A(Af, sigma_u) if use_gpdc else pdc_from_A(Af)
            gpdc_all[wi, fi] = M.astype(np.float32)

    np.save(save_path, gpdc_all)
    return gpdc_all, stable_flags


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
