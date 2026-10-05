"""Exploratory v5 integer-sample timing-offset benchmark for the synthetic codec.

A constant integer sample-phase offset changes the receiver's 64-sample window
starts while leaving the transmitter, sample rate, carrier frequency, and
original decoder unchanged. Zero guards define the finite-frame boundaries.
"""

from __future__ import annotations

import csv
import json
import math
import platform
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from digital_to_wave import WaveConfig, decode_wave, encode_wave
from robustness_benchmark_v2 import (
    MASTER_SEED as V2_MASTER_SEED,
    VECTOR_SEED,
    build_input_patterns,
    wilson_interval,
)
from robustness_benchmark_v3 import MASTER_SEED as V3_MASTER_SEED
from robustness_benchmark_v4 import MASTER_SEED as V4_MASTER_SEED


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
TRIALS_PER_VECTOR_PER_CONDITION = 2_000
MASTER_SEED = 20261007
TOLERANCE = 0.25
VECTOR_LENGTH = 32
SAMPLES_PER_SYMBOL = 64
CYCLES_PER_SYMBOL = 4
AMPLITUDE_MIN = 1.0
NOISE_STD_LEVELS = (0.0, 0.45)
# Constant integer timing phase (early/late); no sample-rate drift.
TIMING_OFFSETS_SAMPLES = (-8, -4, -2, -1, 0, 1, 2, 4, 8)
GUARD_SAMPLES = SAMPLES_PER_SYMBOL
CHUNK_FRAMES = 128
POOLED_PATTERN = "POOLED_ALL_VECTORS"
METHODS = ("existing_nominal_decoder", "oracle_exact_timing")
EXPECTED_PATTERN_NAMES = (
    "mixed_signs",
    "sparse_and_zeros",
    "boundary_values",
    "randomized_1",
    "randomized_2",
    "randomized_3",
)
CSV_FIELDS = (
    "timing_offset_samples", "timing_offset_fraction_of_symbol", "timing_offset_percent_of_symbol",
    "noise_std", "vector_pattern", "method", "frames", "components", "frames_passing",
    "frame_pass_share", "wilson95_lower", "wilson95_upper", "uncertainty_kind",
    "empirical_mae", "empirical_rmse", "empirical_mean_bias", "empirical_variance",
    "theory_frame_pass_probability", "abs_pass_probability_gap",
)


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or int(value) < 1:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _finite_nonnegative(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite and non-negative") from exc
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _validate_nonnegative_levels(values: Iterable[float], label: str) -> tuple[float, ...]:
    try:
        levels = tuple(_finite_nonnegative(value, label) for value in values)
    except TypeError as exc:
        raise ValueError(f"{label} levels must be a non-empty iterable") from exc
    if not levels or len(set(levels)) != len(levels):
        raise ValueError(f"{label} levels must be non-empty and unique")
    return levels


def _validate_offsets(values: Iterable[int]) -> tuple[int, ...]:
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise ValueError("timing offsets must be a non-empty iterable of integers") from exc
    if not raw or any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) for value in raw):
        raise ValueError("timing offsets must be a non-empty iterable of integers")
    offsets = tuple(int(value) for value in raw)
    if len(set(offsets)) != len(offsets) or 0 not in offsets:
        raise ValueError("timing offsets must be unique and include zero")
    if max(abs(value) for value in offsets) > GUARD_SAMPLES:
        raise ValueError("absolute timing offset must not exceed the zero-guard length")
    return offsets


def nominal_template(config: WaveConfig = WaveConfig()) -> np.ndarray:
    """Return the unchanged receiver's local q[n]=sin(omega*n+pi/4) template."""
    n = np.arange(config.samples_per_symbol, dtype=float)
    omega = 2.0 * math.pi * config.cycles_per_symbol / config.samples_per_symbol
    return np.sin(omega * n + math.pi / 4.0)


