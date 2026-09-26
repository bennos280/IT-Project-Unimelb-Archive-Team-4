# Unit tests

Pure functions and CLI/config option resolution, exercised directly — no orchestrator,
no fixture images, no disk I/O beyond argparse. Every image is generated in-memory
with numpy/cv2; nothing here reads a file.

**9 tests. Runs in ~3s.**

```bash
pytest tests-v2/unit
```

## `test_preprocess.py` — 9 tests

Skew estimation and CLI/config option handling for `pipeline.preprocess`.

| Test  | What it checks |
|---|---|
| `test_estimate_skew_angle_detects_known_tilt`  | Synthetic lines tilted 4° are detected to within 1° (magnitude only). |
| `test_deskew_uses_agreeing_card_edges_and_corrects_direction`  | Detection uses the `card_edges` method, picks the right sign, and residual tilt after `deskew()` is under 0.25°. |
| `test_boundary_skew_rejects_blank_and_single_edge`  | A blank image and a single detected edge both return `None` — not enough evidence to guess. |
| `test_boundary_skew_rejects_disagreeing_edges`  | Two edges at conflicting angles return `None` rather than an unreliable average. |
| `test_defaults_and_cli_overrides`  | Precedence order: defaults < config values < command-line flags. |
| `test_invalid_cli_options`  | A bad number and conflicting colour modes both exit with argparse code 2. |
