# Multi-Version Luraph Deobfuscator

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![Node.js: 18+](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Targets](https://img.shields.io/badge/Targets-Luraph%20v14.7%20%7C%20v14.8%20%7C%20v14.9%20%7C%20v15.1%20%7C%20v15.2-red.svg)](#supported-versions)

A unified, multi-version **Luraph Lua/Luau deobfuscation framework** equipped with **deep structural version detection**. It scans protected scripts, accurately identifies the exact Luraph obfuscator version using Bayesian-style exclusion heuristics and AST/bytecode fingerprints, and dispatches the script to the corresponding specialized deobfuscator engine.

---

## Table of Contents

- [Supported Versions](#supported-versions)
- [Project Architecture](#project-architecture)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
  - [Basic Deobfuscation](#basic-deobfuscation)
  - [Auto-Detection Only](#auto-detection-only)
  - [JSON Machine-Readable Output (`--json`)](#json-machine-readable-output---json)
  - [Fast Behavior Trace Mode (`--no-devirt`)](#fast-behavior-trace-mode---no-devirt)
  - [Forcing a Specific Version / Engine](#forcing-a-specific-version--engine)
  - [Fast Devirtualization Mode (`--fast`)](#fast-devirtualization-mode---fast)
  - [Debug Mode (`--debug`)](#debug-mode---debug)
  - [Quiet Output Mode (`-q`)](#quiet-output-mode--q)
- [How Version Detection Works](#how-version-detection-works)
- [Exit Codes](#exit-codes)
- [Submodule Engines](#submodule-engines)
- [Contributing](#contributing)
- [Legal & Disclaimer](#legal--disclaimer)
- [License](#license)

---

## Supported Versions

| Luraph Version | Engine Submodule | Engine Status | Key Capabilities |
|---|---|---|---|
| **Luraph v15.2** | `deobfuscators/v15_2` | Active | VM chunk instrumentation, behavior tracing, 3-level maker lifting |
| **Luraph v15.1 / v15.0** | `deobfuscators/v15_1` | Stable | Full devirtualization (AST hooking, constant decryption, CFG/SSA reconstruction, Roblox API local naming) |
| **Luraph v14.9** | `deobfuscators/v14_v15` | Stable | Dedicated v14.9 dispatcher recovery (`O={...}` seed tables, `:r()` suffix) |
| **Luraph v14.8** | `deobfuscators/v14_v15` | Stable | Dedicated v14.8 dispatcher recovery (`local init = (function(...)` wrapper, `:d()` suffix) |
| **Luraph v14.7** | `deobfuscators/v14_v15` | Stable | Dedicated v14.7 dispatcher recovery (`Z={...}` seed tables, `:g()` suffix) |

---

## Project Architecture

```
luraph-deobf/
├── main.py                  # Master CLI entry point & orchestrator
├── detector.py              # Multi-version detection engine with Bayesian scoring
├── requirements.txt         # Development & testing dependencies
├── README.md                # Project documentation
├── CONTRIBUTING.md          # Contributor guidelines & architecture overview
├── LICENSE                  # MIT License
├── .gitignore               # Git ignore configuration
├── .gitmodules              # Submodule tracking for upstream engines
└── deobfuscators/
    ├── v15_2/               # Luraph v15.2 engine (Submodule: horiz-dev/luraph-v15.2-fix-built)
    ├── v15_1/               # Luraph v15.1/v15 engine (Submodule: ServerDeadd/Luraph-v15.1-Deobfuscator)
    └── v14_v15/             # Luraph v14.x/v15 engine (Submodule: larpcorrupt/luraph-v15-v14.x-deobfuscator)
```

---

## Prerequisites

1. **Python 3.10+**: Core CLI, detection module, and lifting stages.
   - [Download Python](https://www.python.org/)
2. **Node.js 18+**: Required by the v15.1 engine driver.
   - [Download Node.js](https://nodejs.org/)
3. **Luau Runtime**: Precompiled `luau` and `luau-ast` binaries for Linux and Windows are included in `deobfuscators/v15_1/bin/`. `main.py` automatically synchronizes these binaries across all submodule engines on startup.

---

## Installation & Setup

### 1. Clone the Repository with Submodules

Clone this repository with the `--recursive` flag to pull all required deobfuscator submodules:

```bash
git clone --recursive https://github.com/<your-username>/luraph-deobf.git
cd luraph-deobf
```

If you already cloned without `--recursive`, initialize and pull the submodules:

```bash
git submodule update --init --recursive
```

### 2. Verify / Set Permissions (Linux / macOS)

Ensure the prebuilt Luau binaries have executable permissions:

```bash
chmod +x deobfuscators/v15_1/bin/luau deobfuscators/v15_1/bin/luau-ast
```

*(Note: `main.py` automatically sets these permissions on startup.)*

### 3. Optional Development Dependencies

The runtime requires only the Python Standard Library. Development dependencies (type checking, testing) can be installed via:

```bash
pip install -r requirements.txt
```

---

## Usage Guide

### Basic Deobfuscation

Pass your obfuscated Lua/Luau script to `main.py`. The tool auto-detects the version, routes it to the matching engine, and outputs the result:

```bash
python main.py obfuscated.lua -o output.lua
```

The deobfuscated Lua code is saved to `output.lua` and printed to stdout.

### Auto-Detection Only

To inspect a script and identify its Luraph version without deobfuscating:

```bash
# Using main.py
python main.py sample.lua --detect-only

# Or using detector.py directly
python detector.py sample.lua
```

### JSON Machine-Readable Output (`--json`)

To get a structured JSON breakdown of version, confidence, minification flag, scores, pattern matches, and negative exclusion penalties:

```bash
python detector.py sample.lua --json
```

Example output:
```json
{
  "version": "v15.2",
  "confidence": 1.0,
  "detection_type": "structural",
  "minified": true,
  "scores": {
    "v15.2": 195,
    "v15.1": 60,
    "v14.7": -100,
    "v14.8": -100,
    "v14.9": -100
  },
  "matched": {
    "v15.2": [
      "root_setmetatable",
      "native_luau_bitops_no_bit32",
      "script_key_injected",
      "mapped_loadstring_slot8",
      "v15_2_character_dict",
      "buffer_u32_fromstring",
      "lph_marker"
    ],
    "v15.1": [
      "root_setmetatable",
      "powers_of_2_table",
      "buffer_u32_fromstring",
      "lph_marker"
    ],
    "v14.7": [],
    "v14.8": [],
    "v14.9": []
  },
  "excluded": {
    "v15.2": [],
    "v15.1": ["no_bit32_slots_penalty"],
    "v14.7": ["root_setmetatable_present"],
    "v14.8": ["root_setmetatable_present"],
    "v14.9": ["root_setmetatable_present"]
  }
}
```

### Fast Behavior Trace Mode (`--no-devirt`)

If you need to quickly inspect what a script does at runtime (e.g. URLs fetched, remotes fired, webhooks called, UI created), use `--no-devirt`:

```bash
python main.py sample.lua -o trace.lua --no-devirt
```

### Forcing a Specific Version / Engine

To bypass auto-detection and force a specific version or backend engine:

```bash
# Force Luraph v15.2
python main.py input.lua -o clean.lua --version v15.2

# Force Luraph v15.1
python main.py input.lua -o clean.lua --version v15.1

# Force Luraph v14.x with auto engine selection
python main.py input.lua -o clean.lua --version v14

# Force a specific Luraph v14 engine (14.7, 14.8, or 14.9)
python main.py input.lua -o clean.lua --version v14 --engine 14.8
```

### Fast Devirtualization Mode (`--fast`)

The v15.1 engine executes parallel devirtualization candidates with randomized seeds by default. For rapid single-candidate deobfuscation, use `--fast`:

```bash
python main.py input.lua -o clean.lua --fast
```

### Debug Mode (`--debug`)

Keep all intermediate files (disassembly, VM chunk dumps, prototype maps, trace files):

```bash
python main.py input.lua -o clean.lua --debug
```

### Quiet Output Mode (`-q`)

Suppress progress messages on stderr and emit only the deobfuscated Lua code on stdout (useful for piping into formatters or other tools):

```bash
python main.py input.lua -q -o clean.lua > deobfuscated.lua
```

---

## How Version Detection Works

`detector.py` uses a Bayesian-style heuristic engine that inspects structural AST patterns and applies both positive scoring and negative exclusion penalties:

1. **Root Construct Divergence:**
   - **`v15.x`:** Initialized with `return setmetatable({...}, ...)`. Penalizes `v14.x` candidates with $-100$.
   - **`v14.x`:** Initialized with a raw table `return({...})` or `local init = (function(...) return({...}) end)(...)`. Penalizes `v15.x` candidates with $-100$.
2. **Library Slot Mapping & Native Operations:**
   - **`v15.1`:** Maps `bit32` methods in numeric slots (`[90]=bit32.rshift`, `[99]=bit32.countlz`, `[113]=bit32.band`) and includes powers-of-2 tables (`[0]=1,2,4,8...4294967296`).
   - **`v15.2`:** Relies on Luau native 64-bit integer bitwise operations and buffer deserialization (`buffer.writeu32`, `buffer.create`, `buffer.fromstring`), character substitution dictionaries `d={...}`, and closure maker hooks (`__MK`).
3. **v14 Sub-Version Granularity:**
   - **`v14.7`:** Invocation suffix `}):g()(...)`, seed table `Z = { ... }`, parameter signature `(H, K, g, N)`.
   - **`v14.8`:** Bootstrap wrapper `local init = (function(...)`, invocation suffix `}):d()(...)`, parameter signature `(t, i)`.
   - **`v14.9`:** Invocation suffix `}):r()(...)`, seed table `O = { ... }`, parameter signature `(d, C, a, W)`.
4. **Header Confirmation:**
   - Header comments are used solely to confirm or boost confidence on structurally validated scripts. A header comment alone with zero structural evidence returns `unknown` (confidence `0.00`).

---

## Exit Codes

`main.py` adheres to standard exit codes:

- `0`: Deobfuscation succeeded and output was written.
- `1`: Deobfuscation engine failure or timeout.
- `2`: Invalid input file or unknown Luraph version.

---

## Submodule Engines

### 1. `deobfuscators/v15_2` (Luraph v15.2 Engine)
- **Upstream:** [horiz-dev/luraph-v15.2-fix-built](https://github.com/horiz-dev/luraph-v15.2-fix-built)
- **Runtime:** Python 3.10+ + Luau sandbox (`deobf/bin/luau`).

### 2. `deobfuscators/v15_1` (Luraph v15.1 Engine)
- **Upstream:** [ServerDeadd/Luraph-v15.1-Deobfuscator](https://github.com/ServerDeadd/Luraph-v15.1-Deobfuscator)
- **Runtime:** Node.js 18+ + Python 3.10+ + Luau sandbox (`bin/luau`).

### 3. `deobfuscators/v14_v15` (Luraph v14.x Engine)
- **Upstream:** [larpcorrupt/luraph-v15-v14.x-deobfuscator](https://github.com/larpcorrupt/luraph-v15-v14.x-deobfuscator)
- **Runtime:** Python 3.10+ + Luau runtime.

---

## Contributing

Contributions, opcode discoveries, and new test cases are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details on code style, testing, and submission workflows.

---

## Legal & Disclaimer

This project is created strictly for **defensive reverse engineering, malware analysis, security research, and educational purposes**. Obfuscated Lua scripts in gaming and exploit ecosystems are frequently used to conceal malicious payloads (e.g. token stealers, remote-access backdoors, Discord webhook exfiltrators).

- Use this tool only on scripts you own, are authorized to analyze, or are evaluating for safety.
- This project is independent and is not affiliated with, endorsed by, or connected to Luraph, lura.ph, or Roblox Corporation.

---

## License

This project is licensed under the [MIT License](LICENSE).
