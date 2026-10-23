"""Generate a reproducible SQLite dataset for the European first-mile network.

Flow: shipper warehouse -> truck run (direct or milkrun) -> node.
Planning is daily: each shipper gets a pickup forecast for every day it
operates, trucks are planned against that forecast, and actual volume is
what the truck picks up. See docs/data_model.md for definitions.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import random
import sqlite3

import numpy as np
import pandas as pd
from faker import Faker

SEED = 42
START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 9, 30)
# Last 60 days of the dataset: recently onboarded shippers get more compliance holds.
RECENT_ONBOARD_FROM = date(2026, 8, 1)
# Black Friday 2025 through Christmas Eve: peak inbound volume.
PEAK_START = date(2025, 11, 28)
PEAK_END = date(2025, 12, 24)
BOTTLENECK_NODE = "N-UK-01"
BOTTLENECK_SHIPPERS = 50  # first 50 UK shippers deliver to the tight node

# Shipper schedules (spec: 80% Mon-Fri, 10% Mon-Sun, 10% six-day).
# Python weekday numbers: Mon=0 ... Sun=6.
SCHEDULES = {
    "Mon-Fri": {0, 1, 2, 3, 4},
    "Mon-Sun": {0, 1, 2, 3, 4, 5, 6},
    "Mon-Sat": {0, 1, 2, 3, 4, 5},
    "Tue-Sun": {1, 2, 3, 4, 5, 6},
}

# Account managers per country (25 in total).
AM_COUNT = {"UK": 7, "FR": 6, "IT": 6, "ES": 6}

# Planted-scenario rates.
OPT_IN_HOLIDAY_RATE = 0.15      # shippers that agreed to ship on bank holidays
UNPLANNED_HOLIDAY_RATE = 0.06   # non-opted-in shippers that ship anyway (scenario 9)
OFFDAY_SHIP_RATE = 0.004        # shippers shipping on a non-operating day (scenario 10)
WASTED_RATE_NORMAL = 0.0025     # shipper closed when the truck arrives (scenario 11)
WASTED_RATE_UNRELIABLE = 0.045  # repeat offenders, concentrated in 3 AM portfolios
ADHOC_COST_MULT = 1.6           # same-day truck premium

# Milkrun stops are planned 40 minutes apart.
STOP_GAP_MIN = 40

COUNTRIES = ["UK", "FR", "IT", "ES"]
CITIES = {
    "UK": [
        "London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Liverpool",
        "Bristol", "Newcastle", "Sheffield", "Edinburgh", "Cardiff", "Nottingham",
        "Southampton", "Leicester", "Cambridge",
    ],
    "FR": [
        "Paris", "Lyon", "Marseille", "Lille", "Toulouse", "Bordeaux", "Nantes",
        "Nice", "Strasbourg", "Rennes", "Montpellier", "Grenoble", "Rouen",
        "Dijon", "Tours",
    ],
    "IT": [
        "Milan", "Rome", "Turin", "Naples", "Bologna", "Florence", "Venice",
        "Verona", "Genoa", "Bari", "Padua", "Palermo", "Catania", "Brescia",
        "Modena",
    ],
    "ES": [
        "Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Malaga",
        "Zaragoza", "Alicante", "Murcia", "Vigo", "Valladolid", "Palma",
        "Gijon", "Cordoba", "Granada",
    ],
}
CARRIERS = [
    "DHL Freight", "XPO Logistics", "Kuehne+Nagel", "DB Schenker",
    "Wincanton", "Dachser", "CEVA Logistics", "GEFCO",
]
LOCALES = {"UK": "en_GB", "FR": "fr_FR", "IT": "it_IT", "ES": "es_ES"}


def sunday_of(d):
    """Return the Sunday that starts the (Sun-Sat) week containing date d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def generate_holidays():
    """Real public holidays for UK, FR, IT, ES in 2025 and 2026.

    Hard-coded so we do not need an extra holidays library, and so Ferragosto
    (scenario 5) is definitely present.
    """
    rows = [
        # United Kingdom
        ("UK", date(2025, 1, 1), "New Year's Day"),
        ("UK", date(2025, 4, 18), "Good Friday"),
        ("UK", date(2025, 4, 21), "Easter Monday"),
        ("UK", date(2025, 5, 5), "Early May Bank Holiday"),
        ("UK", date(2025, 5, 26), "Spring Bank Holiday"),
        ("UK", date(2025, 8, 25), "Summer Bank Holiday"),
        ("UK", date(2025, 12, 25), "Christmas Day"),
        ("UK", date(2025, 12, 26), "Boxing Day"),
        ("UK", date(2026, 1, 1), "New Year's Day"),
        ("UK", date(2026, 4, 3), "Good Friday"),
        ("UK", date(2026, 4, 6), "Easter Monday"),
        ("UK", date(2026, 5, 4), "Early May Bank Holiday"),
        ("UK", date(2026, 5, 25), "Spring Bank Holiday"),
        ("UK", date(2026, 8, 31), "Summer Bank Holiday"),
        ("UK", date(2026, 12, 25), "Christmas Day"),
        ("UK", date(2026, 12, 26), "Boxing Day"),
        ("UK", date(2026, 12, 28), "Boxing Day (substitute)"),
        # France
        ("FR", date(2025, 1, 1), "Jour de l'an"),
        ("FR", date(2025, 4, 21), "Lundi de Pâques"),
        ("FR", date(2025, 5, 1), "Fête du Travail"),
        ("FR", date(2025, 5, 8), "Victoire 1945"),
        ("FR", date(2025, 5, 29), "Ascension"),
        ("FR", date(2025, 6, 9), "Lundi de Pentecôte"),
        ("FR", date(2025, 7, 14), "Fête nationale"),
        ("FR", date(2025, 8, 15), "Assomption"),
        ("FR", date(2025, 11, 1), "Toussaint"),
        ("FR", date(2025, 11, 11), "Armistice"),
        ("FR", date(2025, 12, 25), "Noël"),
        ("FR", date(2026, 1, 1), "Jour de l'an"),
        ("FR", date(2026, 4, 6), "Lundi de Pâques"),
        ("FR", date(2026, 5, 1), "Fête du Travail"),
        ("FR", date(2026, 5, 8), "Victoire 1945"),
        ("FR", date(2026, 5, 14), "Ascension"),
        ("FR", date(2026, 5, 25), "Lundi de Pentecôte"),
        ("FR", date(2026, 7, 14), "Fête nationale"),
        ("FR", date(2026, 8, 15), "Assomption"),
        ("FR", date(2026, 11, 1), "Toussaint"),
        ("FR", date(2026, 11, 11), "Armistice"),
        ("FR", date(2026, 12, 25), "Noël"),
        # Italy: includes Ferragosto (15 Aug), used in scenario 5
        ("IT", date(2025, 1, 1), "Capodanno"),
        ("IT", date(2025, 1, 6), "Epifania"),
        ("IT", date(2025, 4, 21), "Lunedì dell'Angelo"),
        ("IT", date(2025, 4, 25), "Festa della Liberazione"),
        ("IT", date(2025, 5, 1), "Festa del Lavoro"),
        ("IT", date(2025, 6, 2), "Festa della Repubblica"),
        ("IT", date(2025, 8, 15), "Ferragosto"),
        ("IT", date(2025, 11, 1), "Ognissanti"),
        ("IT", date(2025, 12, 8), "Immacolata Concezione"),
        ("IT", date(2025, 12, 25), "Natale"),
        ("IT", date(2025, 12, 26), "Santo Stefano"),
        ("IT", date(2026, 1, 1), "Capodanno"),
        ("IT", date(2026, 1, 6), "Epifania"),
        ("IT", date(2026, 4, 6), "Lunedì dell'Angelo"),
        ("IT", date(2026, 4, 25), "Festa della Liberazione"),
        ("IT", date(2026, 5, 1), "Festa del Lavoro"),
        ("IT", date(2026, 6, 2), "Festa della Repubblica"),
        ("IT", date(2026, 8, 15), "Ferragosto"),
        ("IT", date(2026, 11, 1), "Ognissanti"),
        ("IT", date(2026, 12, 8), "Immacolata Concezione"),
        ("IT", date(2026, 12, 25), "Natale"),
        ("IT", date(2026, 12, 26), "Santo Stefano"),
        # Spain
        ("ES", date(2025, 1, 1), "Año Nuevo"),
        ("ES", date(2025, 1, 6), "Reyes"),
        ("ES", date(2025, 4, 18), "Viernes Santo"),
        ("ES", date(2025, 5, 1), "Día del Trabajo"),
        ("ES", date(2025, 8, 15), "Asunción"),
        ("ES", date(2025, 10, 12), "Fiesta Nacional de España"),
        ("ES", date(2025, 11, 1), "Todos los Santos"),
        ("ES", date(2025, 12, 6), "Día de la Constitución"),
        ("ES", date(2025, 12, 8), "Inmaculada Concepción"),
        ("ES", date(2025, 12, 25), "Navidad"),
        ("ES", date(2026, 1, 1), "Año Nuevo"),
        ("ES", date(2026, 1, 6), "Reyes"),
        ("ES", date(2026, 4, 3), "Viernes Santo"),
        ("ES", date(2026, 5, 1), "Día del Trabajo"),
        ("ES", date(2026, 8, 15), "Asunción"),
        ("ES", date(2026, 10, 12), "Fiesta Nacional de España"),
        ("ES", date(2026, 11, 1), "Todos los Santos"),
        ("ES", date(2026, 12, 6), "Día de la Constitución"),
        ("ES", date(2026, 12, 8), "Inmaculada Concepción"),
        ("ES", date(2026, 12, 25), "Navidad"),
    ]
    return pd.DataFrame(rows, columns=["country", "holiday_date", "holiday_name"])


