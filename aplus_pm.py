#!/usr/bin/env python3
"""
A+ Package Manager — aplus_pm
==============================
Simple package manager for the A+ programming language.

Commands:
    aplus_pm.py init                  Create aplus-packages.json
    aplus_pm.py install <repo_url>    Clone a package from GitHub/git
    aplus_pm.py install <pkg>         Install a dependency from aplus-packages.json
    aplus_pm.py list                  List installed packages
    aplus_pm.py load <file.a+>        Prepend loaded packages to a file

Packages are stored in ~/.aplus/packages/.
Dependencies tracked in aplus-packages.json (project-local).

$load Directive:
    When A+ encounters $load "packagename", the package manager
    can resolve and prepend the package's .a+ content to the source.
    Use: aplus_pm.py load myfile.a+  → emits resolved source with $load
    directives replaced inline.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import re
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

PACKAGES_HOME = Path.home() / ".aplus" / "packages"
MANIFEST_NAME = "aplus-packages.json"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def ensure_packages_dir() -> Path:
    """Create ~/.aplus/packages/ if it doesn't exist."""
    PACKAGES_HOME.mkdir(parents=True, exist_ok=True)
    return PACKAGES_HOME


def find_git() -> str:
    """Return path to git or raise."""
    git = shutil.which("git")
    if not git:
        sys.exit("Error: git not found. Install git to use the package manager.")
    return git


def find_gh() -> Optional[str]:
    """Return path to gh CLI if available."""
    return shutil.which("gh")


def read_manifest() -> dict:
    """Read aplus-packages.json from current directory."""
    manifest_path = Path(MANIFEST_NAME)
    if not manifest_path.exists():
        return {"name": Path.cwd().name, "version": "0.0.0", "dependencies": {}}
    with open(manifest_path, "r") as f:
        return json.load(f)


