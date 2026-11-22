# Contributing to Multi-Version Luraph Deobfuscator

Thank you for your interest in contributing to the **Multi-Version Luraph Deobfuscator** project! This guide explains how to set up your local development environment, project architecture conventions, how to contribute new detection heuristics and deobfuscation engines, and our code quality standards.

---

## Table of Contents

- [Code of Conduct & Submodule Policy](#submodule-policy)
- [Getting Started](#getting-started)
  - [1. Fork & Clone with Submodules](#1-fork--clone-with-submodules)
  - [2. Set Up Virtual Environment](#2-set-up-virtual-environment)
- [Project Structure Overview](#project-structure-overview)
- [How to Improve Detection Heuristics](#how-to-improve-detection-heuristics)
  - [Scoring Model & Bayesian Exclusions](#scoring-model--bayesian-exclusions)
  - [Debugging Detection with JSON Output](#debugging-detection-with-json-output)
  - [Confidence Thresholds](#confidence-thresholds)
- [How to Add a New Luraph Version](#how-to-add-a-new-luraph-version)
- [Code Style & Quality Guidelines](#code-style--quality-guidelines)
- [Reporting a False Detection](#reporting-a-false-detection)
- [Pull Request Checklist](#pull-request-checklist)

---

## Submodule Policy

> **Important:** The folders located under `deobfuscators/` (`deobfuscators/v15_2`, `deobfuscators/v15_1`, `deobfuscators/v14_v15`) are tracked as external Git submodules from their respective upstream repositories.
>
> **Do not modify files directly inside `deobfuscators/` in pull requests.**
> 
> Any improvements, bug fixes, or lifting features for upstream deobfuscators should be submitted directly to their respective upstream repositories. Pull requests touching submodule file contents in this repository will be closed.

---

## Getting Started

### 1. Fork & Clone with Submodules

1. Fork this repository on GitHub.
2. Clone your fork locally using the `--recursive` flag to pull all submodules:
   ```bash
   git clone --recursive https://github.com/<your-username>/luraph-deobf.git
   cd luraph-deobf
   ```
3. If you cloned without `--recursive`, initialize and update the submodules:
   ```bash
   git submodule update --init --recursive
   ```

### 2. Set Up Virtual Environment

Ensure you have **Python 3.10+** and **Node.js 18+** installed:

```bash
# Create a Python virtual environment
python3 -m venv .venv

# Activate the virtual environment
# On Linux / macOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
```

Verify the environment:
```bash
python3 detector.py --help
python3 main.py --help
```

---

## Project Structure Overview

```
luraph-deobf/
├── main.py                  # Master CLI orchestrator & submodule engine router
├── detector.py              # Multi-version detection engine with structural AST heuristics
├── requirements.txt         # Development & testing dependencies (pytest, mypy, flake8)
├── README.md                # Main user documentation & usage guide
├── CONTRIBUTING.md          # Contributor guide & architecture documentation
├── LICENSE                  # MIT License
├── .gitignore               # Git ignore rules for builds, caches, and deobf artifacts
├── .gitmodules              # Submodule definitions for upstream engines
└── deobfuscators/           # Upstream deobfuscation engines (Git submodules)
    ├── v15_2/               # Luraph v15.2 engine
    ├── v15_1/               # Luraph v15.1/v15.0 Node.js/AST engine
    └── v14_v15/             # Luraph v14.x (14.7, 14.8, 14.9) Python engine
```

---

## How to Improve Detection Heuristics

All detection logic resides in `detector.py`. The detector relies on structural AST/bytecode patterns, standard library numeric slot mappings, root dispatch shape, and negative Bayesian exclusion penalties rather than simple string matching or header comments.

### Scoring Model & Bayesian Exclusions

1. **Root Construct:**
   - Luraph v15.x always boots via `return setmetatable({...}, ...)`. If present, v14.x candidates are penalized with `-100`.
   - Luraph v14.x boots via `return({...})` or `local init = (function(...) return({...}) end)(...)`. If setmetatable is absent, v15.x candidates are penalized with `-100`.
2. **Library Slots vs Native Bitwise:**
   - `v15.1` maps `bit32` methods in numeric table keys (`[90]=bit32.rshift`, `[99]=bit32.countlz`, `[113]=bit32.band`).
   - `v15.2` uses Luau native 64-bit integer bitwise operators and buffer deserialization (`buffer.writeu32`, `buffer.create`, `buffer.fromstring`).
3. **Sub-Version Specific Features (v14.x):**
   - `v14.7`: Seed table `Z = { ... }`, invocation suffix `}):g()(...)`, handler params `(H, K, g, N)`.
   - `v14.8`: Wrapper `local init = (function(...)`, invocation suffix `}):d()(...)`, handler params `(t, i)`.
   - `v14.9`: Seed table `O = { ... }`, invocation suffix `}):r()(...)`, handler params `(d, C, a, W)`.

### Debugging Detection with JSON Output

To debug how a file scores against all versions, run:

```bash
python detector.py <path/to/script.lua> --json
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

### Confidence Thresholds

- **1.00 Confidence:** Large margin between winner and runner-up ($\ge 40\%$ lead with winning score $\ge 40$), or unambiguous structural match + matching header.
- **0.90 Confidence:** Strong structural signature ($\ge 20\%$ lead with winning score $\ge 30$).
- **0.75 Confidence:** Moderate structural match ($\ge 10\%$ lead with winning score $\ge 20$).
- **0.00 / unknown:** Non-obfuscated script, deceptive header comment without structural evidence, or total score $\le 10$.

---

## How to Add a New Luraph Version

When integrating support for a new Luraph version (e.g. `v15.3`):

1. **Add Upstream Submodule (if separate repository):**
   ```bash
   git submodule add https://github.com/author/new-deobf deobfuscators/v15_3
   ```
2. **Add Detection Patterns to `detector.py`:**
   - Define compiled regex constants for unique structural features with descriptive comments explaining what they match and why.
   - Add `"v15.3"` to the candidate list in `detect_structural()`.
   - Implement positive pattern scoring and negative exclusion penalties.
   - Update `detect_from_header()` if header version strings are present.
3. **Add Engine Routing to `main.py`:**
   - Define a runner function (e.g. `run_v15_3()`) handling binary path resolution, subprocess execution, timeouts, and error handling.
   - Add the version to the CLI `--version` choices in `build_parser()`.
   - Route `target_version == "v15.3"` in `main.py`'s `main()` loop.
4. **Add Unit / Integration Tests:**
   - Test against full and comment-stripped samples.
   - Verify that clean/non-obfuscated Lua code still yields `unknown` (confidence `0.00`).
   - Verify `--json` output structure.
5. **Update Documentation:**
   - Update `README.md` to list the new version under Supported Versions and CLI usage examples.

---

## Code Style & Quality Guidelines

- **Python Standard:** Python 3.10+ syntax (union type syntax `A | B`, `from __future__ import annotations`).
- **Formatting & Style:** PEP 8 compliance.
- **Type Hints:** Fully annotate all public functions, classes, and helper methods. Run `mypy detector.py main.py` to ensure zero type errors.
- **No Hardcoded Absolute Paths:** All paths must be relative to `PROJECT_ROOT` or resolved dynamically using `Path(__file__).resolve().parent`.
- **No Extraneous Debug Output:** Progress and diagnostic logging should use `sys.stderr` or proper logging handlers so clean Lua code can be piped to stdout without corruption.

---

## Reporting a False Detection

If `detector.py` misclassifies or fails to identify an obfuscated script:

1. Run the detector in JSON mode:
   ```bash
   python detector.py <file.lua> --json > report.json
   ```
2. Open a GitHub Issue and include:
   - The generated `report.json` (contains pattern matches and score breakdowns without exposing your script's private payload).
   - If possible, a sanitized sample or snippet of the initialization header and footer (e.g., first 50 lines and last 10 lines).
   - The expected Luraph version (if known).

---

## Pull Request Checklist

Before submitting a Pull Request, please ensure the following checklist is satisfied:

- [ ] `detector.py` passes all existing test cases with $\ge 0.90$ (typically $1.00$) confidence on both full and comment-stripped scripts.
- [ ] New heuristics include code comments explaining what they match and why they are version-specific.
- [ ] No new false positives on plain/clean Lua scripts (must return `version: "unknown"`, `confidence: 0.00`).
- [ ] `--json` output strictly complies with the machine-readable schema (`version`, `confidence`, `detection_type`, `minified`, `scores`, `matched`, `excluded`).
- [ ] `main.py` handles the new version routing and returns proper exit codes (`0` on success, `1` on deobfuscation failure, `2` on unknown version / bad input).
- [ ] `README.md` and `CONTRIBUTING.md` are updated to reflect any new CLI flags, options, or supported versions.
- [ ] No files inside `deobfuscators/` submodules were modified.
- [ ] Code passes type-checking (`mypy`) and linting (`flake8`).
