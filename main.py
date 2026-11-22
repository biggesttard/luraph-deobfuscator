#!/usr/bin/env python3
"""
main.py — Multi-Version Luraph Deobfuscator Orchestrator

Automatically detects the version of Luraph obfuscation used on a given script,
routes the script to the corresponding deobfuscation engine from the submodules,
and produces clean, readable Lua/Luau output.

Supported versions:
- Luraph v15.2       (via deobfuscators/v15_2)
- Luraph v15.1 / v15 (via deobfuscators/v15_1)
- Luraph v14.x       (via deobfuscators/v14_v15: v14.7, v14.8, v14.9)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from detector import DetectionResult, detect


# =============================================================================
# Path & Environment Setup
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DEOB_V15_2_DIR = PROJECT_ROOT / "deobfuscators" / "v15_2"
DEOB_V15_1_DIR = PROJECT_ROOT / "deobfuscators" / "v15_1"
DEOB_V14_DIR = PROJECT_ROOT / "deobfuscators" / "v14_v15" / "Deobfuscator" / "deobf"


def eprint(*args, **kwargs) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def ensure_binaries() -> None:
    """
    Ensure that Luau runtime binaries (luau and luau-ast) are available
    and marked executable across all submodule environments.
    """
    v15_1_bin = DEOB_V15_1_DIR / "bin"
    v15_2_bin = DEOB_V15_2_DIR / "deobf" / "bin"
    v14_bin = DEOB_V14_DIR / "bin"

    # Synchronize Linux ELF binaries from v15_1 if missing in other engines
    if os.name != "nt" and v15_1_bin.is_dir():
        for target_bin in (v15_2_bin, v14_bin):
            target_bin.mkdir(parents=True, exist_ok=True)
            for exe in ("luau", "luau-ast"):
                src = v15_1_bin / exe
                dst = target_bin / exe
                if src.is_file() and not dst.is_file():
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass
                if dst.is_file():
                    try:
                        dst.chmod(0o755)
                    except OSError:
                        pass

    # Ensure v15_1 binaries have +x permission
    if os.name != "nt" and v15_1_bin.is_dir():
        for exe in ("luau", "luau-ast"):
            p = v15_1_bin / exe
            if p.is_file():
                try:
                    p.chmod(0o755)
                except OSError:
                    pass


def check_prerequisites(version: str) -> None:
    """Verify runtime tools required for the target version."""
    if version in ("v15.1", "v15"):
        if not shutil.which("node"):
            eprint("[!] Error: Node.js (18+) is required for Luraph v15.1 deobfuscation but was not found in PATH.")
            eprint("    Please install Node.js from https://nodejs.org/")
            sys.exit(1)

    python_bin = sys.executable or "python3"
    if not python_bin:
        eprint("[!] Error: Python 3.10+ is required but was not found.")
        sys.exit(1)


# =============================================================================
# Deobfuscator Runners
# =============================================================================

def run_v15_2(
    input_path: Path,
    output_path: Path,
    no_devirt: bool = False,
    debug: bool = False,
    timeout: int = 180,
) -> bool:
    """Execute the Luraph v15.2 deobfuscator."""
    entry = DEOB_V15_2_DIR / "deobf" / "deob.py"
    if not entry.is_file():
        eprint(f"[!] Error: v15.2 entry point not found at {entry}")
        eprint("    Did you initialize git submodules? Run: git submodule update --init --recursive")
        return False

    cmd = [
        sys.executable,
        str(entry),
        str(input_path),
        "-o",
        str(output_path),
    ]
    if no_devirt:
        cmd.append("--no-devirt")
    if debug:
        cmd.append("--debug")

    eprint(f"[*] Executing Luraph v15.2 engine on {input_path.name}...")
    try:
        res = subprocess.run(cmd, cwd=str(entry.parent), timeout=timeout)
        return res.returncode == 0 and output_path.is_file()
    except subprocess.TimeoutExpired:
        eprint(f"[!] Deobfuscation timed out after {timeout} seconds.")
        return False
    except Exception as exc:
        eprint(f"[!] Error running v15.2 deobfuscator: {exc}")
        return False


def run_v15_1(
    input_path: Path,
    output_path: Path,
    no_devirt: bool = False,
    fast: bool = False,
    debug: bool = False,
    timeout: int = 180,
) -> bool:
    """Execute the Luraph v15.1 / v15 deobfuscator."""
    entry = DEOB_V15_1_DIR / "deob.js"
    if not entry.is_file():
        eprint(f"[!] Error: v15.1 entry point not found at {entry}")
        eprint("    Did you initialize git submodules? Run: git submodule update --init --recursive")
        return False

    cmd = [
        "node",
        str(entry),
        str(input_path),
        "-o",
        str(output_path),
    ]
    if no_devirt:
        cmd.append("--no-devirt")
    if debug:
        cmd.append("--debug")

    env = os.environ.copy()
    env["PYTHON_BIN"] = sys.executable
    if fast:
        env["DEOB_FAST"] = "1"

    eprint(f"[*] Executing Luraph v15.1 engine on {input_path.name}...")
    try:
        res = subprocess.run(cmd, cwd=str(DEOB_V15_1_DIR), env=env, timeout=timeout)
        return res.returncode == 0 and output_path.is_file()
    except subprocess.TimeoutExpired:
        eprint(f"[!] Deobfuscation timed out after {timeout} seconds.")
        return False
    except Exception as exc:
        eprint(f"[!] Error running v15.1 deobfuscator: {exc}")
        return False


def run_v14(
    input_path: Path,
    output_path: Path,
    engine: str = "auto",
    no_devirt: bool = False,
    debug: bool = False,
    timeout: int = 180,
) -> bool:
    """Execute the Luraph v14.x deobfuscator with sub-version engine routing."""
    entry = DEOB_V14_DIR / "cli.py"
    if not entry.is_file():
        eprint(f"[!] Error: v14.x entry point not found at {entry}")
        eprint("    Did you initialize git submodules? Run: git submodule update --init --recursive")
        return False

    # Normalize engine string (e.g. 'v14.8' -> '14.8')
    norm_engine = engine.removeprefix("v")
    if norm_engine not in ("14.7", "14.8", "14.9"):
        norm_engine = "auto"

    cmd = [
        sys.executable,
        str(entry),
        str(input_path),
        "-o",
        str(output_path),
        "--engine",
        norm_engine,
    ]
    if no_devirt:
        cmd.append("--no-devirt")
    if debug:
        cmd.append("--debug")

    eprint(f"[*] Executing Luraph v14.x engine ({norm_engine}) on {input_path.name}...")
    try:
        res = subprocess.run(cmd, cwd=str(DEOB_V14_DIR), timeout=timeout)
        return res.returncode == 0 and output_path.is_file()
    except subprocess.TimeoutExpired:
        eprint(f"[!] Deobfuscation timed out after {timeout} seconds.")
        return False
    except Exception as exc:
        eprint(f"[!] Error running v14 deobfuscator: {exc}")
        return False


# =============================================================================
# CLI Parser & Orchestration
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Multi-Version Luraph Deobfuscator with Deep Auto-Detection (v15.2, v15.1, v14.7, v14.8, v14.9)",
    )
    p.add_argument("input", help="Path to obfuscated .lua/.luau script")
    p.add_argument(
        "-o",
        "--output",
        default="output.lua",
        help="Path to write deobfuscated Lua code (default: output.lua)",
    )
    p.add_argument(
        "-v",
        "--version",
        dest="force_version",
        choices=("auto", "v15.2", "v15.1", "v14", "v14.7", "v14.8", "v14.9", "14.7", "14.8", "14.9"),
        default="auto",
        help="Override auto-detection and force a specific version (default: auto)",
    )
    p.add_argument(
        "--engine",
        choices=("auto", "14.7", "14.8", "14.9"),
        default="auto",
        help="Specific engine for v14.x deobfuscation (default: auto)",
    )
    p.add_argument(
        "--no-devirt",
        "--trace",
        action="store_true",
        help="Fast behaviour trace mode (skip VM bytecode devirtualization)",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: run a single devirtualization candidate (v15.1)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Hard execution timeout in seconds per pass (default: 180)",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Keep intermediate disassembly and trace files",
    )
    p.add_argument(
        "--detect-only",
        action="store_true",
        help="Only run auto-detection and print the result, without deobfuscating",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress banner/progress logs on stderr and only output deobfuscated Lua to stdout",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        eprint(f"[!] Error: input file not found: {input_path}")
        return 2

    output_path = Path(args.output).resolve()

    # Step 1: Detect version using deep structural heuristics
    if not args.quiet:
        eprint(f"[*] Analyzing {input_path.name} with deep structural heuristics...")

    detection: DetectionResult = detect(input_path)

    if args.detect_only:
        print(f"Detected Version : {detection.version}")
        print(f"Confidence       : {detection.confidence:.2f}")
        print(f"Detection Type   : {detection.detection_type}")
        print(f"Minified         : {detection.minified}")
        print(f"Scores           : {detection.scores}")
        print(f"Matched Patterns : {detection.matched.get(detection.version, [])}")
        return 0 if detection.is_known() else 1

    # Resolve target version
    target_version = detection.version
    if args.force_version != "auto":
        target_version = args.force_version
        if not args.quiet:
            eprint(f"[*] Version forced by user: {target_version}")
    else:
        if not args.quiet:
            eprint(f"[+] Detected: {detection.version} (confidence: {detection.confidence:.2f}, type: {detection.detection_type}, minified: {detection.minified})")

    if target_version == "unknown":
        eprint("[!] Error: Version detected as unknown — no matching deobfuscator available.")
        eprint("    The script does not appear to be protected with a supported Luraph version (v15.2, v15.1, v14.7, v14.8, v14.9).")
        eprint("    Run with: python detector.py <file> --json for detailed scoring and pattern breakdown.")
        eprint("    If you know the version, you can force it using: python main.py <file> --version <v15.2|v15.1|v14.7|v14.8|v14.9>")
        return 2

    # Step 2: Ensure binary runtimes & permissions
    ensure_binaries()
    check_prerequisites(target_version)

    # Step 3: Route to the appropriate deobfuscator
    success = False
    if target_version == "v15.2":
        success = run_v15_2(
            input_path=input_path,
            output_path=output_path,
            no_devirt=args.no_devirt,
            debug=args.debug,
            timeout=args.timeout,
        )
    elif target_version in ("v15.1", "v15"):
        success = run_v15_1(
            input_path=input_path,
            output_path=output_path,
            no_devirt=args.no_devirt,
            fast=args.fast,
            debug=args.debug,
            timeout=args.timeout,
        )
    elif target_version.startswith("v14") or target_version.startswith("14"):
        engine = args.engine
        if engine == "auto":
            # Map specific v14 subversions to their dedicated engines
            if target_version in ("v14.7", "14.7"):
                engine = "14.7"
            elif target_version in ("v14.8", "14.8"):
                engine = "14.8"
            elif target_version in ("v14.9", "14.9"):
                engine = "14.9"
            else:
                engine = "auto"
        success = run_v14(
            input_path=input_path,
            output_path=output_path,
            engine=engine,
            no_devirt=args.no_devirt,
            debug=args.debug,
            timeout=args.timeout,
        )
    else:
        eprint(f"[!] Unsupported version: {target_version}")
        return 1

    # Step 4: Handle results
    if success and output_path.is_file():
        if not args.quiet:
            eprint(f"\n[+] Deobfuscation successful! Saved to: {output_path}")
            eprint("=" * 70)
        try:
            content = output_path.read_text(encoding="utf-8", errors="replace")
            print(content)
        except Exception as exc:
            eprint(f"[!] Warning: could not print output content: {exc}")
        return 0
    else:
        eprint(f"\n[!] Deobfuscation failed for {input_path.name}.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
