# Requirements

## Architecture

- **Target architecture:** x86-64 (AMD64)

## Hardware Requirements

- **CPU:** x86-64 processor (Intel or AMD)
- **RAM:** 32 GB minimum (recommended); heavyweight packages (mysql, postgresql, bmq) may require more than 30 GB
- **Disk space:** 100 GB free (the built Docker image is approximately 15 GB; additional space is needed during the build for compiling evaluation packages)
- **No non-commodity peripherals required**

## Software Requirements

- **Host OS:** Linux (tested on Ubuntu 22.04 LTS)
- **Docker:** Version 20.10 or later
- **Network:** Stable internet connection during the Docker build (to download dependencies, clone repositories, and install packages)

## Machine-Readable Dependency Files

- [`Dockerfile`](Dockerfile) — Complete build specification for the evaluation environment
- [`requirements.txt`](requirements.txt) — Python package dependencies
- [`install.sh`](install.sh) — Automated setup script for analysis tools (SAFER, Ghidra, Python venv)

## Estimated Build Time

The Docker image build takes approximately **3 hours**, depending on network speed and CPU cores. This includes downloading all system dependencies, compiling 11 evaluation packages from source, and installing analysis tools.
