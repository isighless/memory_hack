#!/usr/bin/env python3
"""
Local installer for memory_hack with sibling mem_edit checkout.

Assumptions
- This script lives inside the local memory_hack repo root.
- A sibling folder ../mem_edit exists and you want to use it directly.
- No GitHub downloads. No PyPI installs beyond requirements.txt.
- Service install is optional.

Usage
  python install_local.py install            # venv + run scripts
  python install_local.py uninstall          # remove venv + run scripts (keeps repo)
  python install_local.py service install    # install and start service
  python install_local.py service remove     # stop and remove service
  python install_local.py verify             # quick sanity checks

Windows service notes
- Requires nssm.exe already available. Provide path with --nssm "C:\\path\\nssm.exe"
  or put nssm.exe on PATH.

Linux service notes
- Writes /etc/systemd/system/memory_hack.service and enables/starts it.
- Requires sudo for service operations.

Run script behavior
- Scripts set PYTHONPATH to include the sibling ../mem_edit so packaging is not required.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

IS_WIN = platform.system().lower().startswith("win")
IS_LINUX = platform.system().lower() == "linux"

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / "venv"
MEM_EDIT_DIR = (REPO_ROOT / ".." / "mem_edit").resolve()
REQS_FILE = REPO_ROOT / "app" / "patches" / "requirements.txt"
ONSEN_ZIP = REPO_ROOT / "app" / "resources" / "static" / "onsen.zip"
STATIC_DIR = REPO_ROOT / "app" / "resources" / "static"

SERVICE_NAME = "memory_hack"
SYSTEMD_UNIT = f"/etc/systemd/system/{SERVICE_NAME}.service"

def run(cmd, check=True, env=None):
    print(f"$ {' '.join(map(str, cmd))}")
    return subprocess.run(cmd, check=check, env=env)

def ensure_venv():
    if not VENV_DIR.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    py = venv_python()
    # Upgrade pip+wheel for reliability
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel"])
    # Install repo requirements
    if REQS_FILE.exists():
        run([str(py), "-m", "pip", "install", "-r", str(REQS_FILE)])
    else:
        print("requirements.txt not found; continuing")

def venv_python():
    return VENV_DIR / ("Scripts/python.exe" if IS_WIN else "bin/python")

def venv_pip():
    return VENV_DIR / ("Scripts/pip.exe" if IS_WIN else "bin/pip")

def create_run_scripts():
    py_path = venv_python()
    mem_hack_entry = REPO_ROOT / "memory_hack.py"  # keep original entry point
    if not mem_hack_entry.exists():
        # Fallback if entry point differs; use app main if present
        app_main = REPO_ROOT / "app" / "memory_hack.py"
        mem_hack_entry = app_main if app_main.exists() else REPO_ROOT / "memory_hack.py"

    # Run script content uses PYTHONPATH to point to mem_edit sibling
    sh = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -e
        REPO_ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
        VENV="${{REPO_ROOT}}/venv/bin/python"
        export PYTHONPATH="${{PYTHONPATH}}:{MEM_EDIT_DIR}"
        exec "${{VENV}}" "{mem_hack_entry}"
    """)
    bat = textwrap.dedent(f"""\
        @echo off
        setlocal
        set REPO_ROOT=%~dp0
        set REPO_ROOT=%REPO_ROOT:~0,-1%
        set VENV=%REPO_ROOT%\\venv\\Scripts\\python.exe
        set PYTHONPATH=%PYTHONPATH%;{MEM_EDIT_DIR}
        "%VENV%" "{mem_hack_entry}"
    """)

    (REPO_ROOT / "run.sh").write_text(sh, encoding="utf-8")
    os.chmod(REPO_ROOT / "run.sh", 0o755)
    (REPO_ROOT / "run.bat").write_text(bat, encoding="utf-8")

def extract_onsen():
    if ONSEN_ZIP.exists():
        import zipfile
        with zipfile.ZipFile(ONSEN_ZIP, "r") as z:
            z.extractall(STATIC_DIR)
        print("Extracted onsen.zip")
    else:
        print("onsen.zip not present; skipping extract")

def install():
    require_local_layout()
    ensure_venv()
    create_run_scripts()
    extract_onsen()
    print("Install complete.")

