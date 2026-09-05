#!/usr/bin/env python3
"""
Install or remove LockCrypt Windows right-click context menu entries.

Run as Administrator:
    python install_context_menu.py            # install
    python install_context_menu.py --remove   # remove
"""

import sys
import winreg
from pathlib import Path


APP_NAME = "LockCrypt"
HERE = Path(__file__).resolve().parent

# Accept an explicit exe path as the first positional argument, e.g.:
#   python install_context_menu.py "C:\Tools\LockCrypt.exe"
# Otherwise fall back to dist\LockCrypt.exe next to this script.
_explicit = next((Path(a) for a in sys.argv[1:] if not a.startswith("--") and a.endswith(".exe")), None)
_exe = _explicit if _explicit and _explicit.exists() else HERE / "dist" / "LockCrypt.exe"

_py  = Path(sys.executable)
_pyw = _py.parent / "pythonw.exe"
_runner = str(_pyw if _pyw.exists() else _py)
_script = str(HERE / "lockcrypt.py")

if _exe.exists():
    ENCRYPT_CMD = f'"{_exe}" "%1"'
    DECRYPT_CMD = f'"{_exe}" --decrypt "%1"'
    ICON        = str(_exe)
else:
    ENCRYPT_CMD = f'"{_runner}" "{_script}" "%1"'
    DECRYPT_CMD = f'"{_runner}" "{_script}" --decrypt "%1"'
    ICON        = _runner


# (registry key path under HKEY_CLASSES_ROOT, menu label or None, command or None)
# label=None  → this is a \command subkey; write the command value instead
# command=None → write ENCRYPT_CMD
_ENTRIES = [
    # All files — encrypt
    (r"*\shell\LockCrypt",                                  f"{APP_NAME} — Encrypt",         None),
    (r"*\shell\LockCrypt\command",                          None,                                  ENCRYPT_CMD),
    # Folders — encrypt
    (r"Directory\shell\LockCrypt",                          f"{APP_NAME} — Encrypt Folder",   None),
    (r"Directory\shell\LockCrypt\command",                  None,                                  ENCRYPT_CMD),
    # Folder background — encrypt
    (r"Directory\Background\shell\LockCrypt",               f"{APP_NAME} — Encrypt Folder",   None),
    (r"Directory\Background\shell\LockCrypt\command",       None,                                  ENCRYPT_CMD),
    # .7z files — decrypt (SystemFileAssociations works regardless of which app owns .7z)
    (r"SystemFileAssociations\.7z\shell\LockCrypt Decrypt", f"{APP_NAME} — Decrypt",          None),
    (r"SystemFileAssociations\.7z\shell\LockCrypt Decrypt\command", None,                          DECRYPT_CMD),
]


def _require_admin():
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("This script must be run as Administrator.")
        print("Right-click the script and choose 'Run as administrator'.")
        sys.exit(1)


def install():
    _require_admin()
    root = winreg.HKEY_CLASSES_ROOT
    for key_path, label, command in _ENTRIES:
        key = winreg.CreateKey(root, key_path)
        if label is not None:
            winreg.SetValueEx(key, "",     0, winreg.REG_SZ, label)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, ICON)
        else:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)

    print(f"{APP_NAME} context menu entries installed.")
    print(f"  Encrypt command : {ENCRYPT_CMD}")
    print(f"  Decrypt command : {DECRYPT_CMD}")
    print()
    print("  • Right-click any file or folder  →  LockCrypt — Encrypt")
    print("  • Right-click any .7z file        →  LockCrypt — Decrypt")


def remove():
    _require_admin()
    root = winreg.HKEY_CLASSES_ROOT
    for key_path, _, __ in reversed(_ENTRIES):
        try:
            winreg.DeleteKey(root, key_path)
        except FileNotFoundError:
            pass
    print(f"{APP_NAME} context menu entries removed.")


if __name__ == "__main__":
    if "--remove" in sys.argv or "--uninstall" in sys.argv:
        remove()
    else:
        install()
