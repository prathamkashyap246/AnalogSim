# AnalogSim

AnalogSim is a starter web prototype for simulating real-world circuit behavior using structured experimental data.

## Vision

Most simulators assume ideal conditions. AnalogSim focuses on realistic behavior by combining:

- Analog modeling effects (for example NMOS body effect, channel length modulation, and hot-electron degradation)
- Digital behavior under process/voltage/temperature-style conditions
- A structured data layer for real experimental inputs, outputs, and test conditions

This repository now contains a minimal base implementation of that idea.

## What is included

- `index.html` — UI for:
  - NMOS drain-current estimation with non-ideal effects
  - Basic digital delay/power estimation under operating conditions
  - Real experimental dataset viewer
- `app.js` — simulation and dataset logic
- `styles.css` — basic page styling
- `data/experiments.schema.json` — schema for structured experimental records
- `data/experiments.sample.json` — sample records (analog + digital)

## Run locally

Because this is a static prototype, no build step is required.

From the repository root:

```bash
python -m http.server 8000
```

Then open:

`http://localhost:8000`

## Data model direction

The `data/experiments.schema.json` format is designed so contributors can add measured data with:

- board/circuit metadata
- operating conditions (`temperature_c`, `supply_v`, etc.)
- measured outputs (`id_ma`, `delay_ns`, `power_mw`, waveform links, and more)
- model tags such as `body_effect`, `channel_length_modulation`, and `hot_electron_effect`

As more records are added, this dataset can power fitting, calibration, and predictive models for future iterations of AnalogSim.