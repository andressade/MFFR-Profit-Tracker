MFFR Profit Tracker – Home Assistant Integration
================================================

This directory contains a native Home Assistant custom integration located at `custom_components/mffr_tracker`.

Install
-------

1) Copy `custom_components/mffr_tracker` into your Home Assistant `config/custom_components/` folder.

2) Restart Home Assistant.

3) In HA: Settings → Devices & Services → Add Integration → search for "MFFR Profit Tracker".

4) Select entities:
   - `battery_mode_selector` (e.g., `input_select.battery_mode_selector`)
   - `battery_power` (e.g., `sensor.ss_battery_power` in W)
   - `nordpool_price` (€/kWh)
   - Optional: `grid_power`
   - Options: `scan_interval` (default 10s), `fusebox_fee_percent` (default 20%), `baseline_enabled` (default true), `nps_source` (ha/api/auto, default ha)

What it provides
----------------

- `sensor.mffr_signal` (UP/DOWN/IDLE)
- `sensor.mffr_power` (W, baseline-adjusted)
- `sensor.mffr_slot_energy` (kWh)
- `sensor.mffr_slot_profit` (€)
- `sensor.mffr_today_profit` (€)
- `sensor.mffr_week_profit` (€)
- `sensor.mffr_month_profit` (€)
- `sensor.mffr_up_count` (count, today)
- `sensor.mffr_down_count` (count, today)
- `sensor.mffr_recent_slots` (attributes include a markdown table)

Recommended extras
------------------

- Add statistics-based rolling sums for day/week/month from slot profits:
  - See `examples/home_assistant/statistics_sensors.yaml`

- Add Lovelace cards:
  - See `examples/home_assistant/lovelace_cards.yaml`

Notes
-----

- Baseline is a simple idle-average per slot. MFFR power = |battery - baseline| if baseline enabled.
- Prices are fetched and cached by the coordinator. Adjust mapping to your API if needed.
- If prices are temporarily unavailable, slot profit is deferred until data becomes available.
- Daily/weekly/monthly totals are persisted across restarts and reset on calendar boundaries (local time, ISO week).
- UP/DOWN counts are for finalized slots and persist across restarts for the current day.
