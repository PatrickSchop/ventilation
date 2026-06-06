#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path

import paramiko


SSH_HOST = "ventilation.domotica.local"
SSH_USER = "admin"
TARGET_SHARE = r"\\ventilation.domotica.local\root\opt\ventilation"
REMOTE_DIR = "/opt/ventilation"
SERVICE_NAME = "ventilation.service"
RUNTIME_DEPS = ("paho-mqtt", "smbus2")

EXCLUDE_NAMES = {
    "deploy.py",
    "deploy.ps1",
    "workspace.code-workspace",
    "AGENTS.md",
    "pytest.ini",
    "requirements-dev.txt",
    ".gitignore",
    "mqtt-test.py",
    "tests",
}
EXCLUDE_SUFFIXES = (".log",)
PRESERVE_ON_TARGET = {"config.json", "ventilation.log"}

CRON_SCHEDULE = "*/10 * * * *"
HEALTH_MONITOR_SCRIPT = "health_monitor.py"


def parse_args():
    parser = argparse.ArgumentParser(description="Deploy the ventilation service.")
    parser.add_argument("--ssh-password", required=True,
                        help="SSH password for the target host.")
    parser.add_argument("--source", default=str(Path.cwd()),
                        help="Local source directory to deploy from.")
    parser.add_argument("--target", default=TARGET_SHARE,
                        help="Samba/CIFS share on the target host.")
    parser.add_argument("--skip-pip", action="store_true",
                        help="Skip installing Python dependencies on the target.")
    return parser.parse_args()


def ssh_run(client, command):
    print(f"ssh> {command}")
    stdin, stdout, stderr = client.exec_command(command)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code


def is_excluded(name):
    if name.startswith("."):
        return True
    if name == "__pycache__":
        return True
    if name in EXCLUDE_NAMES:
        return True
    return any(name.endswith(s) for s in EXCLUDE_SUFFIXES)


def clean_target(target, keep):
    print(f"Cleaning {target} (preserving {sorted(keep)})")
    for entry in list(target.iterdir()):
        if entry.name in keep:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def copy_source(source, target):
    print(f"Copying {source} -> {target}")
    for entry in sorted(source.iterdir()):
        if is_excluded(entry.name):
            print(f"  skip  {entry.name}")
            continue
        dest = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest, dirs_exist_ok=True)
            print(f"  dir   {entry.name}")
        else:
            shutil.copy2(entry, dest)
            print(f"  file  {entry.name}")


def main():
    args = parse_args()
    source = Path(args.source)
    target = Path(args.target)

    if not source.is_dir():
        print(f"Source directory not found: {source}", file=sys.stderr)
        return 1

    target.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {SSH_USER}@{SSH_HOST} ...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(SSH_HOST, username=SSH_USER, password=args.ssh_password,
                       look_for_keys=False, allow_agent=False)
    except paramiko.AuthenticationException:
        print("Authentication failed.", file=sys.stderr)
        return 1
    except paramiko.SSHException as exc:
        print(f"SSH error: {exc}", file=sys.stderr)
        return 1

    try:
        ssh_run(client, f"sudo systemctl stop {SERVICE_NAME}")
        clean_target(target, keep=PRESERVE_ON_TARGET)
        copy_source(source, target)
        if not args.skip_pip:
            ssh_run(client,
                    f"sudo python3 -m pip install --break-system-packages "
                    f"{' '.join(RUNTIME_DEPS)}")
        ssh_run(client, f"sudo chmod 777 {REMOTE_DIR}/VentilationService.py")
        ssh_run(client, f"sudo systemctl start {SERVICE_NAME}")
        cron_line = f"{CRON_SCHEDULE} python3 {REMOTE_DIR}/{HEALTH_MONITOR_SCRIPT}"
        ssh_run(client,
            f"(crontab -l 2>/dev/null | grep -v {HEALTH_MONITOR_SCRIPT} ; "
            f"echo '{cron_line}') | crontab -")
    finally:
        client.close()

    print("Deployment complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
