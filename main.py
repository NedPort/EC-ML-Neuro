#%%
!pip install statsmodels
import numpy as np
import torch
from tqdm import tqdm
from torch import nn
from statsmodels.tsa.api import VAR
from numpy.linalg import inv
from numpy.linalg import inv, norm, eigvals
from scipy.signal import detrend
import numpy as np
from statsmodels.tsa.api import VAR
from tqdm import tqdm