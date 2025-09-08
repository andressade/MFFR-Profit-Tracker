# MFFR Profit Tracker - Home Assistant Integration Specification

## Overview

Lightweight Home Assistant integration to track Manual Frequency Restoration Reserve (MFFR) signals and calculate profits from battery operations.

**Goal**: Replace standalone Docker application with native HA integration using built-in HA features.

## Core Requirements

### 1. Signal Detection
- Monitor `input_select.battery_mode_selector`
- Detect MFFR signals:
  - "Fusebox Buy" / "Kratt Buy" → DOWN signal
  - "Fusebox Sell" / "Kratt Sell" → UP signal  
  - Other states → IDLE

### 2. Data Tracking
- Track 15-minute time slots
- Calculate energy consumption per slot
- Fetch MFFR prices from API
- Calculate profit per slot
 - Use baseline-adjusted power for MFFR (see Baseline)

### 3. Profit Calculation
```
DOWN signal: profit = (nordpool_price - mffr_price) * energy_kwh * 0.8
UP signal:   profit = (mffr_price - nordpool_price) * energy_kwh * 0.8
```

## Sensor Entities

### Primary Sensors
```yaml
sensor.mffr_profit_tracker_power            # Current MFFR power (W), baseline-adjusted
sensor.mffr_profit_tracker_slot_energy      # Current slot energy (kWh)
sensor.mffr_profit_tracker_slot_profit      # Current slot profit (€)
sensor.mffr_profit_tracker_today_profit     # Daily total (€)
```

### Statistics Sensors  
```yaml
sensor.mffr_profit_tracker_week_profit      # Weekly total (€)
sensor.mffr_profit_tracker_month_profit     # Monthly total (€)
sensor.mffr_profit_tracker_year_profit      # Yearly total (€)
sensor.mffr_profit_tracker_all_time_profit  # All-time total (€)
sensor.mffr_profit_tracker_up_count_today   # UP activations today
sensor.mffr_profit_tracker_down_count_today # DOWN activations today
```

### Meta Sensors
```yaml
sensor.mffr_profit_tracker_recent_slots     # Attributes include recent slot table/rows
```

## Configuration

### Config Flow (UI Setup)
```yaml
# User inputs:
battery_mode_selector: input_select.battery_mode_selector
battery_power: sensor.ss_battery_power  
nordpool_price: sensor.nordpool_kwh_ee_eur_3_10_0
fusebox_fee_percent: 20  # Default 20%
scan_interval: 10        # Default 10 seconds (configurable)
baseline_enabled: true   # Enable baseline-adjusted power
# optional (advanced economics):
# grid_power: sensor.ss_grid_power
# detailed_economics: false
```

### Alternative: YAML Config
```yaml
# configuration.yaml
mffr_tracker:
  battery_mode_selector: input_select.battery_mode_selector
  battery_power: sensor.ss_battery_power
  nordpool_price: sensor.nordpool_kwh_ee_eur_3_10_0
  fusebox_fee: 0.20
  scan_interval: 10
  baseline_enabled: true
  # grid_power: sensor.ss_grid_power
  # detailed_economics: false
```

## MFFR Price API Integration

### Coordinator Pattern (recommended)
- Custom data update coordinator using HA `aiohttp` session
- Fetch and cache current hour (or small window) of prices
- Map prices to slots using HA timezone utilities (DST-safe)
- Handle API rate limiting and retries

### REST Sensor Approach (optional, use with care)
- Can be brittle due to timezone/DST and schema changes
- Prefer fetching JSON and mapping in coordinator
- If used, avoid hard-coded offsets like `+0300`; use HA time helpers

## User Interface

### Dashboard Cards (Use HA Built-ins)

#### 1. Current Status Card
```yaml
type: entities
entities:
  - sensor.mffr_profit_tracker_power
  - sensor.mffr_profit_tracker_slot_profit
  - sensor.mffr_profit_tracker_today_profit
```

#### 2. History Graph
```yaml
type: history-graph
entities:
  - sensor.mffr_profit_tracker_power
  - sensor.mffr_profit_tracker_slot_profit
hours_to_show: 24
```

#### 3. Statistics Card
```yaml
type: statistics-graph
entities:
  - sensor.mffr_profit_tracker_today_profit
  - sensor.mffr_profit_tracker_week_profit
  - sensor.mffr_profit_tracker_month_profit
stat_types:
  - sum
  - mean
```

#### 4. Details Table (Markdown Card)
```yaml
type: markdown
content: |
  ## Recent MFFR Activities
  {{ states.sensor.mffr_profit_tracker_recent_slots.attributes.slots_table }}
```

## Data Storage

