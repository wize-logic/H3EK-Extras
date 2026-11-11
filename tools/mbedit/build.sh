#!/bin/bash
# Builds mbedit.exe (the tag editor every build uses) into H3EK\work, next to a
# copy of the kit's ManagedBlam.dll, with the .NET Framework 4 compiler that
# ships with Windows. Compiles to a scratch name first, so a failed compile
# leaves a working mbedit.exe in place.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../paths.sh"
CSC=/mnt/c/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe
mkdir -p "$EK/work"
cp "$EK/bin/ManagedBlam.dll" "$EK/work/"
cp "$HERE/mbedit.cs" "$EK/work/"
cd "$EK/work"
"$CSC" /nologo /platform:x64 /out:mbedit_new.exe "/r:$EK_WIN\\bin\\ManagedBlam.dll" mbedit.cs
mv -f mbedit_new.exe mbedit.exe
echo "built: $EK/work/mbedit.exe"