def generate_nodes(rng):
    """10 nodes per country. One UK warehouse is undersized so peak season overflows."""
    rows = []
    for country in COUNTRIES:
        cities = CITIES[country]
        for i in range(10):
            node_id = f"N-{country}-{i + 1:02d}"
            # First 3 nodes in each country are larger warehouses.
            node_type = "warehouse" if i < 3 else "delivery_station"
            city = cities[i % len(cities)]
            if node_type == "warehouse":
                capacity = int(rng.integers(450, 801))
            else:
                capacity = int(rng.integers(180, 401))
            if node_id == BOTTLENECK_NODE:
                # Fine in normal weeks, too small for peak volume (scenario 3).
                capacity = 150
            rows.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "country": country,
                    "city": city,
                    "daily_capacity_pallets": capacity,
                }
            )
    return pd.DataFrame(rows)


def generate_account_managers():
    """25 Account Managers (AMs), each working one country.

    The first AM in UK, FR and IT owns the 'problem' portfolios used in
    scenario 11 (shippers that close without notice).
    """
    rows = []
    for country in COUNTRIES:
        fake = Faker(LOCALES[country])
        fake.seed_instance(SEED + 100 + COUNTRIES.index(country))
        for i in range(AM_COUNT[country]):
            rows.append(
                {
                    "name": fake.name(),
                    "country": country,
                    "is_problem_portfolio": i == 0 and country in ("UK", "FR", "IT"),
                }
            )
    return rows


