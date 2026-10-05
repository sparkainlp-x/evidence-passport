# v5 integer-sample timing protocol lock — fixed before the full run

**Protocol source:** [`robustness_benchmark_v5_timing.py`](../robustness_benchmark_v5_timing.py), SHA-256 `1bd9500ce3ceadadae25ce6731bc8ea9058adefa2781adf4d16d403b6c383419`. The complete project suite passed 47 tests before this run. This is an exploratory software protocol, not a formal preregistration.

## Question and finite-frame definition

Test how a fixed receiver timing phase changes the current matched-filter decoder when it is handed windows that begin at the wrong integer sample. The transmitter’s signed encoder, its 64-sample/four-cycle segments, the carrier, the sampling rate, and the frame contents are unchanged. This is **not** a sample-rate or clock-drift sweep, and no CFO is applied.

Serialize the existing 32 encoded segments in order, with exactly 64 zero-valued samples before and after the finite frame. For segment index `k` and local index `n`, the nominal decoder receives the 64 samples beginning at `64 + 64k + Δ`, where `Δ` is its fixed timing offset in samples. Positive `Δ` means late; negative `Δ` means early. The guards define edge samples without circular wrap. The timing-aware oracle is given the exact offset and frame boundary, then selects the true windows beginning at `64 + 64k`. It uses the unchanged projection and is a diagnostic upper bound, **not** a timing-recovery algorithm. Any performance impact from the artificial frame guards and the abrupt, unfiltered segment boundaries is part of this software model only.

## Conditions fixed in advance

- **Inputs:** the same six fixed 32-value v2 vectors, unchanged; randomized-vector seed `20261004`; dimensionless range `[-2,2]`.
- **Waveform and score:** 64 samples per symbol, 4 carrier cycles, `A_min=1`; pass iff the maximum absolute error over 32 values is `≤0.25`, inclusive.
- **Timing offsets:** `Δ = −8, −4, −2, −1, 0, +1, +2, +4, +8` integer samples. These are constant over the complete frame and correspond to `−12.5%, −6.25%, −3.125%, −1.5625%, 0, +1.5625%, +3.125%, +6.25%, +12.5%` of a 64-sample symbol. The levels are arbitrary discrete software stress values, not physical timing specifications.
- **Noise:** clean deterministic control (`σ=0`) and IID Gaussian sample noise at dimensionless SD `0.45`, including on guard samples. Each paired method reads the same noisy serialized frame.
- **Trials:** 2,000 noisy frames per fixed vector and offset; master seed `20261007`; 108,000 noisy input frames total. Each vector also has one clean deterministic frame at each offset. The weak zero-output floor is evaluated once against each fixed vector and is not a competing decoder.
- **Uncertainty/calibration:** stochastic frame pass shares receive two-sided 95% Wilson score intervals, conditional on the fixed vectors and IID Gaussian draws. Clean and zero-output rows are deterministic and have no sampling interval. The nominal receiver’s clean-window projection supplies its exact component bias; independent projected noise has SD `σ/√32`. The theoretical frame pass probability is the product of the 32 component probabilities. These intervals do not quantify model or physical uncertainty.

## Why this test is distinct

MathWorks describes `comm.SymbolSynchronizer` as correcting receiver symbol-timing clock skew and demonstrates adding a fixed fractional timing error in its example ([MathWorks symbol synchronizer documentation](https://www.mathworks.com/help/comm/ref/comm.symbolsynchronizer-system-object.html)). The Stanford communications text has a separate chapter section on symbol-timing synchronization and timing recovery ([*Fundamentals of Synchronization*, §6.3](https://cioffi-group.stanford.edu/doc/book/chap6.pdf)). A communications-link example also distinguishes sample-clock offset from carrier-frequency offset and applies timing recovery ([MathWorks CCSDS optical-link example](https://uk.mathworks.com/help/satcom/ug/ccsds-hdr-optical-link-simulation-for-1550nm.html)). These sources support treating timing as a distinct receiver synchronization impairment; they do not validate this project’s integer-offset grid, zero guards, or model as a physical channel.

The v5 model is intentionally an **arbitrary discrete sample-offset software stress test** for the existing frame/window contract. It is not a measured channel, realistic pulse-shaped link, or evidence of physical validity. Pre-run SHA-256 values for all protected v1–v4 code, tests, reports, and result artifacts are in [`v5-protected-files-pre-run.sha256`](v5-protected-files-pre-run.sha256).