def window_indices(
    timing_offset_samples: int,
    *,
    method: str,
    config: WaveConfig = WaveConfig(),
    vector_length: int = VECTOR_LENGTH,
    guard_samples: int = GUARD_SAMPLES,
) -> np.ndarray:
    """Return disjoint symbol windows from the zero-guarded serialized frame.

    The existing receiver uses offset window starts. The timing-aware oracle
    uses the true transmitted symbol boundaries after using its known offset.
    """
    if isinstance(timing_offset_samples, (bool, np.bool_)) or not isinstance(timing_offset_samples, (int, np.integer)):
        raise ValueError("timing_offset_samples must be an integer")
    offset = int(timing_offset_samples)
    if abs(offset) > GUARD_SAMPLES:
        raise ValueError("absolute timing offset must not exceed the zero-guard length")
    count = _positive_integer(vector_length, "vector_length")
    guard = _positive_integer(guard_samples, "guard_samples")
    if method not in METHODS:
        raise ValueError("method must be an existing decoder or exact-timing oracle")
    shift = offset if method == "existing_nominal_decoder" else 0
    starts = guard + np.arange(count, dtype=int) * config.samples_per_symbol + shift
    indices = starts[:, None] + np.arange(config.samples_per_symbol, dtype=int)[None, :]
    stream_size = 2 * guard + count * config.samples_per_symbol
    if np.any(indices < 0) or np.any(indices >= stream_size):
        raise ValueError("window indices exceed the finite zero-guarded stream")
    return indices


def theoretical_frame_pass_probability(
    component_bias: Any,
    noise_std: float,
    tolerance: float = TOLERANCE,
    template_energy: float = 32.0,
) -> float:
    """Compute a frame probability for independent Gaussian projection errors."""
    bias = np.asarray(component_bias, dtype=float)
    sigma = _finite_nonnegative(noise_std, "noise_std")
    tau = _finite_nonnegative(tolerance, "tolerance")
    energy = _finite_nonnegative(template_energy, "template_energy")
    if bias.ndim != 1 or bias.size < 1 or not np.all(np.isfinite(bias)):
        raise ValueError("component_bias must be a non-empty finite vector")
    if energy <= 0.0:
        raise ValueError("template_energy must be positive")
    if sigma == 0.0:
        return float(np.all(np.abs(bias) <= tau))
    component_sd = sigma / math.sqrt(energy)
    probabilities = []
    for mean in bias:
        upper = 0.5 * (1.0 + math.erf((tau - float(mean)) / (math.sqrt(2.0) * component_sd)))
        lower = 0.5 * (1.0 + math.erf((-tau - float(mean)) / (math.sqrt(2.0) * component_sd)))
        probabilities.append(max(0.0, min(1.0, upper - lower)))
    return float(np.prod(probabilities))


def _error_summary(errors: np.ndarray) -> dict[str, float | int]:
    if errors.ndim != 2 or errors.shape[0] < 1 or errors.shape[1] < 1 or not np.all(np.isfinite(errors)):
        raise ValueError("errors must be a non-empty finite frame-by-component array")
    absolute = np.abs(errors)
    passing = np.all(absolute <= TOLERANCE, axis=1)
    return {
        "frames": int(errors.shape[0]),
        "components": int(errors.size),
        "frames_passing": int(np.count_nonzero(passing)),
        "frame_pass_share": float(np.mean(passing)),
        "empirical_mae": float(np.mean(absolute)),
        "empirical_rmse": float(np.sqrt(np.mean(errors * errors))),
        "empirical_mean_bias": float(np.mean(errors)),
        "empirical_variance": float(np.var(errors, ddof=0)),
    }


def _make_row(
    offset: int,
    sigma: float,
    pattern: str,
    method: str,
    errors: np.ndarray,
    theory_probability: float,
    *,
    stochastic: bool,
) -> dict[str, Any]:
    summary = _error_summary(errors)
    if stochastic:
        lower, upper = wilson_interval(summary["frames_passing"], summary["frames"])
        uncertainty = "two-sided 95% Wilson interval; conditional on fixed vector panel and synthetic IID draws"
    else:
        lower, upper = None, None
        uncertainty = "deterministic; no sampling interval"
    return {
        "timing_offset_samples": int(offset),
        "timing_offset_fraction_of_symbol": float(offset / SAMPLES_PER_SYMBOL),
        "timing_offset_percent_of_symbol": float(100.0 * offset / SAMPLES_PER_SYMBOL),
        "noise_std": float(sigma),
        "vector_pattern": pattern,
        "method": method,
        **summary,
        "wilson95_lower": lower,
        "wilson95_upper": upper,
        "uncertainty_kind": uncertainty,
        "theory_frame_pass_probability": float(theory_probability),
        "abs_pass_probability_gap": abs(float(summary["frame_pass_share"]) - float(theory_probability)),
    }


