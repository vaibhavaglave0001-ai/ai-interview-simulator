"""Send local settings to the linked Vercel project without printing secrets."""

import argparse
import os
import subprocess

from deployment_config import ROOT, load_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=("production", "preview"))
    args = parser.parse_args()
    if not (ROOT / ".vercel" / "project.json").exists():
        raise RuntimeError("Link this directory using vercel link first")
    settings = load_settings()
    command = "vercel.cmd" if os.name == "nt" else "vercel"
    for name, value in settings.items():
        result = subprocess.run(
            [command, "env", "add", name, args.target, "--force", "--yes", "--sensitive"],
            input=value, text=True, capture_output=True, cwd=ROOT,
        )
        if result.returncode:
            raise RuntimeError(f"Vercel could not configure {name}; check authorization and project access")
        print(f"Configured {name} for {args.target}", flush=True)


if __name__ == "__main__":
    main()
