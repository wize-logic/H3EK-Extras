# Tools

Native helpers the Python code drives. Both build scripts read the machine's paths from `h3kit/env.py` (through `tools/paths.sh`).

- `mbedit/`: the tag editor every build uses. `mbedit.cs` runs scripted tag edits through the Editing Kit's ManagedBlam; `mbedit/build.sh` builds it into `H3EK\work\mbedit.exe`. `dump_tag.ps1` prints a tag's fields from PowerShell.
- `hgport/`: moves compiled tags, with everything they need, from one built map into another. It is Assembly's Blamite library as a console tool; `h3kit/donor.py` uses it for donor vehicles. `hgport/build.sh` builds it (it needs the .NET SDK).

What each command does, with the script language and the logs: [docs/tools.md](../docs/tools.md).

## Licence

`hgport/vendor/` is a copy of the Blamite library and the Halo 3 plugins from [Assembly](https://github.com/XboxChaos/Assembly), under the GNU GPL v3 (`hgport/vendor/LICENSE-Assembly.txt`). `hgport` links it, so the GPL v3 covers `hgport` as a whole.