def _clean_stream(reference: np.ndarray, config: WaveConfig, guard_samples: int) -> np.ndarray:
    waveform = encode_wave(reference, config).reshape(-1)
    return np.pad(waveform, (guard_samples, guard_samples), mode="constant", constant_values=0.0)


def run_timing_benchmark(
    trials_per_vector_per_condition: int = TRIALS_PER_VECTOR_PER_CONDITION,
    master_seed: int = MASTER_SEED,
    timing_offsets: Iterable[int] = TIMING_OFFSETS_SAMPLES,
    noise_levels: Iterable[float] = NOISE_STD_LEVELS,
    chunk_frames: int = CHUNK_FRAMES,
) -> dict[str, Any]:
    """Run seeded fixed-offset timing stress with paired and bounded trials."""
    trials = _positive_integer(trials_per_vector_per_condition, "trials_per_vector_per_condition")
    chunk = _positive_integer(chunk_frames, "chunk_frames")
    if isinstance(master_seed, (bool, np.bool_)) or not isinstance(master_seed, (int, np.integer)):
        raise ValueError("master_seed must be an integer")
    seed = int(master_seed)
    if seed in (int(V2_MASTER_SEED), int(V3_MASTER_SEED), int(V4_MASTER_SEED)):
        raise ValueError("v5 master seed must differ from v2, v3, and v4")
    offsets = _validate_offsets(timing_offsets)
    noise_stds = _validate_nonnegative_levels(noise_levels, "noise_std")
    if 0.0 not in noise_stds or NOISE_STD_LEVELS[-1] not in noise_stds:
        raise ValueError("the frozen v5 conditions require clean and 0.45 AWGN controls")

    config = WaveConfig(SAMPLES_PER_SYMBOL, CYCLES_PER_SYMBOL, AMPLITUDE_MIN)
    q = nominal_template(config)
    energy = float(q @ q)
    if not math.isclose(energy, 32.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("unexpected nominal template energy")
    patterns = build_input_patterns()
    if tuple(patterns) != EXPECTED_PATTERN_NAMES or any(len(value) != VECTOR_LENGTH for value in patterns.values()):
        raise RuntimeError("the fixed six-vector panel no longer matches the v5 protocol")

    rows: list[dict[str, Any]] = []
    for offset_index, offset in enumerate(offsets):
        indices_by_method = {
            method: window_indices(offset, method=method, config=config, vector_length=VECTOR_LENGTH)
            for method in METHODS
        }
        for sigma in noise_stds:
            errors_by_method: dict[str, dict[str, np.ndarray]] = {method: {} for method in METHODS}
            pattern_theory: dict[str, dict[str, float]] = {method: {} for method in METHODS}
            for pattern_index, (pattern_name, reference) in enumerate(patterns.items()):
                clean = _clean_stream(reference, config, GUARD_SAMPLES)
                bias_by_method = {
                    method: decode_wave(clean[indices_by_method[method]], config) - reference
                    for method in METHODS
                }
                actual_trials = 1 if sigma == 0.0 else trials
                rng = np.random.default_rng(np.random.SeedSequence([seed, offset_index, pattern_index]))
                chunks: dict[str, list[np.ndarray]] = {method: [] for method in METHODS}
                completed = 0
                while completed < actual_trials:
                    batch_size = min(chunk, actual_trials - completed)
                    if sigma == 0.0:
                        received = clean[None, :]
                    else:
                        noise = rng.normal(0.0, sigma, size=(batch_size, clean.size))
                        received = clean[None, :] + noise
                    for method in METHODS:
                        windows = received[:, indices_by_method[method]]
                        estimates = decode_wave(windows.reshape(-1, SAMPLES_PER_SYMBOL), config).reshape(batch_size, VECTOR_LENGTH)
                        chunks[method].append(estimates - reference[None, :])
                    completed += batch_size

                for method in METHODS:
                    errors = np.concatenate(chunks[method], axis=0)
                    errors_by_method[method][pattern_name] = errors
                    probability = theoretical_frame_pass_probability(bias_by_method[method], sigma, template_energy=energy)
                    pattern_theory[method][pattern_name] = probability
                    rows.append(_make_row(
                        offset, sigma, pattern_name, method, errors, probability,
                        stochastic=(sigma > 0.0),
                    ))

            for method in METHODS:
                pooled_errors = np.concatenate(list(errors_by_method[method].values()), axis=0)
                pooled_probability = float(np.mean(list(pattern_theory[method].values())))
                rows.append(_make_row(
                    offset, sigma, POOLED_PATTERN, method, pooled_errors, pooled_probability,
                    stochastic=(sigma > 0.0),
                ))

    # Weak zero-output floor, evaluated once on the same fixed inputs.
    floor_offset = 0
    floor_sigma_context = NOISE_STD_LEVELS[-1]
    floor_rows = []
    for pattern_name, reference in patterns.items():
        errors = -np.asarray(reference, dtype=float)[None, :]
        row = _make_row(
            floor_offset, floor_sigma_context, pattern_name, "weak_zero_output_floor",
            errors, float(np.all(np.abs(errors[0]) <= TOLERANCE)), stochastic=False,
        )
        rows.append(row)
        floor_rows.append(row)
    floor_errors = np.concatenate([-np.asarray(v, dtype=float)[None, :] for v in patterns.values()], axis=0)
    rows.append(_make_row(
        floor_offset, floor_sigma_context, POOLED_PATTERN, "weak_zero_output_floor",
        floor_errors, float(np.mean([row["theory_frame_pass_probability"] for row in floor_rows])),
        stochastic=False,
    ))

    full_protocol = (
        trials == TRIALS_PER_VECTOR_PER_CONDITION
        and seed == MASTER_SEED
        and offsets == TIMING_OFFSETS_SAMPLES
        and noise_stds == NOISE_STD_LEVELS
        and chunk == CHUNK_FRAMES
    )
    total_stochastic_frames = len(offsets) * len(patterns) * trials
    contract = {
        "classification": "arbitrary integer-sample timing-offset stress in a synthetic dimensionless software test; no physical channel claim",
        "protocol_status": "v5 exploratory fixed integer-sample timing-offset sweep; conditions frozen in source before full run; not a formal preregistration or physical validation",
        "full_protocol_run": full_protocol,
        "conditions_frozen_before_run": True,
        "preservation": "signed encoder and all v1-v4 sources, tests, reports, and result artifacts are used without modification",
        "master_seed": seed,
        "v2_master_seed": int(V2_MASTER_SEED),
        "v3_master_seed": int(V3_MASTER_SEED),
        "v4_master_seed": int(V4_MASTER_SEED),
        "randomized_vector_seed": int(VECTOR_SEED),
        "trials_per_vector_per_timing_offset": trials,
        "chunk_frames": chunk,
        "vector_length": VECTOR_LENGTH,
        "vector_patterns": {name: np.asarray(vector, dtype=float).tolist() for name, vector in patterns.items()},
        "samples_per_symbol": config.samples_per_symbol,
        "cycles_per_symbol": config.cycles_per_symbol,
        "nominal_angular_frequency_radians_per_sample": 2.0 * math.pi * config.cycles_per_symbol / config.samples_per_symbol,
        "phase_radians": math.pi / 4.0,
        "negative_encoder_phase_radians": 5.0 * math.pi / 4.0,
        "amplitude_min": config.amplitude_min,
        "nominal_template_energy": energy,
        "input_range_dimensionless": [-2.0, 2.0],
        "noise_model": {
            "name": "iid_gaussian_sample_noise_on_finite_guarded_stream",
            "sample_standard_deviation_levels_dimensionless": list(noise_stds),
            "independent_across_stream_samples_and_frames": True,
            "construction": "seeded NumPy normal draws over each complete zero-guarded serialized waveform; both receivers use the same noisy stream",
        },
        "timing_offset_model": {
            "name": "constant_integer_sample_receiver_window_offset",
            "offset_samples_levels": list(offsets),
            "fraction_of_64_sample_symbol": [float(value / SAMPLES_PER_SYMBOL) for value in offsets],
            "offset_sign_convention": "positive means receiver windows start late; negative means they start early",
            "sample_rate_offset": "none; the integer timing phase remains constant for every symbol; no clock-rate drift or interpolation is modeled",
            "carrier_frequency_offset": "none",
            "waveform_serialization": "concatenate the existing 64-sample encoder segments in frame order, then prepend/append 64 zero-valued guard samples; no pulse shaping or other waveform change",
            "receiver_window_rule": "nominal decoder uses [guard + k*64 + offset, guard + k*64 + offset + 63]; guard padding makes early/late frame-edge samples defined and prevents circular wrap",
            "guard_samples_each_side": GUARD_SAMPLES,
            "oracle_window_rule": "timing-aware oracle knows the exact fixed offset and extracts the true nominal windows [guard + k*64, guard + k*64 + 63]",
            "level_basis": "small discrete sample-offset stress grid selected for this software test only; no measured timing channel or hardware specification",
        },
        "decoder_methods": {
            "existing_nominal_decoder": "unchanged digital_to_wave.decode_wave applied to windows shifted by the declared integer offset; it receives no timing correction",
            "oracle_exact_timing": "analysis-only upper-bound reference supplied the exact offset and frame boundary; it reselects the true symbol windows, then uses the unchanged nominal projection; not a timing-recovery implementation",
            "weak_zero_output_floor": "always returns zeros; recorded once against each fixed vector; ignores the received waveform and is not a competing decoder",
        },
        "tolerance_dimensionless": TOLERANCE,
        "frame_pass_rule": "inclusive: all 32 absolute component errors must be <= 0.25",
        "frame_counts": {
            "noisy_monte_carlo_input_frames_per_offset": len(patterns) * trials,
            "total_noisy_monte_carlo_input_frames": total_stochastic_frames,
            "clean_deterministic_input_frames_per_offset": len(patterns),
            "weak_floor_fixed_vectors": len(patterns),
        },
        "seed_streams": "NumPy SeedSequence([master_seed, offset_index, vector_index]); paired receiver methods share each complete noisy stream",
        "analytic_calibration": {
            "projection_noise": "each 64-sample receiver window has independent IID noise and q dot q=32, so the decoded noise SD is sigma/sqrt(32)",
            "nominal_bias": "computed exactly by applying the unchanged projection to the clean, zero-guarded stream at the shifted window indices; adjacent-symbol and guard samples are included",
            "oracle_bias": "numerical roundoff only; true segment windows are reselected using exact timing knowledge",
            "frame_probability": "product over 32 disjoint component windows of P(-0.25 <= Normal(bias_k,sigma/sqrt(32)) <= 0.25); at sigma=0 use the deterministic inclusive pass rule",
            "pooled_probability": "equal-weight mean of the six fixed-pattern theoretical frame probabilities; pooled Wilson interval is conditional on this vector panel",
        },
        "source_basis": [
            {"url": "https://www.mathworks.com/help/comm/ref/comm.symbolsynchronizer-system-object.html", "relevance": "documents timing synchronization as correction of receiver symbol-timing clock skew and demonstrates fixed timing error"},
            {"url": "https://cioffi-group.stanford.edu/doc/book/chap6.pdf", "relevance": "communications textbook treatment of symbol-timing synchronization and timing recovery"},
            {"url": "https://uk.mathworks.com/help/satcom/ug/ccsds-hdr-optical-link-simulation-for-1550nm.html", "relevance": "distinguishes sample-clock offset from carrier-frequency offset and describes timing recovery"},
        ],
        "metric_definitions": {
            "frame_pass_share": "passing frames divided by frames; pass iff every absolute component error is <= 0.25",
            "confidence_interval": "two-sided 95% Wilson score interval for Monte Carlo pass shares; deterministic clean/floor rows have no interval",
            "uncertainty_scope": "intervals quantify IID simulation variation conditional on the six fixed vectors and stipulated synthetic model, not model or physical uncertainty",
            "component_errors": "empirical MAE, RMSE, mean signed error, and population variance over decoded components",
        },
        "expected_total_stochastic_input_frames": total_stochastic_frames,
        "software_versions": {"python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib.__version__},
    }
    result = {"benchmark": "synthetic_integer_sample_timing_stress_v5", "contract": contract, "results": rows}
    validate_timing_result(result)
    return result


def _close(a: float, b: float, atol: float = 1e-11) -> bool:
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=atol)


def validate_timing_result(result: dict[str, Any]) -> None:
    """Check v5 manifest, method rows, uncertainty, and equal-pattern pools."""
    if not isinstance(result, dict) or result.get("benchmark") != "synthetic_integer_sample_timing_stress_v5":
        raise ValueError("unexpected v5 benchmark identifier")
    contract, rows = result.get("contract"), result.get("results")
    if not isinstance(contract, dict) or not isinstance(rows, list) or not rows:
        raise ValueError("result must contain a contract and non-empty results")
    if contract.get("conditions_frozen_before_run") is not True or "not a formal preregistration" not in contract.get("protocol_status", ""):
        raise ValueError("v5 conditions must be frozen, while remaining exploratory")
    for key in ("master_seed", "v2_master_seed", "v3_master_seed", "v4_master_seed"):
        value = contract.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("all v5 manifest seeds must be integers")
    seed = contract["master_seed"]
    if seed in (V2_MASTER_SEED, V3_MASTER_SEED, V4_MASTER_SEED):
        raise ValueError("v5 seed must be distinct from v2-v4")
    patterns = contract.get("vector_patterns")
    if not isinstance(patterns, dict) or tuple(patterns) != EXPECTED_PATTERN_NAMES:
        raise ValueError("manifest must retain the six fixed vectors in order")
    if any(not isinstance(v, list) or len(v) != VECTOR_LENGTH or any(not math.isfinite(float(x)) or abs(float(x)) > 2.0 for x in v) for v in patterns.values()):
        raise ValueError("manifest vectors violate the dimensionless input contract")
    offsets = _validate_offsets(contract.get("timing_offset_model", {}).get("offset_samples_levels", ()))
    noise = _validate_nonnegative_levels(contract.get("noise_model", {}).get("sample_standard_deviation_levels_dimensionless", ()), "noise_std")
    if 0.0 not in noise or NOISE_STD_LEVELS[-1] not in noise:
        raise ValueError("manifest must retain clean and 0.45 AWGN controls")
    trials = _positive_integer(contract.get("trials_per_vector_per_timing_offset"), "trials_per_vector_per_timing_offset")
    expected_stochastic = len(offsets) * len(patterns) * trials
    if contract.get("expected_total_stochastic_input_frames") != expected_stochastic:
        raise ValueError("total stochastic frame count is inconsistent")
    full = (
        trials == TRIALS_PER_VECTOR_PER_CONDITION and seed == MASTER_SEED
        and offsets == TIMING_OFFSETS_SAMPLES and noise == NOISE_STD_LEVELS
        and contract.get("chunk_frames") == CHUNK_FRAMES
    )
    if contract.get("full_protocol_run") is not full:
        raise ValueError("full-protocol flag disagrees with the run conditions")
    if contract.get("tolerance_dimensionless") != TOLERANCE or contract.get("vector_length") != VECTOR_LENGTH:
        raise ValueError("v5 tolerance or vector length differs from the locked conditions")

    expected_keys = set()
    for offset in offsets:
        for sigma in noise:
            for method in METHODS:
                for pattern in list(patterns) + [POOLED_PATTERN]:
                    expected_keys.add((offset, sigma, method, pattern))
    for pattern in list(patterns) + [POOLED_PATTERN]:
        expected_keys.add((0, NOISE_STD_LEVELS[-1], "weak_zero_output_floor", pattern))

    row_map: dict[tuple[int, float, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or any(field not in row for field in CSV_FIELDS):
            raise ValueError("a v5 row is missing required fields")
        offset = row["timing_offset_samples"]
        key = (offset, float(row["noise_std"]), row["method"], row["vector_pattern"])
        if key in row_map:
            raise ValueError("duplicate v5 result row")
        if key not in expected_keys:
            raise ValueError("result row is outside the declared v5 grid")
        floor = row["method"] == "weak_zero_output_floor"
        frames = 1 if (key[1] == 0.0 or floor) else trials
        if key[3] == POOLED_PATTERN:
            frames *= len(patterns)
        if row["frames"] != frames or row["components"] != frames * VECTOR_LENGTH:
            raise ValueError("frame or component count disagrees with the manifest")
        successes = row["frames_passing"]
        if isinstance(successes, bool) or not isinstance(successes, int) or not 0 <= successes <= frames:
            raise ValueError("invalid pass count")
        if not _close(row["frame_pass_share"], successes / frames):
            raise ValueError("pass share disagrees with pass count")
        if not _close(row["timing_offset_fraction_of_symbol"], offset / SAMPLES_PER_SYMBOL) or not _close(row["timing_offset_percent_of_symbol"], 100 * offset / SAMPLES_PER_SYMBOL):
            raise ValueError("offset normalization is inconsistent")
        theory = float(row["theory_frame_pass_probability"])
        if not 0.0 <= theory <= 1.0 or not _close(row["abs_pass_probability_gap"], abs(row["frame_pass_share"] - theory)):
            raise ValueError("theoretical probability or absolute gap is inconsistent")
        stochastic = key[1] > 0.0 and not floor
        lower, upper = row["wilson95_lower"], row["wilson95_upper"]
        if stochastic:
            expected_ci = wilson_interval(successes, frames)
            if lower is None or upper is None or not _close(lower, expected_ci[0]) or not _close(upper, expected_ci[1]) or "Wilson" not in row["uncertainty_kind"]:
                raise ValueError("stochastic result has incorrect or missing Wilson interval")
        elif lower is not None or upper is not None or "deterministic" not in row["uncertainty_kind"]:
            raise ValueError("deterministic result must not report a sampling interval")
        row_map[key] = row
    if set(row_map) != expected_keys:
        raise ValueError("v5 rows do not cover exactly the frozen conditions and floor")

    for offset in offsets:
        for sigma in noise:
            for method in METHODS:
                members = [row_map[(offset, sigma, method, name)] for name in patterns]
                pooled = row_map[(offset, sigma, method, POOLED_PATTERN)]
                if pooled["frames_passing"] != sum(row["frames_passing"] for row in members):
                    raise ValueError("pooled pass count disagrees with pattern rows")
                if not _close(pooled["theory_frame_pass_probability"], sum(row["theory_frame_pass_probability"] for row in members) / len(members)):
                    raise ValueError("pooled theoretical probability is not equal-pattern mean")
                for field in ("empirical_mae", "empirical_mean_bias"):
                    if not _close(pooled[field], sum(float(row[field]) for row in members) / len(members)):
                        raise ValueError(f"pooled {field} disagrees with pattern rows")
                expected_rmse = math.sqrt(sum(float(row["empirical_rmse"]) ** 2 for row in members) / len(members))
                if not _close(pooled["empirical_rmse"], expected_rmse):
                    raise ValueError("pooled RMSE disagrees with pattern rows")


def write_timing_outputs(result: dict[str, Any], output_dir: Path = ARTIFACTS) -> tuple[Path, Path, Path]:
    """Write v5 protocol/results JSON, CSV, and pass/error plot."""
    validate_timing_result(result)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "robustness-benchmark-v5-timing.json"
    csv_path = output_dir / "robustness-benchmark-v5-timing.csv"
    plot_path = output_dir / "robustness-benchmark-v5-timing.png"
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(result["results"])

    pooled = [r for r in result["results"] if r["vector_pattern"] == POOLED_PATTERN]
    noisy = sorted((r for r in pooled if r["noise_std"] == NOISE_STD_LEVELS[-1]), key=lambda r: r["timing_offset_samples"])
    clean = sorted((r for r in pooled if r["noise_std"] == 0.0), key=lambda r: r["timing_offset_samples"])
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2), constrained_layout=False)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.86, bottom=0.27, wspace=0.23)
    colors = {METHODS[0]: "#277da1", METHODS[1]: "#f3722c"}
    labels = {METHODS[0]: "existing nominal decoder", METHODS[1]: "oracle: exact timing known"}
    for method in METHODS:
        rows = [row for row in noisy if row["method"] == method]
        x = np.asarray([row["timing_offset_samples"] for row in rows])
        rates = np.asarray([row["frame_pass_share"] for row in rows])
        lower = np.asarray([row["wilson95_lower"] for row in rows])
        upper = np.asarray([row["wilson95_upper"] for row in rows])
        axes[0].errorbar(x, rates,
                         yerr=np.vstack((np.maximum(0.0, rates - lower), np.maximum(0.0, upper - rates))),
                         fmt="o", capsize=3, color=colors[method],
                         label=f"{labels[method]}: observed 95% Wilson CI")
        axes[0].plot(x, [row["theory_frame_pass_probability"] for row in rows], "-",
                     color=colors[method], alpha=0.7, label=f"{labels[method]}: analytic prediction")
    axes[0].set(xlabel="constant receiver window offset (samples; + = late)", ylabel="32-value frames passing",
                ylim=(-0.03, 1.03), title="AWGN SD 0.45; six fixed vectors", xticks=TIMING_OFFSETS_SAMPLES)
    axes[0].grid(alpha=0.22)
    axes[0].legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2)
    for method in METHODS:
        rows = [row for row in clean if row["method"] == method]
        axes[1].plot([row["timing_offset_samples"] for row in rows], [row["empirical_mae"] for row in rows],
                     marker="o", color=colors[method], label=labels[method])
    axes[1].set(xlabel="constant receiver window offset (samples; + = late)", ylabel="component MAE (dimensionless)",
                title="Clean deterministic frames", xticks=TIMING_OFFSETS_SAMPLES)
    axes[1].grid(alpha=0.22)
    axes[1].legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2)
    fig.suptitle("v5 synthetic integer-sample timing stress — no physical validity claimed")
    fig.savefig(plot_path, dpi=180, facecolor="white")
    plt.close(fig)
    return json_path, csv_path, plot_path


