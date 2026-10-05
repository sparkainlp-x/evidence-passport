# Signal Test Commons

Signal Test Commons is a compact, deterministic, versioned **synthetic** challenge suite for evaluating multichannel signal monitors offline. It uses only the Python standard library and generates 512-channel frames arranged as a 16 × 32 row-major grid. A group ID is one grid position, `row * 32 + column` (IDs 0–511).

## Quickstart

Requires Python 3.10 or later; no installation or network access is needed.

```sh
python3 signal_test_commons.py --seed 7 --report challenge_report.json
python3 -m unittest -v
```

The first command writes a JSON report containing the seed, challenge version, scenario parameters, and baseline metrics. Repeating the same seed with the same challenge version replays the same challenge in the same Python runtime. Pass `--threshold 4.5` to set the baseline's absolute-value threshold, or choose another report path with `--report`.

To use the generator and evaluator from another local Python program:

```python
from signal_test_commons import generate_challenge, baseline_detect, evaluate

challenge = generate_challenge(seed=7)
predictions = baseline_detect(challenge, threshold=4.5)
metrics = evaluate(challenge, predictions)
print(metrics)
```

## Challenge contents

Version `1.0.0` creates four 20-frame episodes (80 frames total). Every channel starts as independent seeded Gaussian noise with standard deviation 1.0; injections are additive. Event intervals are inclusive, and each frame records its scenario, episode, event ID (when injected), and exact injected group IDs.

| Scenario | Event window within episode | Injection |
| --- | --- | --- |
| `stable-noise` | None | Noise only; clean reference frames |
| `localized-burst` | Frames 7–9 | One seeded grid group receives +8.0 |
| `block-drift` | Frames 5–12 | A seeded 3 × 4 block receives a rising offset, +5.0 then +0.35 per event frame |
| `global-shock` | Frames 8–9 | All 512 groups receive +6.0 |

The selected group IDs and block coordinates are included in each episode's report parameters. Scenario constants and generator version are defined in `signal_test_commons.py`.

## Baseline and metrics

The deliberately simple baseline flags each group when `abs(value) >= threshold` (default 4.5); it alarms on a frame when at least one group is flagged. `evaluate()` keeps three distinct measures:

- **Event detection recall:** fault episodes with at least one alarm during the labeled event interval, divided by fault episodes.
- **False alarms per clean frame:** alarmed frames containing no injected groups, divided by all frames containing no injected groups. Injected frames are excluded even when the injection is localized.
- **Group localization accuracy:** micro Jaccard over injected frames: `sum(|predicted groups ∩ injected groups|) / sum(|predicted groups ∪ injected groups|)`. This penalizes both missed groups and extra group predictions; clean frames are not part of this measure.

The JSON report also includes the counts used by these metrics and plain-text metric definitions. If a metric's denominator is zero, its value is 0.0.

## Plug in another detector

A local detector can consume `challenge.frames`; each frame's 512 values are available as `frame.values`. Return one `Detection(frame_index, alarm, groups)` for **every** frame, where `groups` is an iterable of predicted row-major group IDs. Then pass those predictions to `evaluate(challenge, predictions)` or `build_report(challenge, predictions, detector_name="your-detector")`. The evaluator checks prediction coverage, frame IDs, alarm types, and group-ID bounds. This is a Python API for local experiments, not a live service or network interface.

## Scope

All data and scores are synthetic and deterministic for a given seed and challenge version. They are useful for exercising replay, event scoring, and spatial localization logic; **synthetic results do not establish or predict performance on physical instruments**. No real instrument data, network access, or external packages are used.