def write_manifest(data: dict) -> None:
    """Write aplus-packages.json to current directory."""
    with open(MANIFEST_NAME, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def resolve_package_name(repo_url: str) -> str:
    """Extract package name from a git URL like user/repo or full URL."""
    # Handle github.com/user/repo or user/repo
    url = repo_url.rstrip("/")
    if "/" not in url:
        return url
    # Remove .git suffix
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def package_installed(name: str) -> bool:
    """Check if a package exists in ~/.aplus/packages/<name>."""
    pkg_dir = PACKAGES_HOME / name
    return pkg_dir.is_dir()


def find_aplus_files(directory: Path) -> list[Path]:
    """Recursively find all .a+ and .a files in a directory."""
    files = []
    for ext in ("*.a+", "*.a"):
        files.extend(sorted(directory.rglob(ext)))
    return files


def resolve_load_directive(source: str, search_dirs: list[Path]) -> str:
    """Replace $load \"package\" directives with the package content.

    Syntax: $load "package_name"
    Searches search_dirs for <package_name>.a+ or <package_name>/entry.a+
    """
    pattern = re.compile(r'\$load\s+"([^"]+)"')

    def replacer(match: re.Match) -> str:
        pkg_name = match.group(1)
        resolved = _resolve_package_content(pkg_name, search_dirs)
        if resolved is None:
            return match.group(0)  # keep unresolved
        return resolved

    result = pattern.sub(replacer, source)
    return result


def _resolve_package_content(pkg_name: str, search_dirs: list[Path]) -> Optional[str]:
    """Try to find and read package content."""
    for search_dir in search_dirs:
        # Try <name>.a+ directly
        direct = search_dir / f"{pkg_name}.a+"
        if direct.is_file():
            return direct.read_text(encoding="utf-8") + "\n"

        # Try <name>.a
        direct_a = search_dir / f"{pkg_name}.a"
        if direct_a.is_file():
            return direct_a.read_text(encoding="utf-8") + "\n"

        # Try <name>/ as directory package, look for main.a+ or entry file
        pkg_dir = search_dir / pkg_name
        if pkg_dir.is_dir():
            for candidate in ["main.a+", "index.a+", "init.a+", f"{pkg_name}.a+"]:
                entry = pkg_dir / candidate
                if entry.is_file():
                    return entry.read_text(encoding="utf-8") + "\n"

            # If no conventional entry, concatenate all .a+ files
            all_files = find_aplus_files(pkg_dir)
            if all_files:
                parts = []
                for f in all_files:
                    parts.append(f"⍝ --- Begin ${pkg_name}/{f.name} ---\n")
                    parts.append(f.read_text(encoding="utf-8"))
                    parts.append(f"\n⍝ --- End ${pkg_name}/{f.name} ---\n")
                return "\n".join(parts)

    return None


# ═══════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════

def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new aplus-packages.json in the current directory."""
    manifest_path = Path(MANIFEST_NAME)
    if manifest_path.exists():
        print(f"{MANIFEST_NAME} already exists. Use 'install' to add dependencies.")
        return

    project_name = Path.cwd().name
    data = {
        "name": project_name,
        "version": "0.1.0",
        "description": "",
        "dependencies": {},
    }
    write_manifest(data)
    print(f"Created {MANIFEST_NAME}")


def cmd_install(args: argparse.Namespace) -> None:
    """Install a package from a git URL or from manifest dependencies."""
    ensure_packages_dir()
    git = find_git()

    targets = args.package

    # If no explicit package, install all from manifest
    if not targets:
        manifest = read_manifest()
        targets = list(manifest.get("dependencies", {}).keys())
        if not targets:
            print("No packages specified and no dependencies in aplus-packages.json.")
            return

    manifest = read_manifest()
    installed_any = False

    for target in targets:
        # Determine repo URL: if in manifest deps, use that; otherwise treat as URL
        if target in manifest.get("dependencies", {}):
            repo_url = manifest["dependencies"][target]
        else:
            repo_url = target

        pkg_name = resolve_package_name(repo_url)
        pkg_dir = PACKAGES_HOME / pkg_name

        if pkg_dir.exists():
            print(f"Package '{pkg_name}' already installed. Updating...")
            subprocess.run(
                [git, "pull", "--ff-only"],
                cwd=str(pkg_dir),
                check=False,
            )
        else:
            print(f"Installing '{pkg_name}' from {repo_url}...")

            # Build full URL if needed (user/repo shorthand)
            if not repo_url.startswith(("http://", "https://", "git@", "ssh://")):
                # Check if it's a github user/repo shorthand
                if repo_url.count("/") == 1:
                    repo_url = f"https://github.com/{repo_url}"
                else:
                    # Assume it's a direct git cloneable URL
                    pass

            result = subprocess.run(
                [git, "clone", repo_url, str(pkg_dir)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"  Failed to clone: {result.stderr.strip()}")
                continue
            print(f"  Installed to {pkg_dir}")

        # Update manifest with the dependency
        if "dependencies" not in manifest:
            manifest["dependencies"] = {}
        manifest["dependencies"][pkg_name] = repo_url
        installed_any = True

    if installed_any:
        write_manifest(manifest)
        print(f"\nUpdated {MANIFEST_NAME}")


def cmd_list(args: argparse.Namespace) -> None:
    """List installed packages."""
    ensure_packages_dir()

    if not PACKAGES_HOME.exists() or not any(PACKAGES_HOME.iterdir()):
        print("No packages installed.")
        print(f"Packages directory: {PACKAGES_HOME}")
        return

    print(f"Installed packages ({PACKAGES_HOME}):")
    print("-" * 50)

    for pkg_dir in sorted(PACKAGES_HOME.iterdir()):
        if not pkg_dir.is_dir():
            continue
        name = pkg_dir.name

        # Check if it's a git repo
        is_git = (pkg_dir / ".git").is_dir()
        files = find_aplus_files(pkg_dir)

        print(f"  {name}")
        if is_git:
            # Try to get remote URL
            try:
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=str(pkg_dir),
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f"    remote: {result.stdout.strip()}")
            except Exception:
                pass

        if files:
            print(f"    files: {len(files)} .a+/.a file(s)")
            for f in files[:5]:
                print(f"      - {f.relative_to(pkg_dir)}")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more")

        # Check for project manifest
        pkg_manifest = pkg_dir / MANIFEST_NAME
        if pkg_manifest.exists():
            try:
                pm = json.loads(pkg_manifest.read_text())
                print(f"    version: {pm.get('version', '?')}")
            except Exception:
                pass

        print()

    # Also show current project deps from manifest
    local_manifest = Path(MANIFEST_NAME)
    if local_manifest.exists():
        manifest = read_manifest()
        deps = manifest.get("dependencies", {})
        if deps:
            print("Project dependencies (from aplus-packages.json):")
            for dep_name, dep_url in deps.items():
                installed = "✓" if package_installed(dep_name) else "✗"
                print(f"  [{installed}] {dep_name} → {dep_url}")


def cmd_load(args: argparse.Namespace) -> None:
    """Process $load directives in an A+ source file.

    Reads the file, replaces $load "package" directives with the actual
    package content from ~/.aplus/packages/, and outputs the resolved
    source to stdout or --output file.
    """
    input_path = Path(args.file)
    if not input_path.exists():
        sys.exit(f"File not found: {input_path}")

    source = input_path.read_text(encoding="utf-8")

    # Build search directories
    search_dirs = [PACKAGES_HOME]
    if args.package_dir:
        for d in args.package_dir:
            search_dirs.append(Path(d).resolve())
    # Also search current directory
    search_dirs.append(Path.cwd())

    resolved = resolve_load_directive(source, search_dirs)

    if args.output:
        # If output specified, write to file; resolved may be raw bytes from
        # KAPL files, so write bytes
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(resolved)
        except UnicodeEncodeError:
            # Fall back to binary write for KAPL-encoded files
            with open(args.output, "wb") as f:
                f.write(resolved.encode("utf-8", errors="surrogateescape"))
        print(f"Resolved source written to {args.output}")
    else:
        # Print to stdout. Try text, fall back to binary.
        try:
            print(resolved)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(resolved.encode("utf-8", errors="surrogateescape"))


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove an installed package."""
    pkg_name = args.package[0]
    pkg_dir = PACKAGES_HOME / pkg_name

    if not pkg_dir.exists():
        print(f"Package '{pkg_name}' is not installed.")
        return

    shutil.rmtree(str(pkg_dir))
    print(f"Removed package '{pkg_name}' from {pkg_dir}")

    # Update manifest
    manifest = read_manifest()
    if pkg_name in manifest.get("dependencies", {}):
        del manifest["dependencies"][pkg_name]
        write_manifest(manifest)
        print(f"Removed '{pkg_name}' from {MANIFEST_NAME}")


def cmd_update(args: argparse.Namespace) -> None:
    """Update all installed packages (git pull)."""
    ensure_packages_dir()
    git = find_git()

    if not PACKAGES_HOME.exists():
        print("No packages installed.")
        return

    updated = 0
    for pkg_dir in sorted(PACKAGES_HOME.iterdir()):
        if not pkg_dir.is_dir():
            continue
        if not (pkg_dir / ".git").is_dir():
            continue
        print(f"Updating {pkg_dir.name}...")
        result = subprocess.run(
            [git, "pull", "--ff-only"],
            cwd=str(pkg_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                print(f"  Already up to date.")
            else:
                print(f"  Updated.")
                updated += 1
        else:
            print(f"  Failed: {result.stderr.strip()}")

    print(f"\n{updated} package(s) updated.")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="A+ Package Manager",
        prog="aplus_pm",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser("init", help="Create aplus-packages.json")

    # install
    install_parser = subparsers.add_parser(
        "install", help="Install package(s) from git"
    )
    install_parser.add_argument(
        "package",
        nargs="*",
        help="Package to install (git URL, github user/repo, or manifest dependency name)",
    )

    # list
    list_parser = subparsers.add_parser("list", help="List installed packages")

    # load
    load_parser = subparsers.add_parser(
        "load", help="Resolve $load directives in an A+ source file"
    )
    load_parser.add_argument("file", help="A+ source file to process")
    load_parser.add_argument(
        "-o", "--output", help="Output file (default: stdout)"
    )
    load_parser.add_argument(
        "-p", "--package-dir", action="append",
        help="Additional package search directory (can repeat)"
    )

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove an installed package")
    remove_parser.add_argument("package", nargs=1, help="Package name to remove")

    # update
    update_parser = subparsers.add_parser("update", help="Update all installed packages")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "install": cmd_install,
        "list": cmd_list,
        "load": cmd_load,
        "remove": cmd_remove,
        "update": cmd_update,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
