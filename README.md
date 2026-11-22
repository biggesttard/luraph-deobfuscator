# Luraph Deobfuscator

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/node.js-18%2B-brightgreen?logo=node.js&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Versions](https://img.shields.io/badge/targets-v14.7%20%7C%20v14.8%20%7C%20v14.9%20%7C%20v15.1%20%7C%20v15.2-red)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

A multi-version static deobfuscation framework for **Luraph** — a Lua/Luau obfuscator widely used in Roblox exploit ecosystems. Automatically identifies the exact Luraph version using Bayesian-style heuristics, then dispatches to the matching engine for full devirtualization.

---

## Demo

**Input** — Luraph v15.2 protected script:

```lua
-- Luraph Obfuscator | lura.ph
return setmetatable({...}, {__index = function(t, k)
    local d = { ["\99\108\111\115"] = "\117\114\101", ... }
    local __MK = function(...) ... end
    -- VM chunk with encrypted constants, buffer deserialization ...
end})
```

**Detection:**

```
$ python detector.py sample.lua
Version : v15.2
Confidence : 1.00  (structural)
Minified : yes
```

**Deobfuscation:**

```
$ python main.py sample.lua -o clean.lua
[*] Detected Luraph v15.2 (confidence: 1.00)
[*] Dispatching to v15.2 engine...
[*] Lifting VM chunk...
[+] Done → clean.lua
```

```lua
-- Deobfuscated by Luraph Deobfuscator
local Players = game:GetService("Players")
local localPlayer = Players.LocalPlayer
local function onCharacterAdded(character)
    -- ... full readable Luau source recovered
end
```

---

## How It Works

The deobfuscator operates in two phases: detection, then engine dispatch.

```
┌──────────────────────────────┐
│   Luraph Protected Script    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 1. Version Detection         │ ➔ Bayesian scoring across AST patterns,
│                              │   structural fingerprints, exclusion rules
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 2. Engine Dispatch           │ ➔ Routes script to the matched version
│                              │   engine (v14_v15, v15_1, or v15_2)
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 3. Constant Decryption       │ ➔ Recovers encrypted string literals,
│                              │   numeric constants, and table slots
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 4. VM Devirtualization       │ ➔ Disassembles the embedded VM bytecode,
│                              │   maps opcode handlers, reconstructs ops
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 5. CFG / SSA Lifting         │ ➔ Reconstructs control flow, recovers
│                              │   locals, loops, closures, upvalues
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│   Clean Luau Source Code     │
└──────────────────────────────┘
```

1. **Version Detection** (`detector.py`): Scores the input script against all five Luraph versions using structural AST patterns and Bayesian exclusion penalties. Root construct divergence (`setmetatable({...})` for v15.x vs `return({...})` for v14.x) immediately eliminates half the candidates. Sub-version fingerprints (invocation suffixes `:g()` / `:d()` / `:r()`, seed table names `Z=` / `O=`, buffer ops for v15.2) narrow it to one. A header comment alone with zero structural evidence returns `unknown`.

2. **Engine Dispatch** (`main.py`): Routes to one of three engine submodules — `v14_v15` (covering v14.7, v14.8, v14.9), `v15_1`, or `v15_2`. Each engine is a specialized deobfuscation pipeline built for its version's exact bytecode format and VM layout.

3. **Constant Decryption**: Recovers encrypted string literals from the character substitution dictionary (`d={...}` in v15.2), numeric constants from scrambled table slots, and all data-encoding layers the engine uses to obscure immediate values.

4. **VM Devirtualization**: Disassembles the embedded VM instruction stream: extracts opcodes from the dispatcher, maps handlers via the opcode table, and reconstructs operand expressions. For v15.1, runs parallel devirtualization candidates with randomized seeds to handle non-deterministic scrambling.

5. **CFG / SSA Lifting**: Translates decoded bytecode back to readable Luau source. Recovers control flow structures (branches, loops), reassembles closures and upvalue captures, performs register-to-local assignment, and emits clean output targeting the Roblox Luau runtime.

---

## Supported Versions

| Luraph Version | Engine Submodule | Status | Key Capabilities |
|---|---|---|---|
| **v15.2** | `deobfuscators/v15_2` | Active | Buffer deserialization, behavior tracing, 3-level maker lifting |
| **v15.1 / v15.0** | `deobfuscators/v15_1` | Stable | Full devirtualization, CFG/SSA reconstruction, Roblox API local naming |
| **v14.9** | `deobfuscators/v14_v15` | Stable | `O={...}` seed table, `:r()` suffix dispatcher recovery |
| **v14.8** | `deobfuscators/v14_v15` | Stable | `local init = (function(...)` wrapper, `:d()` suffix dispatcher |
| **v14.7** | `deobfuscators/v14_v15` | Stable | `Z={...}` seed table, `:g()` suffix dispatcher recovery |

---

## Prerequisites

- **Python 3.10+** — CLI, detection, and lifting stages
- **Node.js 18+** — required by the v15.1 engine driver
- **Luau binaries** — prebuilt `luau` / `luau-ast` for Linux/Windows included in `deobfuscators/v15_1/bin/`; `main.py` syncs them on startup

---

## Quick Start

```bash
# Clone with all engine submodules
git clone --recursive https://github.com/biggesttard/luraph-deobfuscator.git
cd luraph-deobfuscator

# Install optional dev dependencies
pip install -r requirements.txt

# Deobfuscate a script (auto-detects version)
python main.py obfuscated.lua -o clean.lua

# Detect version only, no deobfuscation
python detector.py sample.lua

# Get a full JSON breakdown of detection scores
python detector.py sample.lua --json

# Force a specific version
python main.py input.lua -o clean.lua --version v15.2

# Behavior trace mode (fast, no devirt — reveals URLs, remotes, webhooks)
python main.py sample.lua -o trace.lua --no-devirt
```

If you cloned without `--recursive`, initialize submodules with:

```bash
git submodule update --init --recursive
```

---

## CLI Reference

| Flag | Description |
|---|---|
| `-o <file>` | Output path for deobfuscated Lua |
| `--detect-only` | Print detected version and exit |
| `--version <v>` | Force a version (`v14`, `v14.7`, `v15.1`, `v15.2`, …) |
| `--engine <e>` | Force a v14 sub-engine (`14.7`, `14.8`, `14.9`) |
| `--no-devirt` | Skip devirtualization — fast behavior trace only |
| `--fast` | Single-candidate devirt (v15.1); skips seed randomization |
| `--json` | Machine-readable JSON output from `detector.py` |
| `--debug` | Keep all intermediate files (VM dumps, proto maps, traces) |
| `-q` | Quiet — suppress progress, emit only deobfuscated code on stdout |

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success — output written |
| `1` | Engine failure or timeout |
| `2` | Invalid input or unknown version |

---

## Project Layout

```
luraph-deobfuscator/
├── main.py               CLI entry point and orchestrator
├── detector.py           Bayesian version detection engine
├── requirements.txt      Development dependencies
├── CONTRIBUTING.md       Contributor guidelines
├── LICENSE               MIT License
└── deobfuscators/
    ├── v15_2/            Luraph v15.2 engine
    ├── v15_1/            Luraph v15.1 / v15.0 engine
    └── v14_v15/          Luraph v14.7, v14.8, v14.9 engine
```

---

## How Version Detection Works

`detector.py` uses a Bayesian-style heuristic engine: structural AST patterns earn positive scores, and version-exclusive signatures trigger hard exclusion penalties of −100.

**Root construct divergence** instantly splits v14 from v15:
- `v15.x` — `return setmetatable({...}, ...)` at root → −100 on all v14 candidates
- `v14.x` — `return({...})` or `local init = (function(...)` → −100 on all v15 candidates

**Sub-version fingerprints** then separate within the surviving group:
- `v14.7`: suffix `}):g()(...)`, seed table `Z = { ... }`, params `(H, K, g, N)`
- `v14.8`: wrapper `local init = (function(...)`, suffix `}):d()(...)`
- `v14.9`: suffix `}):r()(...)`, seed table `O = { ... }`, params `(d, C, a, W)`
- `v15.1`: `bit32` slots (`[90]=bit32.rshift`), powers-of-2 table
- `v15.2`: `buffer.writeu32` / `buffer.create`, character dict `d={...}`, `__MK` hooks

A header comment (`-- Luraph Obfuscator`) boosts confidence on structurally validated scripts. A header alone with no structural evidence returns `unknown` (confidence `0.00`).

---

## Legal & Disclaimer

This project is intended strictly for **defensive reverse engineering, malware analysis, security research, and educational purposes**. Obfuscated Lua scripts in gaming ecosystems are frequently used to conceal malicious payloads — token stealers, remote-access backdoors, Discord webhook exfiltrators.

- Use this tool only on scripts you own or are authorized to analyze.
- This project is not affiliated with, endorsed by, or connected to Luraph, lura.ph, or Roblox Corporation.

---

## License

[MIT](LICENSE)
