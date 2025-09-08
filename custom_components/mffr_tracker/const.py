DOMAIN = "mffr_tracker"

CONF_BATTERY_MODE = "battery_mode_selector"
CONF_BATTERY_POWER = "battery_power"
CONF_NORDPOOL_PRICE = "nordpool_price"
CONF_GRID_POWER = "grid_power"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_FUSEBOX_FEE = "fusebox_fee_percent"
CONF_BASELINE_ENABLED = "baseline_enabled"
CONF_NPS_SOURCE = "nps_source"  # 'ha' | 'api' | 'auto'

DEFAULT_SCAN_INTERVAL = 10
DEFAULT_FUSEBOX_FEE = 20.0
DEFAULT_BASELINE_ENABLED = True
DEFAULT_NPS_SOURCE = "ha"

ATTR_SLOT_START = "current_slot_start"
ATTR_SLOT_END = "current_slot_end"
ATTR_MFFR_PRICE = "mffr_price"
ATTR_NORDPOOL_PRICE = "nordpool_price"
ATTR_ENERGY_KWH = "energy_kwh"
ATTR_DURATION_MIN = "duration_minutes"
ATTR_WAS_BACKUP = "was_backup"
ATTR_CANCELLED = "cancelled"
ATTR_BASELINE_W = "baseline_w"
ATTR_MFFR_POWER_W = "mffr_power_w"