def main() -> int:
    result = run_timing_benchmark()
    json_path, csv_path, plot_path = write_timing_outputs(result)
    print(
        f"v5 timing sweep: {len(EXPECTED_PATTERN_NAMES)} fixed vectors x "
        f"{TRIALS_PER_VECTOR_PER_CONDITION:,} frames x {len(TIMING_OFFSETS_SAMPLES)} offsets "
        f"at SD=0.45 = {result['contract']['expected_total_stochastic_input_frames']:,} noisy input frames; "
        f"seed={MASTER_SEED}"
    )
    for row in result["results"]:
        if row["method"] == METHODS[0] and row["noise_std"] == 0.45 and row["vector_pattern"] == POOLED_PATTERN:
            print(
                f"offset={row['timing_offset_samples']:+d} samples ({row['timing_offset_percent_of_symbol']:+.3f}% symbol): "
                f"nominal pass={row['frames_passing']}/{row['frames']} ({row['frame_pass_share']:.4f}; "
                f"Wilson95=[{row['wilson95_lower']:.4f}, {row['wilson95_upper']:.4f}]); "
                f"theory={row['theory_frame_pass_probability']:.4f}; MAE={row['empirical_mae']:.5f}"
            )
    print(f"JSON: {json_path}\nCSV: {csv_path}\nplot: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