def generate_shippers(rng, nodes):
    """1000 shippers, 250 per country, with flags used later for planted scenarios.

    Columns starting with '_' are hidden helpers; they drive the simulation
    but are dropped before saving.
    """
    nodes_by_country = {
        c: nodes.loc[nodes["country"] == c, "node_id"].tolist() for c in COUNTRIES
    }
    ams = generate_account_managers()
    ams_by_country = defaultdict(list)
    for am in ams:
        ams_by_country[am["country"]].append(am)

    rows = []
    shipper_num = 0
    for country in COUNTRIES:
        local_fake = Faker(LOCALES[country])
        local_fake.seed_instance(SEED + COUNTRIES.index(country))
        home_nodes = nodes_by_country[country]
        for i in range(250):
            shipper_num += 1
            # Send a share of UK shippers to the bottleneck node (scenario 3).
            if country == "UK" and i < BOTTLENECK_SHIPPERS:
                home_node = BOTTLENECK_NODE
            else:
                # Spread everyone else over the country's other nodes.
                others = [n for n in home_nodes if n != BOTTLENECK_NODE]
                home_node = others[int(rng.integers(0, len(others)))]
            am = ams_by_country[country][int(rng.integers(0, AM_COUNT[country]))]
            rows.append(
                {
                    "shipper_id": f"S{shipper_num:04d}",
                    "name": f"{local_fake.company()} {shipper_num}",
                    "country": country,
                    "city": str(rng.choice(CITIES[country])),
                    "onboarded_date": None,
                    "status": "active",
                    "delisted_date": None,
                    "operating_days": None,
                    "ships_on_holidays": 0,
                    "account_manager": am["name"],
                    "_home_node_id": home_node,
                    "_problem_am": am["is_problem_portfolio"],
                }
            )

    df = pd.DataFrame(rows)
    n = len(df)

    # Operating schedule: 80% Mon-Fri, 10% Mon-Sun, 10% six days.
    schedule = rng.choice(
        ["Mon-Fri", "Mon-Sun", "Mon-Sat", "Tue-Sun"], size=n, p=[0.80, 0.10, 0.05, 0.05]
    )
    df["operating_days"] = schedule
    df["ships_on_holidays"] = (rng.random(n) < OPT_IN_HOLIDAY_RATE).astype(int)

    # Size sets the typical daily volume (packages) for the shipper.
    size = rng.choice(["S", "M", "L"], size=n, p=[0.50, 0.35, 0.15])
    base = np.where(
        size == "S", rng.integers(12, 41, n),
        np.where(size == "M", rng.integers(35, 91, n), rng.integers(90, 221, n)),
    )
    df["_base_packages"] = base

    # Most shippers joined before 2025; a slice is recent (scenario 7).
    recent_idx = set(rng.choice(df.index, size=32, replace=False).tolist())
    onboard, is_recent = [], []
    span = (date(2026, 7, 1) - date(2023, 1, 1)).days
    for idx in df.index:
        if idx in recent_idx:
            d = RECENT_ONBOARD_FROM + timedelta(days=int(rng.integers(0, 40)))
            onboard.append(min(d, END_DATE - timedelta(days=7)))
            is_recent.append(True)
        else:
            onboard.append(date(2023, 1, 1) + timedelta(days=int(rng.integers(0, span))))
            is_recent.append(False)
    df["onboarded_date"] = pd.Series(onboard, dtype=object)
    df["_is_recent"] = is_recent

    # Scenario 8: de-listed shippers stop shipping on delisted_date.
    remaining = [i for i in df.index if i not in recent_idx]
    delist_pool = [i for i in remaining if df.at[i, "onboarded_date"] < date(2025, 6, 1)]
    delist_idx = set(rng.choice(delist_pool, size=48, replace=False).tolist())
    delisted = [None] * n
    status = ["active"] * n
    for idx in delist_idx:
        ob = df.at[idx, "onboarded_date"]
        earliest = max(ob + timedelta(days=90), START_DATE + timedelta(days=30))
        latest = END_DATE - timedelta(days=30)
        gap = max(1, (latest - earliest).days)
        delisted[idx] = earliest + timedelta(days=int(rng.integers(0, gap)))
        status[idx] = "de-listed"
    df["delisted_date"] = pd.Series(delisted, dtype=object)
    df["status"] = status

    # Scenario 4: a few established shippers always over-forecast.
    over_pool = [
        i for i in remaining
        if i not in delist_idx and df.at[i, "onboarded_date"] < date(2025, 1, 1)
    ]
    over_idx = set(rng.choice(over_pool, size=12, replace=False).tolist())
    df["_overforecast"] = [i in over_idx for i in df.index]

    # Scenario 11: shippers that close without notice. Mostly in the
    # three problem AM portfolios, plus a handful elsewhere.
    problem = df.index[df["_problem_am"]].tolist()
    others = df.index[~df["_problem_am"]].tolist()
    unreliable = set(rng.choice(problem, size=int(len(problem) * 0.6), replace=False).tolist())
    unreliable |= set(rng.choice(others, size=6, replace=False).tolist())
    df["_unreliable"] = [i in unreliable for i in df.index]

    # H5 truth: a few 'slow loaders' delay every truck they are on.
    slow_idx = set(rng.choice(df.index, size=20, replace=False).tolist())
    df["_slow_loader"] = [i in slow_idx for i in df.index]
    return df


