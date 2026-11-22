"""Luraph version detection engine.

Analyzes Lua / Luau source code and detects Luraph obfuscator versions
(v14.7, v14.8, v14.9, v15.1, v15.2) using deep structural AST/bytecode
fingerprints, execution bootstrap analysis, VM handler density heuristics,
and Bayesian-style exclusion rules.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping


# =============================================================================
# Regular Expressions & Structural Fingerprints
# =============================================================================

# 1. Header & Comment Signatures
LURAPH_HEADER_RE = re.compile(
    r"--[^\n]*Luraph\s+Obfuscator\s+(?:v?(\d+)(?:\.(\d+))?(?:\.(\d+))?|(?:beta|alpha|free|test))",
    re.IGNORECASE,
)
LURAPH_URL_RE = re.compile(r"https?://lura\.ph/?", re.IGNORECASE)
LURAPH_LPH_OBF_RE = re.compile(r"(?:LPH[\|_]|\[=\[LPH|[\"']LPH|LPH\s*\{)")

# 2. Structural Root Patterns
SETMETATABLE_ROOT_RE = re.compile(
    r"return\s+setmetatable\s*\(",
    re.MULTILINE,
)
RETURN_TABLE_ROOT_RE = re.compile(
    r"return\s*\(\s*\{",
    re.MULTILINE,
)

# 3. VM Standard Library Mapping (Numeric Index Table)
VM_LIB_OP_MAP_RE = re.compile(
    r"\[\d+\]\s*=\s*(?:bit32|buffer|string|table|math|coroutine|Vector2|Vector3|Color3|UDim|UDim2|Instance|CFrame|task)\.\w+",
)
BIT32_MAP_ENTRY_RE = re.compile(r"\[\d+\]\s*=\s*bit32\.\w+")
BUFFER_MAP_ENTRY_RE = re.compile(r"\[\d+\]\s*=\s*buffer\.\w+")

# 4. v15.1 Specific Patterns
POW2_TABLE_RE = re.compile(
    r"\[0\]\s*=\s*1\s*,\s*2\s*,\s*4\s*,\s*8\s*,\s*16\s*,\s*32\s*,\s*64",
)

# 5. v15.2 Specific Patterns
V15_2_DICT_MAP_RE = re.compile(
    r"\bd\s*=\s*\{\s*\[\"[^\"]+\"\]\s*=\s*\"[^\"]{4,8}\"",
)
V15_2_MK_HOOKS_RE = re.compile(
    r"\b(?:E\.)?__MK\b",
)
V15_2_SCRIPT_KEY_RE = re.compile(
    r"getgenv\s*\(\s*\)\s*\.\s*SCRIPT_KEY\s*=",
)

# 6. v14.x VM Handler & Bytecode Dispatch Patterns
V14_4ARG_HANDLERS_RE = re.compile(
    r"\b[A-Za-z0-9_]+\s*=\s*function\s*\(\s*[A-Za-z0-9_]+(?:\s*,\s*[A-Za-z0-9_]+){3}\s*\)",
)
V14_ALL_HANDLERS_RE = re.compile(
    r"\b[A-Za-z0-9_]+\s*=\s*function\s*\(",
)
V14_NUMERIC_DISPATCH_RE = re.compile(
    r"\bif\s+[A-Za-z0-9_]+\s*<=\s*\d+\s+then",
)
V14_MODULO_ARITH_RE = re.compile(
    r"%\s*256",
)

# 7. v14 Sub-version Specific Signatures
# v14.7: invocation suffix `}):g()(...)`, seed table `Z = { ... }`, params `H,K,g,N`
V14_7_SUFFIX_G_RE = re.compile(r"\}\)\s*:\s*g\s*\(\s*\)")
V14_7_SEED_Z_RE = re.compile(r"\bZ\s*=\s*\{[^\}]*\b(?:0[xX][0-9a-fA-F]+|\d+)\b")
V14_7_PARAMS_HKGN_RE = re.compile(r"\bfunction\s*\(\s*H\s*,\s*K\s*,\s*g\s*,\s*N\s*\)")

# v14.8: bootstrap wrapper `local init = (function(...)`, invocation suffix `}):d()(...)`, params `t,i`
V14_8_INIT_BOOTSTRAP_RE = re.compile(r"local\s+init\s*=\s*\(?\s*function")
V14_8_SUFFIX_D_RE = re.compile(r"\}\)\s*:\s*d\s*\(\s*\)")
V14_8_PARAMS_TI_RE = re.compile(r"\bfunction\s*\(\s*t\s*,\s*i\s*\)")

# v14.9: invocation suffix `}):r()(...)`, seed table `O = { ... }`, params `d,C,a,W`
V14_9_SUFFIX_R_RE = re.compile(r"\}\)\s*:\s*r\s*\(\s*\)")
V14_9_SEED_O_RE = re.compile(r"\bO\s*=\s*\{[^\}]*\b(?:0[xX][0-9a-fA-F]+|\d+)\b")
V14_9_PARAMS_DCAW_RE = re.compile(r"\bfunction\s*\(\s*d\s*,\s*C\s*,\s*a\s*,\s*W\s*\)")

# Generic v14 seed / suffix
V14_ANY_SEEDS_RE = re.compile(
    r"=\s*\{(?:\s*0[xX][0-9a-fA-F]+|\s*\d+)(?:\s*,\s*(?:0[xX][0-9a-fA-F]+|\d+)){4,}\s*\}",
)
V14_ANY_SUFFIX_RE = re.compile(
    r"\}\)\s*:\s*[A-Za-z0-9_]+\s*\(\s*\)\s*\(\s*\.\.\.\s*\)\s*;?",
)


@dataclasses.dataclass
class DetectionResult:
    """Detection result holding version, confidence, and Bayesian scoring evidence."""
    version: str
    confidence: float
    detection_type: str  # "structural" | "header" | "unknown"
    minified: bool
    scores: dict[str, int]
    matched: dict[str, list[str]]
    excluded: dict[str, list[str]]

    def is_known(self) -> bool:
        """Return True if a known Luraph version was detected."""
        return self.version != "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "confidence": round(self.confidence, 2),
            "detection_type": self.detection_type,
            "minified": self.minified,
            "scores": self.scores,
            "matched": self.matched,
            "excluded": self.excluded,
        }


def check_minification(source: str) -> bool:
    """Detect whether script is minified (whitespace/newline stripped)."""
    if not source:
        return False
    length = len(source)
    if length < 200:
        return False
    newlines = source.count("\n")
    avg_line_len = length / max(newlines, 1)
    newlines_per_1k = (newlines / length) * 1000.0
    return avg_line_len > 400 or newlines_per_1k < 10.0


def normalize_tokens(text: str) -> str:
    """Strip string literals, comments, and normalize delimiters for AST matching."""
    text_no_str = re.sub(r'\[(=*)\[.*?\]\1\]', '', text, flags=re.DOTALL)
    text_no_str = re.sub(r'"(?:\\.|[^"\\])*"', '""', text_no_str)
    text_no_str = re.sub(r"'(?:\\.|[^'\\])*'", "''", text_no_str)
    return text_no_str


def detect_from_header(source: str) -> tuple[str | None, float]:
    """Inspect leading comments for explicit Luraph signature strings."""
    head_2k = source[:2048]
    m = LURAPH_HEADER_RE.search(head_2k)
    if m:
        major = m.group(1)
        minor = m.group(2)
        patch = m.group(3)
        if major == "15":
            if minor == "2" or (minor and int(minor) >= 2):
                return "v15.2", 1.00
            elif minor == "1":
                return "v15.1", 1.00
            elif minor == "0":
                return "v15.1", 0.95
            return "v15.1", 0.90
        elif major == "14":
            if minor == "7":
                return "v14.7", 1.00
            elif minor == "8":
                return "v14.8", 1.00
            elif minor == "9":
                return "v14.9", 1.00
            return "v14.9", 0.90
        elif major:
            return f"v{major}", 0.70

    if LURAPH_URL_RE.search(head_2k):
        return "luraph_generic", 0.60

    return None, 0.0


def detect_structural(source: str) -> DetectionResult:
    """Perform Bayesian-style structural scoring across all candidate Luraph versions."""
    is_minified = check_minification(source)

    head_16k = source[:16384]
    head_64k = source[:65536]
    tail_2k = source[-2048:] if len(source) > 2048 else source

    candidates = ["v15.2", "v15.1", "v14.7", "v14.8", "v14.9"]
    scores: dict[str, int] = {c: 0 for c in candidates}
    matched: dict[str, list[str]] = {c: [] for c in candidates}
    excluded: dict[str, list[str]] = {c: [] for c in candidates}

    # =========================================================================
    # Structural Extraction
    # =========================================================================

    has_setmetatable = bool(SETMETATABLE_ROOT_RE.search(head_16k)) or (
        "setmetatable" in head_16k and "return" in head_16k
    )
    has_return_table = bool(RETURN_TABLE_ROOT_RE.search(head_16k)) or bool(
        V14_8_INIT_BOOTSTRAP_RE.search(head_16k)
    )
    has_lph = "LPH" in source

    # Check for v15.x vs v14.x Root Divergence
    if has_setmetatable:
        # v15.x Root: return setmetatable({...}, ...)
        for v14_ver in ("v14.7", "v14.8", "v14.9"):
            scores[v14_ver] = -100
            excluded[v14_ver].append("root_setmetatable_present")

        scores["v15.1"] += 20
        scores["v15.2"] += 20
        matched["v15.1"].append("root_setmetatable")
        matched["v15.2"].append("root_setmetatable")

        # Map counts
        bit32_in_tbl = len(BIT32_MAP_ENTRY_RE.findall(source))
        buf_in_tbl = len(BUFFER_MAP_ENTRY_RE.findall(source))
        has_pow2 = bool(POW2_TABLE_RE.search(source))
        has_buf_u32 = "buffer.writeu32" in source
        has_buf_fromstring = "buffer.fromstring" in source
        has_script_key = bool(V15_2_SCRIPT_KEY_RE.search(head_16k))
        has_loadstring_tbl = (
            "[8]=loadstring" in head_16k or "[8] = loadstring" in head_16k
        )
        has_mk_hooks = bool(V15_2_MK_HOOKS_RE.search(head_64k))
        has_v15_2_dict = bool(V15_2_DICT_MAP_RE.search(head_64k))

        # v15.1 vs v15.2 Bayesian Divergence:
        # v15.1 maps extensive bit32 helpers in numeric slots ([90]=bit32.rshift, [99]=bit32.countlz...)
        # v15.2 relies purely on Luau native 64-bit integer bitwise operators and buffer deserialization.
        if bit32_in_tbl >= 3:
            scores["v15.1"] += 50
            scores["v15.2"] -= 40
            matched["v15.1"].append("bit32_numeric_slots")
            excluded["v15.2"].append("bit32_slots_penalty")
        elif bit32_in_tbl == 0 and buf_in_tbl >= 1:
            scores["v15.2"] += 50
            scores["v15.1"] -= 40
            matched["v15.2"].append("native_luau_bitops_no_bit32")
            excluded["v15.1"].append("no_bit32_slots_penalty")

        if has_pow2:
            scores["v15.1"] += 40
            matched["v15.1"].append("powers_of_2_table")

        if has_script_key:
            scores["v15.2"] += 30
            matched["v15.2"].append("script_key_injected")

        if has_loadstring_tbl:
            scores["v15.2"] += 20
            matched["v15.2"].append("mapped_loadstring_slot8")

        if has_mk_hooks:
            scores["v15.2"] += 30
            matched["v15.2"].append("mk_closure_hooks")

        if has_v15_2_dict and bit32_in_tbl == 0:
            scores["v15.2"] += 35
            matched["v15.2"].append("v15_2_character_dict")

        if has_buf_u32 and has_buf_fromstring:
            scores["v15.2"] += 25
            scores["v15.1"] += 25
            matched["v15.2"].append("buffer_u32_fromstring")
            matched["v15.1"].append("buffer_u32_fromstring")

        if has_lph:
            scores["v15.1"] += 15
            scores["v15.2"] += 15
            matched["v15.1"].append("lph_marker")
            matched["v15.2"].append("lph_marker")

    else:
        # v14.x or Unknown (No Root setmetatable)
        scores["v15.1"] = -100
        scores["v15.2"] = -100
        excluded["v15.1"].append("setmetatable_absent")
        excluded["v15.2"].append("setmetatable_absent")

        v14_4arg_count = len(V14_4ARG_HANDLERS_RE.findall(head_64k))
        v14_all_count = len(V14_ALL_HANDLERS_RE.findall(head_64k))
        has_num_disp = bool(V14_NUMERIC_DISPATCH_RE.search(head_64k))
        has_mod_arith = bool(V14_MODULO_ARITH_RE.search(head_64k)) and (
            "math.floor" in head_64k or "* 128" in head_64k or "* 16384" in head_64k or "* 2097152" in head_64k
            or "*128" in head_64k or "*16384" in head_64k or "*2097152" in head_64k
        )

        has_seed_z = bool(V14_7_SEED_Z_RE.search(head_16k)) or bool(V14_7_SUFFIX_G_RE.search(tail_2k))
        has_seed_o = bool(V14_9_SEED_O_RE.search(head_16k)) or bool(V14_9_SUFFIX_R_RE.search(tail_2k))
        has_seeds = has_seed_z or has_seed_o or bool(V14_ANY_SEEDS_RE.search(head_16k))

        has_v14_init = bool(V14_8_INIT_BOOTSTRAP_RE.search(head_16k))
        has_suffix_g = bool(V14_7_SUFFIX_G_RE.search(tail_2k))
        has_suffix_d = bool(V14_8_SUFFIX_D_RE.search(tail_2k))
        has_suffix_r = bool(V14_9_SUFFIX_R_RE.search(tail_2k))
        has_v14_suffix = (
            has_suffix_g or has_suffix_d or has_suffix_r or bool(V14_ANY_SUFFIX_RE.search(tail_2k))
        )

        has_hkg_n = len(V14_7_PARAMS_HKGN_RE.findall(head_64k)) >= 3
        has_dc_aw = len(V14_9_PARAMS_DCAW_RE.findall(head_64k)) >= 3
        has_ti = len(V14_8_PARAMS_TI_RE.findall(head_64k)) >= 1

        for v14_ver in ("v14.7", "v14.8", "v14.9"):
            if has_return_table:
                scores[v14_ver] += 30
                matched[v14_ver].append("return_table_root")
            if v14_4arg_count >= 8 or v14_all_count >= 10:
                scores[v14_ver] += 40
                matched[v14_ver].append("dense_opcode_handlers")
            if has_num_disp:
                scores[v14_ver] += 25
                matched[v14_ver].append("binary_jump_dispatch")
            if has_mod_arith:
                scores[v14_ver] += 25
                matched[v14_ver].append("modulo_arithmetic_unpacking")
            if has_seeds:
                scores[v14_ver] += 20
                matched[v14_ver].append("seed_table_present")
            if has_v14_suffix:
                scores[v14_ver] += 20
                matched[v14_ver].append("closing_invocation_suffix")

        # Sub-version discrimination
        if has_suffix_g or has_seed_z or has_hkg_n:
            scores["v14.7"] += 60
            scores["v14.8"] -= 30
            scores["v14.9"] -= 30
            matched["v14.7"].append("v14_7_suffix_g_or_seed_z")
        if has_v14_init or has_suffix_d or has_ti:
            scores["v14.8"] += 60
            scores["v14.7"] -= 30
            scores["v14.9"] -= 30
            matched["v14.8"].append("v14_8_init_bootstrap_or_suffix_d")
        if has_suffix_r or has_seed_o or has_dc_aw:
            scores["v14.9"] += 60
            scores["v14.7"] -= 30
            scores["v14.8"] -= 30
            matched["v14.9"].append("v14_9_suffix_r_or_seed_o")

    # =========================================================================
    # Evaluation & Confidence Computation
    # =========================================================================

    sorted_scores = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    winner, win_score = sorted_scores[0]
    runner_up_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0

    if win_score <= 10:
        return DetectionResult(
            version="unknown",
            confidence=0.0,
            detection_type="unknown",
            minified=is_minified,
            scores=scores,
            matched=matched,
            excluded=excluded,
        )

    # Bayesian margin gap
    gap = (win_score - runner_up_score) / max(win_score, 1)
    if gap >= 0.40 and win_score >= 40:
        confidence = 1.00
    elif gap >= 0.20 and win_score >= 30:
        confidence = 0.90
    elif gap >= 0.10 and win_score >= 20:
        confidence = 0.75
    else:
        confidence = 0.50

    return DetectionResult(
        version=winner,
        confidence=confidence,
        detection_type="structural",
        minified=is_minified,
        scores=scores,
        matched=matched,
        excluded=excluded,
    )


def detect(source: str | bytes | Path) -> DetectionResult:
    """Detect Luraph obfuscator version for the given script.

    Args:
        source: Lua / Luau source code as string, bytes, or Path.

    Returns:
        DetectionResult dataclass containing version, confidence, detection_type,
        minified flag, and scores breakdown.
    """
    if isinstance(source, Path) or (isinstance(source, str) and os.path.isfile(source)):
        with open(source, "rb") as fp:
            source_text = fp.read().decode("latin-1")
    elif isinstance(source, bytes):
        source_text = source.decode("latin-1")
    else:
        source_text = str(source)

    # Run structural detection first
    result = detect_structural(source_text)

    # Header check as confirmation / booster (never sole decider if structural is unknown)
    header_ver, header_conf = detect_from_header(source_text)
    if header_ver and result.version != "unknown":
        if header_ver == result.version or (header_ver.startswith("v14") and result.version.startswith("v14")):
            result.confidence = max(result.confidence, 1.00)
            result.matched[result.version].append(f"header_confirmation_{header_ver}")

    return result


def detect_version(source: str | bytes | Path) -> str:
    """Convenience function returning only the version string (e.g. 'v15.2', 'v15.1', 'v14.8')."""
    return detect(source).version


# =============================================================================
# CLI Interface
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="detector.py",
        description="Luraph obfuscator version detector with structural AST & Bayesian scoring.",
    )
    parser.add_argument("file", help="Path to Lua/Luau script")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON schema")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    res = detect(Path(args.file))

    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"Detected: {res.version} (confidence: {res.confidence:.2f}, minified: {res.minified})")
        print(f"Scores:   {res.scores}")

    return 0 if res.version != "unknown" else 1


if __name__ == "__main__":
    sys.exit(main())
