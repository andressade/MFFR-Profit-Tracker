from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, Optional, Tuple
import logging

from aiohttp import ClientConnectorCertificateError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import aiohttp_client
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store

from .const import (
    CONF_BATTERY_MODE,
    CONF_BATTERY_POWER,
    CONF_NORDPOOL_PRICE,
    CONF_GRID_POWER,
    CONF_SCAN_INTERVAL,
    CONF_FUSEBOX_FEE,
    CONF_BASELINE_ENABLED,
    CONF_NPS_SOURCE,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_FUSEBOX_FEE,
    DEFAULT_BASELINE_ENABLED,
    DEFAULT_NPS_SOURCE,
    DEFAULT_VERIFY_SSL,
)


def _quarter_start(ts: datetime) -> datetime:
    minute = (ts.minute // 15) * 15
    return ts.replace(minute=minute, second=0, microsecond=0)


@dataclass
class Slot:
    start: datetime
    end: datetime
    signal: str
    energy_kwh: float = 0.0
    duration_s: float = 0.0
    was_backup: bool = False
    cancelled: bool = False
    baseline_w: Optional[float] = None
    mffr_price: Optional[float] = None
    nordpool_price: Optional[float] = None
    profit: Optional[float] = None


class MFFRCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        data = entry.data
        options = entry.options

        self.entity_mode = options.get(CONF_BATTERY_MODE, data.get(CONF_BATTERY_MODE))
        self.entity_power = options.get(CONF_BATTERY_POWER, data.get(CONF_BATTERY_POWER))
        self.entity_nordpool = options.get(CONF_NORDPOOL_PRICE, data.get(CONF_NORDPOOL_PRICE))
        self.entity_grid = options.get(CONF_GRID_POWER, data.get(CONF_GRID_POWER))
        self.scan_seconds = int(options.get(CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        self.fusebox_fee_pct = float(options.get(CONF_FUSEBOX_FEE, data.get(CONF_FUSEBOX_FEE, DEFAULT_FUSEBOX_FEE)))
        self.baseline_enabled = bool(options.get(CONF_BASELINE_ENABLED, data.get(CONF_BASELINE_ENABLED, DEFAULT_BASELINE_ENABLED)))
        self.nps_source = (options.get(CONF_NPS_SOURCE, data.get(CONF_NPS_SOURCE, DEFAULT_NPS_SOURCE)) or "ha").lower()
        self.verify_ssl = bool(options.get(CONF_VERIFY_SSL, data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)))

        super().__init__(
            hass,
            logging.getLogger(__name__),
            name="mffr_tracker",
            update_interval=timedelta(seconds=self.scan_seconds),
        )

        if not self.verify_ssl:
            self.logger.warning(
                "FRR price fetch configured with SSL verification disabled; enable it once tihend.energy presents a trusted certificate."
            )

        self._recent_slots: Deque[Slot] = deque(maxlen=48)
        self._active_slot: Optional[Slot] = None
        self._today_profit: float = 0.0
        self._today_date: Optional[datetime.date] = None
        self._week_profit: float = 0.0
        self._month_profit: float = 0.0
        self._week_key: Optional[tuple[int, int]] = None  # (iso_year, iso_week)
        self._month_key: Optional[tuple[int, int]] = None  # (year, month)
        self._year_profit: float = 0.0
        self._year_key: Optional[int] = None  # year
        self._all_profit: float = 0.0
        self._up_count: int = 0
        self._down_count: int = 0

        self._baseline_sum_w: float = 0.0
        self._baseline_samples: int = 0
        self._baseline_last_w: float = 0.0
        self._last_ts: Optional[datetime] = None
        # Detect early cancellations even if mode remains BUY/SELL:
        # accumulate time with near-zero MFFR power while signal claims active
        self._active_idle_s: float = 0.0

        # Cache per-slot prices keyed by local slot-start ISO
        # value: {"mfrr_price": float, "nps_price": float}
        self._mffr_price_cache: Dict[str, Dict[str, float]] = {}
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._store: Store = Store(hass, 1, f"mffr_tracker_{entry.entry_id}.json")
        self._last_price_fetch: Optional[datetime] = None

    async def async_load_state(self) -> None:
        data = await self._store.async_load() or {}
        try:
            # Restore totals only if keys match current periods
            now = dt_util.now()
            # Day
            saved_day = data.get("today_date")
            if saved_day:
                try:
                    y, m, d = saved_day.split("-")
                    saved_date = datetime(int(y), int(m), int(d)).date()
                except Exception:
                    saved_date = None
                if saved_date == now.date():
                    self._today_date = saved_date
                    self._today_profit = float(data.get("today_profit", 0.0))
                    self._up_count = int(data.get("up_count", 0))
                    self._down_count = int(data.get("down_count", 0))
            # Week
            saved_week = data.get("week_key")  # [iso_year, iso_week]
            if isinstance(saved_week, list) and len(saved_week) == 2:
                iso_year, iso_week, _ = now.isocalendar()
                if tuple(saved_week) == (iso_year, iso_week):
                    self._week_key = (iso_year, iso_week)
                    self._week_profit = float(data.get("week_profit", 0.0))
            # Month
            saved_month = data.get("month_key")  # [year, month]
            if isinstance(saved_month, list) and len(saved_month) == 2:
                if tuple(saved_month) == (now.year, now.month):
                    self._month_key = (now.year, now.month)
                    self._month_profit = float(data.get("month_profit", 0.0))
            # Year
            saved_year = data.get("year_key")
            if isinstance(saved_year, int):
                if saved_year == now.year:
                    self._year_key = now.year
                    self._year_profit = float(data.get("year_profit", 0.0))
            # All-time
            self._all_profit = float(data.get("all_profit", 0.0))
        except Exception:
            # Ignore corrupt store
            pass

    async def _async_save_state(self) -> None:
        payload = {
            "today_date": self._today_date.isoformat() if self._today_date else None,
            "today_profit": self._today_profit,
            "up_count": self._up_count,
            "down_count": self._down_count,
            "week_key": list(self._week_key) if self._week_key else None,
            "week_profit": self._week_profit,
            "month_key": list(self._month_key) if self._month_key else None,
            "month_profit": self._month_profit,
            "year_key": self._year_key,
            "year_profit": self._year_profit,
            "all_profit": self._all_profit,
        }
        try:
            await self._store.async_save(payload)
        except Exception:
            pass

    def _parse_any_datetime(self, s: str) -> Optional[datetime]:
        if not isinstance(s, str):
            return None
        # normalize: allow space or 'T', allow +0300 or +03:00
        s2 = s.strip().replace(" ", "T")
        # Insert colon in timezone if missing (e.g., +0300 -> +03:00)
        if len(s2) >= 5 and (s2[-5] in ["+", "-"]) and s2[-3] != ":":
            s2 = f"{s2[:-2]}:{s2[-2:]}"
        try:
            dt = dt_util.parse_datetime(s2)
        except Exception:
            return None
        if not dt:
            return None
        return dt_util.as_local(dt)

    async def _fetch_mffr_prices(self, ts: datetime) -> None:
        # Fetch current set of FRR prices (15-min granularity) and cache
        url = "https://tihend.energy/api/v1/frr"
        try:
            async with self._session.get(url, timeout=10, ssl=self.verify_ssl) as resp:
                if resp.status != 200:
                    self.logger.warning("FRR price fetch HTTP %s", resp.status)
                    return
                data = await resp.json()
        except ClientConnectorCertificateError as exc:
            if self.verify_ssl:
                self.logger.error(
                    "FRR price fetch failed due to certificate error. Disable 'Verify SSL certificates' in options to skip verification: %s",
                    exc,
                )
            else:
                self.logger.error("FRR price fetch failed despite SSL verification disabled: %s", exc)
            return
        except Exception:
            self.logger.exception("FRR price fetch failed")
            return

        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self.logger.debug("FRR response has no data list")
            return
        added = 0
        for item in items:
            start_s = item.get("start")
            mp = item.get("mfrr_price")
            np = item.get("nps_price")
            if not start_s or mp is None:
                continue
            dt = self._parse_any_datetime(start_s)
            if not dt:
                continue
            # Slot-level key (15-min aligned start)
            slot_key = _quarter_start(dt).isoformat()
            rec = self._mffr_price_cache.get(slot_key, {})
            rec["mfrr_price"] = self._normalize_price(mp)
            if np is not None:
                rec["nps_price"] = self._normalize_price(np)
            self._mffr_price_cache[slot_key] = rec
            added += 1
        self.logger.debug("FRR cached %s slots; example key=%s", added, next(iter(self._mffr_price_cache.keys()), None))

    def _get_slot_prices_for(self, ts: datetime) -> Dict[str, float]:
        key = _quarter_start(ts).isoformat()
        return self._mffr_price_cache.get(key, {})

    def _normalize_price(self, price: Any) -> Optional[float]:
        if price is None:
            return None
        try:
            value = float(price)
        except (TypeError, ValueError):
            return None
        # FRR API returns €/MWh; convert values that look like MWh pricing
        return value / 1000.0 if abs(value) > 5 else value

    def _select_nps_price(self, slot_prices: Dict[str, float], nordpool_price: Optional[float]) -> Tuple[Optional[float], str]:
        api_price = self._normalize_price(slot_prices.get("nps_price"))
        fallback_price = self._normalize_price(nordpool_price)

        if self.nps_source == "ha":
            return fallback_price, "ha"
        if self.nps_source == "api":
            if api_price is not None:
                return api_price, "api"
            return fallback_price, "ha"

        # auto mode
        if api_price is not None:
            return api_price, "api"
        return fallback_price, "ha"

    def _mode_to_signal(self, mode: str) -> str:
        m = (mode or "").lower()
        if "sell" in m:
            return "UP"
        if "buy" in m:
            return "DOWN"
        return "IDLE"

    async def _async_update_prices_if_needed(self, now: datetime) -> None:
        # Fetch at most once per 60 seconds and only if slot prices missing
        if not self._get_slot_prices_for(now):
            if self._last_price_fetch is None or (now - self._last_price_fetch) >= timedelta(seconds=60):
                self.logger.debug("FRR prices missing for slot %s → fetching", _quarter_start(now).isoformat())
                await self._fetch_mffr_prices(now)
                self._last_price_fetch = now

    async def _async_finalize_previous_day(self, now: datetime) -> None:
        if self._today_date is None:
            self._today_date = now.date()
        elif now.date() != self._today_date:
            self._today_profit = 0.0
            self._up_count = 0
            self._down_count = 0
            self._today_date = now.date()
            await self._async_save_state()

        # Week boundary (ISO week, Monday-based)
        iso_year, iso_week, _ = now.isocalendar()
        if self._week_key is None:
            self._week_key = (iso_year, iso_week)
        elif self._week_key != (iso_year, iso_week):
            self._week_profit = 0.0
            self._week_key = (iso_year, iso_week)
            await self._async_save_state()

        # Month boundary
        ym = (now.year, now.month)
        if self._month_key is None:
            self._month_key = ym
        elif self._month_key != ym:
            self._month_profit = 0.0
            self._month_key = ym
            await self._async_save_state()

        # Year boundary
        if self._year_key is None:
            self._year_key = now.year
        elif self._year_key != now.year:
            self._year_profit = 0.0
            self._year_key = now.year
            await self._async_save_state()

    def _finalize_active_slot(self) -> None:
        if not self._active_slot:
            return
        slot = self._active_slot

        fee = self.fusebox_fee_pct / 100.0
        np = slot.nordpool_price
        mp = slot.mffr_price
        if np is not None and mp is not None and slot.energy_kwh > 0:
            if slot.signal == "UP":
                profit = (mp - np) * slot.energy_kwh * (1 - fee)
            elif slot.signal == "DOWN":
                profit = (np - mp) * slot.energy_kwh * (1 - fee)
            else:
                profit = 0.0
            slot.profit = profit
            self._today_profit += profit
            self._week_profit += profit
            self._month_profit += profit
            self._year_profit += profit
            self._all_profit += profit
        # Count activations per finalized slot (one per slot with signal)
        if slot.signal == "UP":
            self._up_count += 1
        elif slot.signal == "DOWN":
            self._down_count += 1
        # Persist after change
        # Note: not awaited here to avoid blocking; schedule task
        self.hass.async_create_task(self._async_save_state())
        self._recent_slots.appendleft(slot)
        self._active_slot = None

    async def _update_baseline(self, battery_w: float, dt_s: float, signal: str, now: datetime) -> None:
        if signal == "IDLE":
            # Accumulate signed power for realistic baseline
            self._baseline_sum_w += float(battery_w)
            self._baseline_samples += 1
        # finalize baseline near slot end and carry forward last value
        if now.minute % 15 == 14 and now.second >= 50:
            if self._baseline_samples > 0:
                avg = self._baseline_sum_w / self._baseline_samples
            else:
                avg = self._baseline_last_w
            self._baseline_sum_w = 0.0
            self._baseline_samples = 0
            self._baseline_last_w = avg
            if self._active_slot and self._active_slot.baseline_w is None:
                self._active_slot.baseline_w = avg

    async def _async_update_logic(self) -> Dict[str, Any]:
        now = dt_util.now()
        await self._async_finalize_previous_day(now)

        mode_state = self.hass.states.get(self.entity_mode)
        power_state = self.hass.states.get(self.entity_power)
        nordpool_state = self.hass.states.get(self.entity_nordpool)

        signal = self._mode_to_signal(mode_state.state if mode_state else "")
        try:
            battery_w = float(power_state.state) if power_state and power_state.state not in ("unknown", "unavailable") else 0.0
        except Exception:
            battery_w = 0.0
        try:
            nordpool_raw = float(nordpool_state.state) if nordpool_state and nordpool_state.state not in ("unknown", "unavailable") else None
        except Exception:
            nordpool_raw = None
        nordpool = self._normalize_price(nordpool_raw)

        await self._async_update_prices_if_needed(now)
        slot_prices = self._get_slot_prices_for(now)
        mffr_price = self._normalize_price(slot_prices.get("mfrr_price"))

        chosen_nps_price, active_source = self._select_nps_price(slot_prices, nordpool)

        if self._last_ts is None:
            self._last_ts = now
        dt_s = max(0.0, (now - self._last_ts).total_seconds())
        self._last_ts = now

        await self._update_baseline(battery_w, dt_s, signal, now)

        baseline_w = None
        if self.baseline_enabled:
            baseline_w = None
            if self._baseline_samples > 0:
                baseline_w = self._baseline_sum_w / max(1, self._baseline_samples)
            else:
                baseline_w = self._baseline_last_w
            mffr_power_w = abs(battery_w - (baseline_w or 0.0))
        else:
            mffr_power_w = abs(battery_w)

        slot_start = _quarter_start(now)
        slot_end = slot_start + timedelta(minutes=15)

        if signal in ("UP", "DOWN"):
            if not self._active_slot:
                was_backup = not (now.minute % 15 == 0 and now.second < 10)
                self._active_slot = Slot(start=slot_start, end=slot_end, signal=signal, was_backup=was_backup)
                self._active_idle_s = 0.0
            if self._active_slot and self._active_slot.signal != signal:
                self._finalize_active_slot()
                self._active_slot = Slot(start=slot_start, end=slot_end, signal=signal, was_backup=True)
                self._active_idle_s = 0.0

            if self._active_slot:
                self._active_slot.nordpool_price = chosen_nps_price
                self._active_slot.mffr_price = mffr_price
                self._active_slot.baseline_w = self._active_slot.baseline_w if self._active_slot.baseline_w is not None else baseline_w
                self._active_slot.energy_kwh += (mffr_power_w * dt_s) / 3_600_000.0
                self._active_slot.duration_s += dt_s

                # Early cancellation heuristic: if MFFR power collapses close to baseline
                # and stays low for a while while the signal still claims active, treat as cancelled.
                try:
                    low_threshold = 100.0  # W
                    grace_seconds = 60.0   # s
                    if mffr_power_w <= low_threshold:
                        self._active_idle_s += dt_s
                    else:
                        self._active_idle_s = 0.0
                    if self._active_idle_s >= grace_seconds:
                        self._active_slot.cancelled = True
                        self._finalize_active_slot()
                        self._active_idle_s = 0.0
                except Exception:
                    # Never let heuristic break updates
                    self._active_idle_s = 0.0
        else:
            if self._active_slot:
                self._active_slot.cancelled = True
                self._finalize_active_slot()
                self._active_idle_s = 0.0

        # Finalize strictly based on the active slot's stored end time.
        # Using a "now"-derived slot_end can miss the boundary right after a quarter rollover
        # and delay finalization until the next quarter.
        if self._active_slot and now >= self._active_slot.end:
            self._finalize_active_slot()
            self._active_idle_s = 0.0

        # Backfill profits for recent finalized slots if prices became available later
        backfilled = False
        for s in list(self._recent_slots):
            if s.profit is not None or not s.energy_kwh or s.energy_kwh <= 0:
                continue

            cached_prices = self._get_slot_prices_for(s.start)
            cached_mffr = self._normalize_price(cached_prices.get("mfrr_price"))
            if s.mffr_price is None and cached_mffr is not None:
                s.mffr_price = cached_mffr

            cached_nps, _ = self._select_nps_price(cached_prices, None)
            if s.nordpool_price is None and cached_nps is not None:
                s.nordpool_price = cached_nps

            if s.nordpool_price is None or s.mffr_price is None:
                continue

            fee = self.fusebox_fee_pct / 100.0
            if s.signal == "UP":
                s.profit = (s.mffr_price - s.nordpool_price) * s.energy_kwh * (1 - fee)
            elif s.signal == "DOWN":
                s.profit = (s.nordpool_price - s.mffr_price) * s.energy_kwh * (1 - fee)
            else:
                s.profit = 0.0
            self._today_profit += s.profit
            self._week_profit += s.profit
            self._month_profit += s.profit
            self._year_profit += s.profit
            self._all_profit += s.profit
            backfilled = True
        if backfilled:
            self.hass.async_create_task(self._async_save_state())

        data: Dict[str, Any] = {
            "signal": signal,
            "mffr_power_w": round(mffr_power_w, 2),
            "slot_energy_kwh": round(self._active_slot.energy_kwh, 6) if self._active_slot else 0.0,
            "slot_profit": round(self._active_slot.profit, 4) if (self._active_slot and self._active_slot.profit is not None) else None,
            "today_profit": round(self._today_profit, 4),
            "up_count": self._up_count,
            "down_count": self._down_count,
            "week_profit": round(self._week_profit, 4),
            "month_profit": round(self._month_profit, 4),
            "year_profit": round(self._year_profit, 4),
            "all_time_profit": round(self._all_profit, 4),
            "slot_start": slot_start,
            "slot_end": slot_end,
            # Expose the chosen NPS price
            "nordpool_price": chosen_nps_price,
            "mffr_price": mffr_price,
            "nps_source_active": active_source,
            "price_cache_hit": bool(slot_prices),
            "last_price_fetch": self._last_price_fetch,
            "was_backup": bool(self._active_slot.was_backup) if self._active_slot else False,
            "cancelled": bool(self._active_slot.cancelled) if self._active_slot else False,
            "baseline_w": round(baseline_w, 2) if baseline_w is not None else None,
            "duration_minutes": round((self._active_slot.duration_s / 60.0), 2) if self._active_slot else 0.0,
            "recent_slots": [
                {
                    "timeslot": s.start.isoformat(),
                    "signal": s.signal,
                    "energy_kwh": round(s.energy_kwh, 6),
                    "profit": round(s.profit, 4) if s.profit is not None else None,
                    "was_backup": s.was_backup,
                    "cancelled": s.cancelled,
                    "baseline_w": round(s.baseline_w, 2) if s.baseline_w is not None else None,
                    "mffr_price": s.mffr_price,
                    "nordpool_price": s.nordpool_price,
                }
                for s in list(self._recent_slots)
            ],
        }
        return data

    async def _async_update_data(self) -> Dict[str, Any]:
        return await self._async_update_logic()