def generate_truck_runs(shippers, nodes, holidays, rng):
    """Simulate each day: forecast, plan trucks, pick up, deliver to node.

    Returns the truck_runs table and a 'pending' dict holding the rows for
    run_stops, shipments and forecasts, so every table stays linked:
    shipment -> run -> node, run_stops -> run, forecast -> shipper/day.
    """
    holiday_set = {(r.country, r.holiday_date) for r in holidays.itertuples(index=False)}

    # Scenario 6: winter weather closures, mostly UK working days.
    winter_days = pd.bdate_range("2025-12-01", "2026-02-27").date
    uk_weather = set(rng.choice(winter_days, size=16, replace=False))
    fr_weather = set(rng.choice(winter_days, size=2, replace=False))

    node_capacity = dict(zip(nodes["node_id"], nodes["daily_capacity_pallets"]))

    by_country = defaultdict(list)
    for rec in shippers.to_dict("records"):
        rec["_weekdays"] = SCHEDULES[rec["operating_days"]]
        by_country[rec["country"]].append(rec)

    all_days = list(pd.date_range(START_DATE, END_DATE).date)
    carry = defaultdict(int)  # holiday volume shifted to the next operating day
    pallet_load_by_node_day = defaultdict(int)

    runs, stops, shipments, forecasts = [], [], [], []
    counters = {"run": 0, "ship": 0}

    def next_id(kind, width, prefix):
        counters[kind] += 1
        return f"{prefix}{counters[kind]:0{width}d}"

    def stop_delay(shipper, run_type):
        """Minutes late at one pickup stop. Milkruns run tighter schedules."""
        if run_type == "direct":
            d = int(rng.choice([0, 5, 10, 20, 40], p=[0.40, 0.25, 0.18, 0.12, 0.05]))
        else:
            d = int(rng.choice([0, 10, 20, 35, 55], p=[0.45, 0.25, 0.15, 0.10, 0.05]))
        if shipper["_slow_loader"]:
            d += int(rng.integers(45, 100))
        return d

    def make_run(day, country, run_type, legs, weather_close, is_adhoc=False, wasted=False):
        """One truck. legs = list of (shipper, actual_packages, forecast_packages).

        direct = 1 leg, milkrun = 2-4 legs. A wasted run visits one shipper
        that turns out to be closed: no pickup, no shipments, full cost.
        """
        node_id = legs[0][0]["_home_node_id"]
        peak = PEAK_START <= day <= PEAK_END
        run_id = next_id("run", 6, "R")

        pickup_hour = int(rng.integers(5, 10))
        pickup_min = int(rng.choice([0, 15, 30, 45]))
        planned_first = datetime.combine(day, time(pickup_hour, pickup_min))
        drive_min = int(rng.integers(150, 361)) if run_type == "direct" else int(rng.integers(120, 301))
        planned_last = planned_first + timedelta(minutes=STOP_GAP_MIN * (len(legs) - 1))
        # Transport Planning adds a buffer: 30 minutes, plus 10 per extra milkrun stop.
        buffer_min = 30 + 10 * (len(legs) - 1)
        planned_arrival = planned_last + timedelta(minutes=drive_min + buffer_min)

        is_no_show = (not weather_close) and (not wasted) and rng.random() < 0.007
        cancelled_run = is_no_show or weather_close
        is_partial = (not cancelled_run) and (not wasted) and rng.random() < 0.018

        total_packages = total_pallets = forecast_pallets = 0
        prev_actual = None
        first_shipment = len(shipments)  # shipments created by this run start here
        for seq, (shipper, packages, fc_packages) in enumerate(legs, start=1):
            planned_stop = planned_first + timedelta(minutes=STOP_GAP_MIN * (seq - 1))
            if cancelled_run:
                actual_stop = None
            else:
                ready = planned_stop if prev_actual is None else max(
                    planned_stop, prev_actual + timedelta(minutes=STOP_GAP_MIN)
                )
                actual_stop = ready + timedelta(minutes=stop_delay(shipper, run_type))
                prev_actual = actual_stop

            forecast_pallets += max(1, round((fc_packages or packages) / 28))
            picked = 0
            if not wasted:
                if is_partial and seq == 1:
                    packages = max(4, packages // 2)  # shipper not ready: half loaded
                # Large daily volumes are split into two shipments.
                parts = [packages] if packages < 120 else [packages // 2, packages - packages // 2]
                for part in parts:
                    pallets = max(1, int(round(part / float(rng.uniform(18, 40)))))
                    service = "1DD" if rng.random() < 0.45 else "NDD"
                    created = day if rng.random() < 0.8 else day - timedelta(days=1)
                    if created < shipper["onboarded_date"]:
                        created = day

                    # Scenario 3: once the bottleneck node is full, freight rolls over.
                    overflow_days = 0
                    if not cancelled_run:
                        already = pallet_load_by_node_day[(node_id, day)]
                        if node_id == BOTTLENECK_NODE and peak and already + pallets > node_capacity[node_id]:
                            overflow_days = 1 if rng.random() < 0.7 else 2
                        pallet_load_by_node_day[(node_id, day)] += pallets

                    shipments.append(
                        {
                            "shipment_id": next_id("ship", 7, "SH"),
                            "shipper_id": shipper["shipper_id"],
                            "run_id": run_id,
                            "node_id": node_id,
                            "service_level": service,
                            "created_date": created,
                            "packages": part,
                            "pallets": pallets,
                            "run_type": run_type,
                            "country": country,
                            "is_recent": bool(shipper["_is_recent"]),
                            "is_cancelled_run": cancelled_run,
                            "overflow_days": overflow_days,
                            "arrival_day": None,  # filled after arrival is known
                        }
                    )
                    picked += pallets
                    total_packages += part
                    total_pallets += pallets

            stops.append(
                {
                    "run_id": run_id,
                    "shipper_id": shipper["shipper_id"],
                    "stop_sequence": seq,
                    "planned_pickup_time": planned_stop,
                    "actual_pickup_time": actual_stop,
                    "pallets_picked": picked,
                }
            )

        # Arrival at the node follows the last pickup (delays build up on milkruns).
        actual_first = stops[-len(legs)]["actual_pickup_time"]  # None if cancelled
        if cancelled_run or wasted:
            actual_arrival = None  # never reached the node
        else:
            noise = int(rng.integers(-25, 26))
            actual_arrival = prev_actual + timedelta(minutes=drive_min + noise)
            if peak:
                actual_arrival += timedelta(minutes=int(rng.integers(0, 40)))
            for shp in shipments[first_shipment:]:
                shp["arrival_day"] = actual_arrival.date()

        # Trucks are booked against the forecast. Over-forecasters leave space empty
        # (scenario 4); wasted runs carry nothing.
        util_target = float(rng.uniform(0.78, 0.95))
        planned_pallets = forecast_pallets if not is_adhoc else max(1, total_pallets)
        pallet_capacity = max(total_pallets, int(np.ceil(planned_pallets / util_target)))

        # Cost = fixed truck cost + pallets. Milkruns share the fixed cost across
        # several shippers, so cost per package is lower (scenario 2).
        if run_type == "milkrun":
            cost = 220 + 15 * pallet_capacity + 40 * (len(legs) - 1)
        else:
            cost = 180 + 25 * pallet_capacity
        cost *= float(rng.uniform(0.9, 1.2))
        if is_adhoc:
            cost *= ADHOC_COST_MULT

        runs.append(
            {
                "run_id": run_id,
                "run_date": day,
                "run_type": run_type,
                "carrier": str(rng.choice(CARRIERS)),
                "node_id": node_id,
                "planned_pickup_time": planned_first,
                "actual_pickup_time": actual_first,
                "planned_arrival_time": planned_arrival,
                "actual_arrival_time": actual_arrival,
                "pallet_capacity": int(pallet_capacity),
                "pallets_loaded": int(total_pallets),
                "cost_eur": round(cost, 2),
                "is_adhoc": int(is_adhoc),
                "run_outcome": "wasted" if wasted else "completed",
                "_is_no_show": is_no_show,
                "_is_weather": weather_close,
                "_is_partial": is_partial,
            }
        )

    for day in all_days:
        peak = PEAK_START <= day <= PEAK_END
        for country in COUNTRIES:
            is_holiday = (country, day) in holiday_set
            weather_today = (country == "UK" and day in uk_weather) or (
                country == "FR" and day in fr_weather
            )

            planned, adhoc = [], []
            for s in by_country[country]:
                if day < s["onboarded_date"]:
                    continue
                if s["delisted_date"] is not None and day >= s["delisted_date"]:
                    continue  # scenario 8: nothing after de-listing
                operates = day.weekday() in s["_weekdays"]

                if is_holiday and not s["ships_on_holidays"]:
                    if operates and rng.random() < UNPLANNED_HOLIDAY_RATE:
                        adhoc.append(s)  # scenario 9: ships without telling us
                    elif operates:
                        carry[s["shipper_id"]] += 1  # scenario 5: shift to next day
                    continue
                if operates:
                    planned.append(s)
                elif rng.random() < OFFDAY_SHIP_RATE:
                    adhoc.append(s)  # scenario 10: volume on a non-operating day

            # Volume multiplier for the day (planners know about peak).
            def day_mult(s):
                m = 1.0
                if peak:
                    m = 2.6 if s["_home_node_id"] == BOTTLENECK_NODE else 1.8
                return m

            legs_today = []
            for s in planned:
                mult = day_mult(s) * (1 + 0.8 * carry.pop(s["shipper_id"], 0))
                fc = max(5, int(round(s["_base_packages"] * mult * float(rng.uniform(0.8, 1.2)))))
                forecasts.append(
                    {"shipper_id": s["shipper_id"], "forecast_date": day, "forecast_packages": fc}
                )
                # Actual = forecast x attainment factor.
                factor = float(rng.uniform(0.66, 0.74)) if s["_overforecast"] else float(rng.uniform(0.90, 1.10))
                actual = max(4, int(round(fc * factor)))

                wasted_rate = WASTED_RATE_UNRELIABLE if s["_unreliable"] else WASTED_RATE_NORMAL
                if rng.random() < wasted_rate:
                    # Scenario 11: truck arrives, shipper closed.
                    make_run(day, country, "direct", [(s, 0, fc)], False, wasted=True)
                    continue
                legs_today.append((s, actual, fc))

            # Unplanned volume gets a same-day ad-hoc truck.
            for s in adhoc:
                actual = max(4, int(round(s["_base_packages"] * day_mult(s) * float(rng.uniform(0.6, 1.1)))))
                make_run(day, country, "direct", [(s, actual, None)], False, is_adhoc=True)

            if not legs_today:
                continue

            # About a third of planned pickups ride a milkrun with same-city shippers.
            order = rng.permutation(len(legs_today))
            legs_today = [legs_today[i] for i in order]
            n_milk = int(len(legs_today) * 0.35)
            milk_candidates, direct_legs = legs_today[:n_milk], legs_today[n_milk:]
            by_city = defaultdict(list)
            for leg in milk_candidates:
                by_city[leg[0]["city"]].append(leg)

            for group in by_city.values():
                i = 0
                while i < len(group):
                    remaining = len(group) - i
                    if remaining < 2:
                        direct_legs.extend(group[i:])
                        break
                    n_stops = min(int(rng.integers(2, 5)), remaining)
                    if remaining - n_stops == 1:  # avoid one stranded shipper
                        n_stops = remaining if remaining <= 4 else n_stops - 1
                    chunk = group[i: i + n_stops]
                    i += n_stops
                    close = weather_today and rng.random() < 0.70
                    make_run(day, country, "milkrun", chunk, close)

            for leg in direct_legs:
                close = weather_today and rng.random() < 0.70
                make_run(day, country, "direct", [leg], close)

    truck_runs = pd.DataFrame(runs)
    pending = {"stops": stops, "shipments": shipments, "forecasts": forecasts}
    return truck_runs, pending


def generate_run_stops(pending):
    """One row per shipper visited on each run, with per-stop pickup times."""
    return pd.DataFrame(pending["stops"])


def generate_forecasts(pending):
    """Daily pickup forecasts, only for days each shipper operates.

    No row = no forecast (bank holiday without opt-in, or non-operating day).
    """
    return pd.DataFrame(pending["forecasts"])


def generate_shipments(pending, rng):
    """Apply status, promise, delivery and hold rules on top of picked-up shipments."""
    df = pd.DataFrame(pending["shipments"])
    n = len(df)

    created = pd.to_datetime(df["created_date"])
    ndd_offset = rng.integers(2, 4, size=n)  # NDD = created + 2 or 3 days
    promised = created + pd.to_timedelta(
        np.where(df["service_level"].to_numpy() == "1DD", 1, ndd_offset), unit="D"
    )

    arrival = pd.to_datetime(df["arrival_day"])
    delivered = arrival + pd.to_timedelta(df["overflow_days"].to_numpy().astype(int), unit="D")

    status = np.full(n, "Delivered to Node", dtype=object)
    hold_reason = np.full(n, None, dtype=object)

    # Weather closures and no-shows cancel the freight on that truck.
    cancelled = df["is_cancelled_run"].to_numpy(dtype=bool) | (rng.random(n) < 0.006)
    status[cancelled] = "Cancelled"

    # Scenario 1: ~8% of UK shipments sit at customs. Other countries ~0.
    uk = (df["country"].to_numpy() == "UK") & (status != "Cancelled")
    customs = uk & (rng.random(n) < 0.086)
    status[customs] = "On Hold"
    hold_reason[customs] = "At Customs"

    # Scenario 7: recently onboarded shippers have more compliance holds.
    open_mask = status == "Delivered to Node"
    is_recent = df["is_recent"].to_numpy(dtype=bool)
    rec_hold = is_recent & open_mask & (rng.random(n) < 0.17)
    old_hold = (~is_recent) & open_mask & (rng.random(n) < 0.010)
    status[rec_hold | old_hold] = "On Hold"
    hold_reason[rec_hold | old_hold] = "Shipper Compliance"

    # Last few days of the dataset still have work in progress.
    near_end = (created >= pd.Timestamp(END_DATE - timedelta(days=4))).to_numpy() & (
        status == "Delivered to Node"
    )
    roll = rng.random(n)
    status[near_end & (roll < 0.25)] = "Created"
    status[near_end & (roll >= 0.25) & (roll < 0.50)] = "Picked Up"
    status[near_end & (roll >= 0.50) & (roll < 0.78)] = "In Transit"

    # Same-day node arrival meets most promises, so push a slice of milkruns
    # (and all peak overflow) past promised_date (scenario 2 and 3).
    late_date = promised + pd.Timedelta(days=1)
    still_delivered = status == "Delivered to Node"
    is_milk = df["run_type"].to_numpy() == "milkrun"
    force_late = still_delivered & (
        (is_milk & (rng.random(n) < 0.22))
        | (~is_milk & (rng.random(n) < 0.055))
        | (df["overflow_days"].to_numpy() > 0)
    )
    delivered = delivered.mask(force_late, np.maximum(delivered, late_date))

    delivered_date = np.where(
        status == "Delivered to Node", delivered.dt.strftime("%Y-%m-%d").to_numpy(), None
    )
    hold_reason = np.where(status == "On Hold", hold_reason, None)

    out = pd.DataFrame(
        {
            "shipment_id": df["shipment_id"],
            "shipper_id": df["shipper_id"],
            "run_id": df["run_id"],
            "node_id": df["node_id"],
            "service_level": df["service_level"],
            "created_date": created.dt.date,
            "promised_date": promised.dt.date,
            "delivered_to_node_date": delivered_date,
            "status": status,
            "hold_reason": hold_reason,
            "packages": df["packages"],
            "pallets": df["pallets"],
        }
    )
    # Kept for the exceptions table, dropped before saving.
    out["_overflow_days"] = df["overflow_days"].to_numpy()
    return out


def generate_exceptions(truck_runs, shipments, rng):
    """One exception row per operational failure, tied to a run and/or shipment."""
    rows = []

    def add(run_id, shipment_id, etype, on_date, resolved):
        rows.append(
            {
                "exception_id": f"E{len(rows) + 1:06d}",
                "run_id": run_id,
                "shipment_id": shipment_id,
                "exception_type": etype,
                "exception_date": on_date,
                "resolved_date": resolved,
            }
        )

    runs = truck_runs
    planned_arr = pd.to_datetime(runs["planned_arrival_time"])
    actual_arr = pd.to_datetime(runs["actual_arrival_time"])
    late = (actual_arr.notna() & (actual_arr > planned_arr)).to_numpy()

    for rec, is_late in zip(runs.to_dict("records"), late):
        d = rec["run_date"]
        if is_late:
            add(rec["run_id"], None, "Late arrival at node", d, d)
        if rec["_is_no_show"]:
            add(rec["run_id"], None, "Truck no-show", d, d)
        if rec["_is_weather"]:
            add(rec["run_id"], None, "Weather site closure", d, d + timedelta(days=1))
        if rec["_is_partial"]:
            add(rec["run_id"], None, "Partial pickup (shipper not ready)", d, d)
        if rec["is_adhoc"]:
            add(rec["run_id"], None, "Ad-hoc truck request", d, d)
        if rec["run_outcome"] == "wasted":
            add(rec["run_id"], None, "Shipper closed on arrival (wasted truck)", d, d)

    for rec in shipments.loc[shipments["hold_reason"] == "At Customs"].to_dict("records"):
        add(rec["run_id"], rec["shipment_id"], "Customs hold", rec["created_date"], None)

    for rec in shipments.loc[shipments["_overflow_days"] > 0].to_dict("records"):
        resolved = rec["created_date"] + timedelta(days=int(rec["_overflow_days"]))
        add(rec["run_id"], rec["shipment_id"], "Node capacity rejection", rec["created_date"], resolved)

    delivered = shipments.loc[shipments["status"] == "Delivered to Node"]
    n_dmg = max(1, int(len(delivered) * 0.003))
    dmg_idx = rng.choice(delivered.index, size=n_dmg, replace=False)
    for rec in delivered.loc[dmg_idx].to_dict("records"):
        add(rec["run_id"], rec["shipment_id"], "Damaged freight", rec["created_date"], rec["delivered_to_node_date"])

    out = pd.DataFrame(rows)
    return out.sort_values(["exception_date", "exception_id"]).reset_index(drop=True)


def _to_sql_dates(df, date_cols, datetime_cols):
    """Store dates/times as ISO text so SQLite stays easy to query."""
    out = df.copy()
    for col in date_cols:
        s = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
        out[col] = s.astype(object).where(s.notna(), None)
    for col in datetime_cols:
        s = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        out[col] = s.astype(object).where(s.notna(), None)
    return out


# Indexes on the columns queries join and filter on. Without them every join scans
# the full 411k-row tables, and AI-written queries can hit the 30 s timeout.
INDEXES = [
    "CREATE INDEX idx_shipments_run ON shipments(run_id)",
    "CREATE INDEX idx_shipments_shipper ON shipments(shipper_id)",
    "CREATE INDEX idx_runs_date ON truck_runs(run_date)",
    "CREATE INDEX idx_runs_node ON truck_runs(node_id)",
    "CREATE INDEX idx_stops_run ON run_stops(run_id)",
    "CREATE INDEX idx_stops_shipper ON run_stops(shipper_id)",
    "CREATE INDEX idx_forecasts_shipper_date ON forecasts(shipper_id, forecast_date)",
    "CREATE INDEX idx_holidays_country_date ON holidays(country, holiday_date)",
    "CREATE INDEX idx_exceptions_run ON exceptions(run_id)",
    "CREATE INDEX idx_exceptions_shipment ON exceptions(shipment_id)",
]


def save_database(tables, path="logistics.db"):
    conn = sqlite3.connect(path)
    for name, df in tables.items():
        df.to_sql(name, conn, if_exists="replace", index=False)
    for statement in INDEXES:
        conn.execute(statement)
    # ANALYZE records table sizes so SQLite picks the right index.
    # Without it, some queries got slower with the indexes than without.
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


def print_checks(path="logistics.db"):
    """Re-read the saved database and print the checks from the spec."""
    conn = sqlite3.connect(path)
    q = lambda sql: pd.read_sql(sql, conn)

    print("\nRow counts")
    for t in ["shippers", "nodes", "truck_runs", "run_stops", "shipments",
              "forecasts", "holidays", "exceptions"]:
        print(f"  {t:12s} {q(f'SELECT COUNT(*) n FROM {t}')['n'][0]:,}")

    print("\nOn-time rate and cost per package by run_type")
    print(q("""
        WITH sh AS (
            SELECT tr.run_type,
                   AVG(CASE WHEN s.delivered_to_node_date <= s.promised_date THEN 1.0 ELSE 0 END) AS on_time,
                   SUM(s.packages) AS packages
            FROM shipments s JOIN truck_runs tr ON tr.run_id = s.run_id
            WHERE s.status <> 'Cancelled' GROUP BY tr.run_type),
        c AS (SELECT run_type, SUM(cost_eur) AS cost FROM truck_runs GROUP BY run_type)
        SELECT sh.run_type, ROUND(100 * on_time, 1) AS on_time_pct,
               ROUND(c.cost / sh.packages, 2) AS cost_per_package_eur
        FROM sh JOIN c USING (run_type)
    """).to_string(index=False))

    # CASE (not AVG(hold_reason = ...)) so NULL hold_reason rows count as 0.
    pct = q("""SELECT 100.0 * AVG(CASE WHEN s.hold_reason = 'At Customs' THEN 1 ELSE 0 END) p
               FROM shipments s JOIN shippers sh USING (shipper_id) WHERE sh.country = 'UK'""")["p"][0]
    print(f"\n% UK shipments with customs hold: {pct:.1f}%")

    r = q("""SELECT 100.0 * AVG(is_adhoc) adhoc, 100.0 * AVG(run_outcome = 'wasted') wasted
             FROM truck_runs""")
    print(f"% of runs ad-hoc: {r['adhoc'][0]:.2f}%   % of runs wasted: {r['wasted'][0]:.2f}%")

    print("\nTop 3 AMs by wasted-truck cost")
    print(q("""
        SELECT sh.account_manager, COUNT(*) AS wasted_runs, ROUND(SUM(tr.cost_eur)) AS wasted_cost_eur
        FROM truck_runs tr JOIN run_stops rs USING (run_id) JOIN shippers sh USING (shipper_id)
        WHERE tr.run_outcome = 'wasted'
        GROUP BY sh.account_manager ORDER BY wasted_cost_eur DESC LIMIT 3
    """).to_string(index=False))

    weekly = q("""
        WITH da AS (
            SELECT s.shipper_id, tr.run_date AS d, SUM(s.packages) AS act
            FROM shipments s JOIN truck_runs tr ON tr.run_id = s.run_id
            WHERE s.status <> 'Cancelled' GROUP BY 1, 2)
        SELECT f.shipper_id,
               date(f.forecast_date, '-' || strftime('%w', f.forecast_date) || ' days') AS week_start,
               SUM(f.forecast_packages) AS fc, SUM(COALESCE(da.act, 0)) AS act
        FROM forecasts f LEFT JOIN da ON da.shipper_id = f.shipper_id AND da.d = f.forecast_date
        GROUP BY 1, 2
    """)
    weekly["att"] = weekly["act"] / weekly["fc"]
    print(f"\nWeekly attainment (Sun-Sat), overall: {weekly['act'].sum() / weekly['fc'].sum():.1%}")
    print(f"Shipper-weeks within +/-10%: {weekly['att'].between(0.9, 1.1).mean():.1%}")
    print("Lowest 5 shippers (average weekly attainment)")
    low = weekly.groupby("shipper_id")["att"].mean().sort_values().head(5)
    for sid, v in low.items():
        print(f"  {sid}  {v:.1%}")
    conn.close()


def main():
    random.seed(SEED)
    np.random.seed(SEED)
    rng = np.random.default_rng(SEED)
    Faker.seed(SEED)

    holidays = generate_holidays()
    nodes = generate_nodes(rng)
    shippers = generate_shippers(rng, nodes)
    truck_runs, pending = generate_truck_runs(shippers, nodes, holidays, rng)
    run_stops = generate_run_stops(pending)
    forecasts = generate_forecasts(pending)
    shipments = generate_shipments(pending, rng)
    exceptions = generate_exceptions(truck_runs, shipments, rng)

    # Drop helper columns (names starting with '_') before saving.
    def public(df):
        return df.drop(columns=[c for c in df.columns if c.startswith("_")])

    tables = {
        "shippers": _to_sql_dates(public(shippers), ["onboarded_date", "delisted_date"], []),
        "nodes": nodes,
        "truck_runs": _to_sql_dates(
            public(truck_runs), ["run_date"],
            ["planned_pickup_time", "actual_pickup_time", "planned_arrival_time", "actual_arrival_time"],
        ),
        "run_stops": _to_sql_dates(run_stops, [], ["planned_pickup_time", "actual_pickup_time"]),
        "shipments": _to_sql_dates(
            public(shipments), ["created_date", "promised_date", "delivered_to_node_date"], []
        ),
        "forecasts": _to_sql_dates(forecasts, ["forecast_date"], []),
        "holidays": _to_sql_dates(holidays, ["holiday_date"], []),
        "exceptions": _to_sql_dates(exceptions, ["exception_date", "resolved_date"], []),
    }
    save_database(tables)
    print("Wrote logistics.db")
    print_checks()


if __name__ == "__main__":
    main()