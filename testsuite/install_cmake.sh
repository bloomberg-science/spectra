#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


# Download
wget https://github.com/Kitware/CMake/releases/download/v3.24.0/cmake-3.24.0-linux-x86_64.tar.gz

# Extract
tar -xzf cmake-3.24.0-linux-x86_64.tar.gz

# Use directly or install to a system path
cd cmake-3.24.0-linux-x86_64
sudo cp -r bin/ share/ man/ /usr/local/

