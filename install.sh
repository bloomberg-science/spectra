#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

set -e

# Use sudo only if not root
if [ "$(id -u)" -ne 0 ]; then SUDO=sudo; else SUDO=""; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/analysisenv"

echo "============================================"
echo "  SPECTRA — Installation"
echo "============================================"
echo ""

# ─── 0. Initialize Submodules ────────────────────────────────────────────────

echo "[0/5] Initializing submodules..."

if [ -d "$SCRIPT_DIR/.git" ]; then
    git -C "$SCRIPT_DIR" submodule update --init --recursive
    echo "  Submodules initialized."
else
    echo "  Not a git repo — skipping submodule init."
    echo "  If you cloned without --recurse-submodules, run:"
    echo "    git submodule update --init --recursive"
fi

echo ""

# ─── 0.5. Download Package Sources ───────────────────────────────────────────

echo "[0.5/5] Downloading package sources..."

TESTSUITE_DIR="$SCRIPT_DIR/testsuite"

# Apache httpd 2.4.64 (not a submodule — downloaded as tarball)
if [ ! -d "$TESTSUITE_DIR/apache" ]; then
    echo "  Downloading Apache httpd 2.4.64..."
    wget -q -O /tmp/httpd-2.4.64.tar.gz https://archive.apache.org/dist/httpd/httpd-2.4.64.tar.gz
    tar -xzf /tmp/httpd-2.4.64.tar.gz -C "$TESTSUITE_DIR"
    mv "$TESTSUITE_DIR/httpd-2.4.64" "$TESTSUITE_DIR/apache"
    rm -f /tmp/httpd-2.4.64.tar.gz
    echo "  Apache httpd 2.4.64 extracted."
else
    echo "  Apache source already exists. Skipping."
fi

echo ""

# ─── 1. System Dependencies ─────────────────────────────────────────────────

echo "[1/5] Installing system dependencies..."

$SUDO apt-get update -qq

# Python build deps
$SUDO apt-get install -y -qq python3 python3-venv python3-pip python3-dev build-essential

# SAFER deps
$SUDO apt-get install -y -qq ocaml camlp4-extra camlp4 exuberant-ctags libcapstone-dev

# Ghidra 11.4 requires Java 21+
if ! command -v java &>/dev/null || ! java -version 2>&1 | grep -q "\"2[1-9]\|\"[3-9][0-9]"; then
    $SUDO apt-get install -y -qq openjdk-21-jdk-headless
fi

echo "  System dependencies installed."
echo ""

# ─── 2. Python Virtual Environment ──────────────────────────────────────────

echo "[2/5] Setting up Python virtual environment..."

if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment already exists at $VENV_DIR"
else
    python3 -m venv "$VENV_DIR"
    echo "  Created virtual environment at $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q

echo "  Python dependencies installed."
echo ""

# ─── 3. SAFER Backend ───────────────────────────────────────────────────────

echo "[3/5] Installing SAFER backend..."

SAFER_DIR="$SCRIPT_DIR/bin_analysis_tools/safer"

cd "$SAFER_DIR"
bash install.sh
cd "$SCRIPT_DIR"
echo "  SAFER installed."

echo ""

# ─── 4. Ghidra ──────────────────────────────────────────────────────────────

echo "[4/5] Installing Ghidra..."

GHIDRA_DIR="$SCRIPT_DIR/bin_analysis_tools/ghidra_projects"

if [ -d "$GHIDRA_DIR/ghidra" ]; then
    echo "  Ghidra already installed (ghidra_projects/ghidra/ exists). Skipping."
else
    cd "$GHIDRA_DIR"
    bash install.sh
    cd "$SCRIPT_DIR"
    echo "  Ghidra installed."
fi

echo ""

# ─── Summary ────────────────────────────────────────────────────────────────

echo "============================================"
echo "  Installation Complete"
echo "============================================"
echo ""
echo "  Installed:"
echo "    - Python venv:  $VENV_DIR"
echo "    - SAFER:        $SAFER_DIR/apps/"
echo "    - Ghidra:       $GHIDRA_DIR/ghidra/"
echo "    - Angr:         via pip (in venv)"
echo ""
echo "  Not installed (commercial — manual setup required):"
echo "    - IDA Pro:      set IDA_PATH env variable"
echo "    - Binary Ninja: set BNINJA_PATH env variable"
echo ""
echo "  To activate:"
echo "    source $VENV_DIR/bin/activate"
echo ""
echo "  Quick test:"
echo "    python3 gen_syscall.py safer /bin/ls"
echo ""
