#!/usr/bin/env python3
"""Explicit SSH deployment; all installation/download/inference remains remote.

Default only deploys the worker. --install prepares a task-local venv, --download
fetches the official ModelScope model remotely, --manifest verifies its content.
No system Python/driver changes, sudo, service port or model transfer is needed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def remote_setup(root, install, download):
    from remote_worker import MODEL_ID, scoped_environment
    environment = scoped_environment(root)
    # Preparation may use network; inference always forces offline mode instead.
    environment.update(HF_HUB_OFFLINE="0", TRANSFORMERS_OFFLINE="0")
    python = root / "venv/bin/python"
    log_dir = root / "output"
    log_dir.mkdir(exist_ok=True)
    with (log_dir / "setup.log").open("ab") as log:
        def run(args):
            print(json.dumps([str(arg) for arg in args]), flush=True)
            subprocess.run([str(arg) for arg in args], env=environment, cwd=root,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if install:
            # Existing host lacks ensurepip; bootstrap pip only inside this venv.
            run(["python3", "-m", "venv", "--without-pip", root / "venv"])
            import urllib.request
            installer = root / "tmp/get-pip.py"
            with urllib.request.urlopen("https://bootstrap.pypa.io/get-pip.py", timeout=60) as response:
                installer.write_bytes(response.read())
            run([python, installer])
            run([python, "-m", "pip", "install", "torch==2.8.0", "torchaudio==2.8.0",
                 "--index-url", "https://download.pytorch.org/whl/cu128", "--report", log_dir / "torch-install.json"])
            run([python, "-m", "pip", "install", "-r", root / "requirements-tts.txt",
                 "--report", log_dir / "tts-install.json"])
            run([python, "-m", "pip", "check"])
            freeze = subprocess.run([str(python), "-m", "pip", "freeze"], env=environment,
                                    capture_output=True, check=True).stdout
            (log_dir / "environment-freeze.txt").write_bytes(freeze)
        if download:
            run([root / "venv/bin/modelscope", "download", "--model", MODEL_ID,
                 "--local_dir", root / "models" / MODEL_ID.split("/")[-1]])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--remote-root", default="/srv/manim-tts")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--remote", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.remote:
        remote_setup(Path(args.remote_root), args.install, args.download)
        return 0
    from research.voice import deploy_worker, request, ssh
    settings = {"backend": "ssh", "host": args.host, "remote_root": args.remote_root}
    deploy_worker(settings)
    if args.install or args.download:
        payload = {"setup_remote_voice.py": Path(__file__).read_text(),
                   "requirements-tts.txt": Path(__file__).parents[1].joinpath("requirements-tts.txt").read_text()}
        bootstrap = ("import json,pathlib,sys; r=pathlib.Path(sys.argv[1]); "
                     "[(r/k).write_text(v) for k,v in json.load(sys.stdin).items()]")
        ssh(settings, ["python3", "-c", bootstrap, args.remote_root], json.dumps(payload).encode())
        command = ["python3", args.remote_root + "/setup_remote_voice.py", "--host", args.host, "--remote", "--remote-root", args.remote_root]
        if args.install:
            command.append("--install")
        if args.download:
            command.append("--download")
        # Long-running preparation is explicit, not hidden in synthesize_remote.
        print(ssh(settings, command, timeout=None).decode())
    if args.manifest:
        print(json.dumps(request(settings, "manifest"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
