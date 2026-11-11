# Sourced by the tool build scripts: the machine's paths from h3kit/env.py
# (local_paths.json or H3KIT_* environment variables override the defaults).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eval "$(cd "$ROOT" && python3 -c '
from h3kit import env
for k in ("EK", "EK_WIN", "DOTNET"):
    v = str(getattr(env, k)).replace("\x27", "\x27\\\x27\x27")
    print(f"{k}=\x27{v}\x27")
')"