def uninstall():
    # Do not delete repo files. Only local artifacts.
    for p in [VENV_DIR, REPO_ROOT / "run.sh", REPO_ROOT / "run.bat"]:
        if isinstance(p, Path) and p.is_dir():
            print(f"Removing {p}")
            shutil.rmtree(p, ignore_errors=True)
        elif Path(p).exists():
            print(f"Removing {p}")
            Path(p).unlink()
    print("Uninstall complete.")

def require_local_layout():
    assert MEM_EDIT_DIR.exists(), f"Expected sibling mem_edit at {MEM_EDIT_DIR}"
    assert (REPO_ROOT / "app").exists(), "Expected app/ in memory_hack repo"

# -------- services --------

def service_install_linux():
    run_path = (REPO_ROOT / "run.sh").resolve()
    unit = textwrap.dedent(f"""\
        [Unit]
        Description=memory_hack local
        After=network.target

        [Service]
        Type=simple
        WorkingDirectory={REPO_ROOT}
        ExecStart={run_path}
        Restart=on-failure
        Environment=PYTHONUNBUFFERED=1

        [Install]
        WantedBy=multi-user.target
    """)
    sudo_write(SYSTEMD_UNIT, unit)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", SERVICE_NAME])
    run(["systemctl", "start", SERVICE_NAME])
    print("Linux service installed and started.")

def service_remove_linux():
    run(["systemctl", "stop", SERVICE_NAME], check=False)
    run(["systemctl", "disable", SERVICE_NAME], check=False)
    if os.path.exists(SYSTEMD_UNIT):
        sudo_rm(SYSTEMD_UNIT)
        run(["systemctl", "daemon-reload"])
    print("Linux service removed.")

def sudo_write(path, content):
    tmp = REPO_ROOT / ".tmp_unit"
    tmp.write_text(content, encoding="utf-8")
    try:
        run(["sudo", "mv", str(tmp), path])
        run(["sudo", "chmod", "644", path])
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

def sudo_rm(path):
    run(["sudo", "rm", "-f", path])

def service_install_windows(nssm_path):
    if not nssm_path:
        # try on PATH
        nssm_path = "nssm.exe"
    runbat = (REPO_ROOT / "run.bat").resolve()
    svc = "MemoryHack"
    # install
    run([nssm_path, "install", svc, str(runbat)])
    # set working dir
    run([nssm_path, "set", svc, "AppDirectory", str(REPO_ROOT)])
    # start
    run([nssm_path, "start", svc])
    print("Windows service installed and started as 'MemoryHack'.")

def service_remove_windows(nssm_path):
    if not nssm_path:
        nssm_path = "nssm.exe"
    svc = "MemoryHack"
    run([nssm_path, "stop", svc], check=False)
    run([nssm_path, "remove", svc, "confirm"], check=False)
    print("Windows service removed.")

def verify():
    problems = []
    if not MEM_EDIT_DIR.exists():
        problems.append(f"Missing mem_edit at {MEM_EDIT_DIR}")
    if not REQS_FILE.exists():
        problems.append(f"Missing requirements file at {REQS_FILE}")
    py = venv_python()
    if not py.exists():
        problems.append("venv not created")
    if problems:
        print("VERIFY FAIL:")
        for p in problems:
            print(f"- {p}")
        sys.exit(1)
    print("VERIFY OK")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("install")
    sub.add_parser("uninstall")
    sub.add_parser("verify")

    svc = sub.add_parser("service")
    svc_sub = svc.add_subparsers(dest="svc_cmd", required=True)
    svc_install = svc_sub.add_parser("install")
    svc_install.add_argument("--nssm", help="Path to nssm.exe (Windows only)")
    svc_sub.add_parser("remove").add_argument("--nssm", help="Path to nssm.exe (Windows only)")

    args, extra = ap.parse_known_args()

    if args.cmd == "install":
        install()
    elif args.cmd == "uninstall":
        uninstall()
    elif args.cmd == "verify":
        verify()
    elif args.cmd == "service":
        if args.svc_cmd == "install":
            if IS_LINUX:
                service_install_linux()
            elif IS_WIN:
                service_install_windows(getattr(args, "nssm", None))
            else:
                print("Service install not supported on this OS.")
        elif args.svc_cmd == "remove":
            if IS_LINUX:
                service_remove_linux()
            elif IS_WIN:
                service_remove_windows(getattr(args, "nssm", None))
            else:
                print("Service remove not supported on this OS.")
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
