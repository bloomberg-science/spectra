# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

def remove_suffix(s: str, suf: str) -> str:
    return s[:-len(suf)] if suf and s.endswith(suf) else s


def split_commas_or_string(s: str):
    if ',' not in s:
        return [s]
    parts = [p.strip() for p in s.split(',') if p.strip()]
    return parts if len(parts) > 1 else [s]
