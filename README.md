# SolaXCloud — Home Assistant Custom Integration

A Home Assistant custom integration for monitoring SolaX Power solar installations via the [SolaXCloud OpenAPI](https://developer.solaxcloud.com/).

Polls plant, inverter, and battery realtime data on a configurable schedule and exposes them as standard Home Assistant sensor entities.

## Features

- **Plant-level sensors** — Daily and total yield, grid import/export, battery charge/discharge, and earnings
- **Inverter sensors** — AC voltage/current/power per phase, grid power, frequencies, temperature, MPPT string data, and production totals
- **Battery sensors** — State of charge, state of health, voltage, current, temperature, cycle count, and energy throughput
- **Last data update** - Timestamp sensor per device (diagnostic)
- **Energy dashboard ready** — Sensors are classified with `TOTAL_INCREASING` state class and `kWh` units
- **Configurable polling interval** — Defaults to 5 minutes; adjustable without restarting HA
- **Multi-Language ready** - German translation included

## Requirements

- Home Assistant **2024.1** or newer (uses `entry.runtime_data` and PEP 695 type aliases)
- A [SolaX Developer Portal](https://developer.solaxcloud.com/) account with an **OAuth2 application** created (provides Client ID and Client Secret)

## Creating API Credentials

1. Log in to the [SolaX Developer Portal](https://developer.solaxcloud.com/)
2. Navigate to **My Applications** and create a new application
3. Note the **Client ID** and **Client Secret** — you will need these during setup
4. The application must have access to the **Data Monitoring Service (API_Telemetry_V2)** and **Information Access Service (API_Info_V2)** scopes

> **Regional API URL**
> The base URL depends on your region. The integration defaults to the European endpoint (`https://openapi-eu.solaxcloud.com`). Check the developer portal documentation for your region's URL. Generally, you should find your endpoint URL (call URL) in your Account/Profile settings.

## Installation

This integration is installed **manually**. Currently, no HACS support is available.

### Step 1 — Download the integration

Clone or download this repository:

```bash
git clone https://github.com/anmx/ha-solaxcloud.git
```

Or download the ZIP from the repository page and extract it.

### Step 2 — Copy the integration files

Copy the `custom_components/solaxcloud` directory into the `custom_components` folder inside your Home Assistant configuration directory.

```bash
cp -r ha-solaxcloud/custom_components/solaxcloud /path/to/homeassistant/config/custom_components/
```

### Step 3 — Restart Home Assistant

Go to **Settings --> System --> Restart** and restart Home Assistant so it picks up the new integration.

### Step 4 — Add the integration

1. Go to **Settings --> Devices & Services**
2. Click **+ Add Integration**
3. Search for **SolaXCloud**
4. Fill in the setup dialog:

| Field         | Description                                        | Default                             |
| ------------- | -------------------------------------------------- | ----------------------------------- |
| API Base URL  | Root URL of the SolaXCloud OpenAPI for your region | `https://openapi-eu.solaxcloud.com` |
| Client ID     | OAuth2 Client ID from the developer portal         | —                                   |
| Client Secret | OAuth2 Client Secret from the developer portal     | —                                   |

The integration validates your credentials by fetching an access token before creating the entry. If authentication fails, check your Client ID and Client Secret in the developer portal.

### Step 5 — Configure the polling interval (optional)

The default polling interval is **5 minutes** (300 seconds), which is conservative to stay within the SolaXCloud API rate limits.

To change it:

1. Go to **Settings → Devices & Services → SolaXCloud**
2. Click **Configure**
3. Set your preferred **Query interval** in seconds

The new interval takes effect immediately without restarting.

## Entities

Once configured, the integration creates one HA device per plant, inverter, and battery, each with a set of sensor entities.

### Plant sensors (`solax_plant_<plant_name>`)

| Entity                         | Description                        | Unit |
| ------------------------------ | ---------------------------------- | ---- |
| Plant Daily Yield              | PV production today                | kWh  |
| Plant Total Yield              | Lifetime PV production             | kWh  |
| Plant Daily Battery Charged    | Battery energy charged today       | kWh  |
| Plant Total Battery Charged    | Lifetime battery energy charged    | kWh  |
| Plant Daily Battery Discharged | Battery energy discharged today    | kWh  |
| Plant Total Battery Discharged | Lifetime battery energy discharged | kWh  |
| Plant Daily Grid Import        | Energy imported from grid today    | kWh  |
| Plant Total Grid Import        | Lifetime energy imported from grid | kWh  |
| Plant Daily Grid Export        | Energy exported to grid today      | kWh  |
| Plant Total Grid Export        | Lifetime energy exported to grid   | kWh  |
| Plant Daily Earnings           | Revenue earned today               | —    |
| Plant Total Earnings           | Lifetime revenue earned            | —    |

### Inverter sensors (`solax_inverter_<serial_number>`)

| Entity                          | Description                                        | Unit |
| ------------------------------- | -------------------------------------------------- | ---- |
| Grid Power                      | Net grid exchange power                            | W    |
| Today / Total Import Energy     | Grid energy imported                               | kWh  |
| Today / Total Export Energy     | Grid energy exported                               | kWh  |
| AC Voltage L1 / L2 / L3         | Phase voltages                                     | V    |
| AC Current L1 / L2 / L3         | Phase currents                                     | A    |
| AC Power L1 / L2 / L3           | Phase power                                        | W    |
| AC Frequency L1 / L2 / L3       | Phase frequencies                                  | Hz   |
| Total Power Factor              | Power factor                                       | —    |
| Inverter Temperature            | Inverter heat sink temperature                     | °C   |
| Daily / Total AC Output         | AC energy produced                                 | kWh  |
| Daily / Total Yield             | PV energy produced                                 | kWh  |
| MPPT 1 / 2 Voltage              | PV string voltage                                  | V    |
| MPPT 1 / 2 Current              | PV string current                                  | A    |
| MPPT 1 / 2 Power                | PV string power                                    | W    |
| Last Data Update *(diagnostic)* | Timestamp of the last data point from the inverter | —    |

### Battery sensors (`solax_battery_<serial_number>`)

| Entity                          | Description                                       | Unit |
| ------------------------------- | ------------------------------------------------- | ---- |
| Battery State of Charge         | Current SOC                                       | %    |
| Battery State of Health         | Battery health                                    | %    |
| Charge/Discharge Power          | Charge (+) / discharge (−) power                  | W    |
| Battery Voltage                 | Terminal voltage                                  | V    |
| Battery Current                 | Charge/discharge current                          | A    |
| Battery Temperature             | Cell temperature                                  | °C   |
| Battery Cycle Count             | Full charge/discharge cycles                      | —    |
| Total Battery Discharge         | Lifetime energy discharged                        | kWh  |
| Total Battery Charge            | Lifetime energy charged                           | kWh  |
| Battery Remaining Capacity      | Usable energy remaining                           | kWh  |
| Last Data Update *(diagnostic)* | Timestamp of the last data point from the battery | —    |

## Energy Dashboard Configuration

### Grid

| Setting                   | Recommended sensor                                     |
| ------------------------- | ------------------------------------------------------ |
| Energy imported from grid | `sensor.solax_plant_<name>_plant_total_imported`       |
| Energy exported to grid   | `sensor.solax_plant_<name>_plant_total_exported`       |
| Power measurement         | **Standard** → `sensor.solax_inverter_<sn>_grid_power` |

> **Note on `grid_power` sign convention:** verify whether a positive value means importing or exporting by checking a live reading during a known state. If the sign is reversed, select **Inverted** instead of Standard.

### Solar panels

| Setting                 | Recommended sensor                                                           |
| ----------------------- | ---------------------------------------------------------------------------- |
| Solar production energy | `sensor.solax_plant_<name>_plant_total_yield`                                |
| Solar production power  | Create a template sensor summing `mppt_1_power` + `mppt_2_power` (see below) |

Because the API does not provide a single total PV power field, add the following template sensor to your `configuration.yaml` to get real-time solar power for the Energy dashboard:

Example:

```yaml
template:
  - sensor:
      - name: "SolaX Total PV Power"
        unique_id: solax_total_pv_power
        unit_of_measurement: W
        device_class: power
        state_class: measurement
        state: >
          {{ (states('sensor.solax_inverter_<serial>_mppt_1_power') | float(0))
           + (states('sensor.solax_inverter_<serial>_mppt_2_power') | float(0)) }}
```

Replace `<serial>` with your inverter serial number.

### Battery storage

| Setting                          | Recommended sensor                                         |
| -------------------------------- | ---------------------------------------------------------- |
| Energy going in to the battery   | `sensor.solax_plant_<name>_plant_total_battery_charged`    |
| Energy coming out of the battery | `sensor.solax_plant_<name>_plant_total_battery_discharged` |
| Battery charge %                 | `sensor.solax_battery_<sn>_battery_state_of_charge`        |

## Known Limitations

- **No HACS support** — manual installation only
- **No push updates** — the SolaXCloud API is poll-only; data freshness depends on the configured query interval
- **API rate limits** — the SolaXCloud free tier enforces rate limits (error 10406) and a total call quota (error 10405). The integration logs a warning on rate-limit and an error on quota exhaustion. Increase the query interval if you frequently hit limits
- **Solar power sensor requires a template** — the API provides per-MPPT-string power but not a pre-summed total PV power value

## License

![github license](https://img.shields.io/badge/License-MIT-orange)

This project uses the MIT License, for more details see the [license](LICENSE) document.
