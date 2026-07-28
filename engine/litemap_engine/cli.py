from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .errors import EngineError
from .service import EngineService


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="litemap", description="Headless LiteMaptica engine")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("versions", help="list tested Minecraft Java versions")
    create = commands.add_parser("create", help="create a .litemap project")
    create.add_argument("path")
    create.add_argument("--name", default="Untitled Reconstruction")
    create.add_argument("--minecraft-version", default="26.2")
    open_command = commands.add_parser("open", help="validate and summarize a project")
    open_command.add_argument("project")
    demo = commands.add_parser("demo", help="load the evidence-backed development fixture")
    demo.add_argument("project")
    voxels = commands.add_parser("voxels", help="print composed project voxels")
    voxels.add_argument("project")
    export = commands.add_parser("export", help="write and validate a .litematic")
    export.add_argument("project")
    export.add_argument("destination")
    export.add_argument("--author", default="LiteMaptica")
    validate = commands.add_parser("validate-export", help="round-trip validate a .litematic")
    validate.add_argument("path")
    capabilities_command = commands.add_parser("capabilities", help="report packaged/native adapter availability")
    return result


def main() -> None:
    args = parser().parse_args()
    service = EngineService()
    try:
        if args.command == "versions":
            value = service.dispatch("assets.list_supported")
        elif args.command == "create":
            value = service.dispatch("project.create", {"path": args.path, "name": args.name, "minecraftVersion": args.minecraft_version})
        elif args.command == "open":
            value = service.dispatch("project.open", {"project": args.project})
        elif args.command == "demo":
            value = service.dispatch("development.load_demo", {"project": args.project})
        elif args.command == "voxels":
            value = service.dispatch("scene.voxels", {"project": args.project, "includeEvidence": True})
        elif args.command == "export":
            value = service.dispatch("export.write", {"project": args.project, "destination": args.destination, "author": args.author})
        elif args.command == "validate-export":
            value = service.dispatch("export.validate", {"path": args.path})
        elif args.command == "capabilities":
            value = service.dispatch("engine.capabilities")
        else:
            raise AssertionError(args.command)
        _print(value)
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
