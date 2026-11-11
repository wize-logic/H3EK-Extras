#!/bin/bash
# Copies tools/hgport to H3EK\work\hgport and builds hgport.exe there (Windows .NET SDK).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../paths.sh"
DST="$EK/work/hgport"
mkdir -p "$DST"
rm -rf "$DST/vendor" "$DST/Program.cs" "$DST/hgport.csproj"
cp -r "$HERE/vendor" "$HERE/Program.cs" "$HERE/hgport.csproj" "$DST/"
cd "$DST"
"$DOTNET" build hgport.csproj -c Release -nologo -v q "$@"
echo "built: $DST/bin/hgport.exe"
