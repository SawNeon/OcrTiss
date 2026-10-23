"""Shared runtime setup for every entry point (API, scripts, tests).

OpenCV probes for an OpenCL device on first use in each thread and, on machines
without a usable GPU driver, that probe raises a Windows access violation —
harmless in the end, but it crashes the process under a fault handler and shows
up as noise in logs. The flag is thread-local, so disabling it per thread is not
enough: the runtime has to be turned off through the environment, before the
library is imported. The pipeline runs on CPU by design.
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")
os.environ.setdefault("OPENCV_OPENCL_DEVICE", "disabled")

import cv2

cv2.ocl.setUseOpenCL(False)
