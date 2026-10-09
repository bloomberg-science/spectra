#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_11.4_build/ghidra_11.4_PUBLIC_20250620.zip
unzip ghidra_11.4_PUBLIC_20250620.zip
mv ghidra_11.4_PUBLIC ghidra
rm ghidra_11.4_PUBLIC_20250620.zip