### Use HA Recorder
- No custom SQLite database needed
- Automatic history retention
- Built-in statistics computation
- Long-term data storage

### State Attributes
Store additional data in sensor attributes:
```python
self._attr_extra_state_attributes = {
    "current_slot_start": slot_start.isoformat(),
    "current_slot_end": slot_end.isoformat(), 
    "mffr_price": mffr_price,
    "nordpool_price": nordpool_price,
    "energy_kwh": energy_kwh,
    "duration_minutes": duration_minutes
}
```

## Technical Implementation

### File Structure
```
custom_components/mffr_tracker/
├── __init__.py           # Integration setup
├── manifest.json         # Integration metadata  
├── config_flow.py        # UI configuration
├── coordinator.py        # Data update coordinator
├── sensor.py            # Sensor entities
├── const.py             # Constants
└── translations/
    └── en.json          # UI text
```

### Key Components

#### 1. Data Coordinator
- Poll sensors every `scan_interval` (default 10s)
- Track 15-minute slots (floor to nearest 00/15/30/45, DST-safe)
- Integrate power (W) → energy (kWh) over sampling interval
- Apply baseline-adjusted MFFR power if enabled
- Mark slot flags: `was_backup` (off-boundary start), `cancelled` (ended early)
- Fetch/cache MFFR prices and calculate profits
- Update sensor states and attributes

#### 2. Sensor Platform
- Create all sensor entities
- Handle state updates
- Manage attributes

#### 3. Config Flow
- UI-based configuration
- Validate sensor entities exist
- Store config options

## Simplified Logic Flow

1. **Every scan_interval (default 10s)**:
   - Read battery mode selector
   - If MFFR signal detected → start/continue slot tracking
   - Calculate energy consumption for current slot
   - Update sensor states

2. **End of 15-min slot**:
   - Fetch MFFR price for completed slot
   - Calculate profit (if price missing, defer and recalc when available)
   - Update statistics
   - Reset for next slot

3. **Daily statistics**:
   - Sum all slots for the day
   - Update daily/weekly/monthly totals

## What NOT to Include

- ❌ Separate SQLite database
- ❌ Custom web interface  
- ❌ FastAPI backend
- ❌ React frontend
- ❌ Complex/ML baseline models (simple idle-average baseline only)
- ❌ Grid import/export tracking (keep it simple)

## Success Criteria

### Minimum Viable Product
- [ ] Detects MFFR signals correctly
- [ ] Tracks energy per 15-min slot  
- [ ] Calculates basic profit
- [ ] Shows current status in HA dashboard
- [ ] Maintains daily/weekly/monthly totals
- [ ] Uses baseline-adjusted power for MFFR (configurable)

### Nice-to-Have
- [ ] Detailed history view
- [ ] Export functionality
- [ ] Advanced statistics
- [ ] Grid cost analysis (requires grid_power)

## Baseline (Power) Handling

### Purpose
- Separate normal battery usage from MFFR reaction power to avoid systematic bias

### Method
- During IDLE periods, accumulate battery power samples per 15-min slot
- At slot end, compute average baseline power for that slot
- MFFR power = `abs(battery_power - baseline_power)`

### Configuration
- `baseline_enabled`: default `true` (can be disabled)
- No complex models; simple slot-average from idle samples only

### Attributes
Add to relevant sensors (e.g., recent slots):
```yaml
was_backup: bool        # started off-boundary
cancelled: bool         # ended before slot end
baseline_w: number      # average baseline power for slot
mffr_power_w: number    # baseline-adjusted instantaneous power
```

## Statistics and Totals

### Daily/Weekly/Monthly Totals
- Option A: maintain running totals in sensors and rely on Recorder for history
- Option B: use HA `utility_meter` or `statistics` helpers to derive sums

### Example (Utility Meter approach)
```yaml
utility_meter:
  mffr_profit_daily:
    source: sensor.mffr_slot_profit
    cycle: daily
  mffr_profit_weekly:
    source: sensor.mffr_slot_profit
    cycle: weekly
  mffr_profit_monthly:
    source: sensor.mffr_slot_profit
    cycle: monthly
```

Expose these as `sensor.mffr_today_profit`, `sensor.mffr_week_profit`, `sensor.mffr_month_profit` via template or direct entity selection.

## Error Handling and Resilience
- If MFFR price is temporarily unavailable, keep slot profit `unknown` and recompute when data arrives
- Use HA timezone utilities for slot boundaries (DST-safe)
- Backoff and cache API responses to avoid rate limits

## Estimated Implementation Time

**MVP**: 2-3 days  
**Full featured**: 1-2 weeks

**Developer Experience Required**: Basic HA integration development, Python async programming
