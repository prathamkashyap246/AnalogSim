function toNum(form, key) {
  return Number(form.elements[key].value);
}

function setupNmosSimulation() {
  const form = document.getElementById("nmos-form");
  const output = document.getElementById("nmos-output");

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const vgs = toNum(form, "vgs");
    const vds = toNum(form, "vds");
    const vth0 = toNum(form, "vth0");
    const vsb = Math.max(0, toNum(form, "vsb"));
    const gamma = toNum(form, "gamma");
    const phi2f = Math.max(0.01, toNum(form, "phi2f"));
    const k = Math.max(0, toNum(form, "k"));
    const lambda = Math.max(0, toNum(form, "lambda"));
    const hotFactor = Math.min(1, Math.max(0, toNum(form, "hotFactor")));

    const vth = vth0 + gamma * (Math.sqrt(phi2f + vsb) - Math.sqrt(phi2f));
    const overdrive = vgs - vth;
    if (overdrive <= 0) {
      output.textContent = `Cutoff region. Effective Vth=${vth.toFixed(3)} V, Id≈0 mA`;
      return;
    }

    let idSatMa = 0.5 * k * overdrive * overdrive;
    idSatMa *= 1 + lambda * Math.max(vds, 0);
    idSatMa *= hotFactor;

    output.textContent = `Effective Vth=${vth.toFixed(3)} V, Id≈${idSatMa.toFixed(
      4
    )} mA (includes body effect, channel length modulation, hot-electron factor)`;
  });
}

function setupDigitalEstimate() {
  const form = document.getElementById("digital-form");
  const output = document.getElementById("digital-output");

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const baseDelay = Math.max(0.01, toNum(form, "baseDelay"));
    const temperature = toNum(form, "temperature");
    const vdd = Math.max(0.1, toNum(form, "vdd"));
    const activity = Math.min(1, Math.max(0, toNum(form, "activity")));
    const capacitancePf = Math.max(0, toNum(form, "capacitancePf"));
    const frequencyMhz = Math.max(0, toNum(form, "frequencyMhz"));

    const tempFactor = 1 + (temperature - 25) * 0.0015;
    const voltageFactor = 1 / vdd;
    const estimatedDelayNs = baseDelay * tempFactor * voltageFactor;

    const capacitanceF = capacitancePf * 1e-12;
    const frequencyHz = frequencyMhz * 1e6;
    const dynamicPowerW = activity * capacitanceF * vdd * vdd * frequencyHz;
    const dynamicPowerMw = dynamicPowerW * 1000;

    output.textContent = `Estimated delay=${estimatedDelayNs.toFixed(
      4
    )} ns, estimated dynamic power=${dynamicPowerMw.toFixed(4)} mW`;
  });
}

function formatConditions(conditions) {
  return Object.entries(conditions)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

function formatMeasurements(measured) {
  return Object.entries(measured)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

async function loadDataset() {
  const meta = document.getElementById("dataset-meta");
  const tbody = document.getElementById("dataset-body");

  try {
    const response = await fetch("./data/experiments.sample.json");
    const dataset = await response.json();
    meta.textContent = `Version: ${dataset.version} | Records: ${dataset.records.length}`;

    tbody.innerHTML = "";
    for (const record of dataset.records) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${record.record_id}</td>
        <td>${record.category}</td>
        <td>${record.device_or_board}</td>
        <td>${formatConditions(record.conditions)}</td>
        <td>${formatMeasurements(record.measured_outputs)}</td>
      `;
      tbody.appendChild(row);
    }
  } catch (error) {
    meta.textContent = "Failed to load dataset.";
  }
}

setupNmosSimulation();
setupDigitalEstimate();
loadDataset();
