"""Generate a reproducible SQLite dataset for the European first-mile network."""

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
# Black Friday 2025 through Christmas Eve — peak inbound volume.
PEAK_START = date(2025, 11, 28)
PEAK_END = date(2025, 12, 24)
BOTTLENECK_NODE = "N-UK-01"

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


def monday_of(d):
    """Return the Monday of the week that contains date d."""
    return d - timedelta(days=d.weekday())


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
        # Italy — includes Ferragosto (15 Aug), used in scenario 5
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
            is_bottleneck = node_id == BOTTLENECK_NODE
            if is_bottleneck:
                # Tight cap vs the volume we will send here in peak (scenario 3).
                capacity = 150
            rows.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "country": country,
                    "city": city,
                    "daily_capacity_pallets": capacity,
                    "_is_bottleneck": is_bottleneck,
                }
            )
    return pd.DataFrame(rows)


def generate_shippers(rng, nodes):
    """1000 shippers, 250 per country, with flags used later for planted scenarios."""
    nodes_by_country = {
        c: nodes.loc[nodes["country"] == c, "node_id"].tolist() for c in COUNTRIES
    }
    rows = []
    shipper_num = 0
    for country in COUNTRIES:
        fake_locale = {"UK": "en_GB", "FR": "fr_FR", "IT": "it_IT", "ES": "es_ES"}[country]
        local_fake = Faker(fake_locale)
        local_fake.seed_instance(SEED + COUNTRIES.index(country))
        home_nodes = nodes_by_country[country]
        for i in range(250):
            shipper_num += 1
            # Send a large share of UK shippers to the bottleneck node (scenario 3).
            if country == "UK" and i < 120:
                home_node = BOTTLENECK_NODE
            else:
                home_node = home_nodes[int(rng.integers(0, len(home_nodes)))]
            city = rng.choice(CITIES[country])
            rows.append(
                {
                    "shipper_id": f"S{shipper_num:04d}",
                    "name": f"{local_fake.company()} {shipper_num}",
                    "country": country,
                    "city": str(city),
                    "onboarded_date": None,
                    "status": "active",
                    "delisted_date": None,
                    "_home_node_id": home_node,
                    "_size": None,
                    "_ship_weekdays": None,
                    "_overforecast": False,
                    "_is_recent": False,
                }
            )

    df = pd.DataFrame(rows)

    # Most shippers joined well before 2025; a slice is recent (scenario 7).
    n = len(df)
    recent_idx = rng.choice(df.index, size=32, replace=False)
    remaining = df.index.difference(recent_idx)

    for idx in df.index:
        if idx in recent_idx:
            onboard = START_DATE + timedelta(
                days=int((RECENT_ONBOARD_FROM - START_DATE).days + rng.integers(0, 40))
            )
            onboard = min(onboard, END_DATE - timedelta(days=7))
            df.at[idx, "onboarded_date"] = onboard
            df.at[idx, "_is_recent"] = onboard >= RECENT_ONBOARD_FROM
        else:
            span = (date(2026, 7, 1) - date(2023, 1, 1)).days
            df.at[idx, "onboarded_date"] = date(2023, 1, 1) + timedelta(
                days=int(rng.integers(0, span))
            )

    # Scenario 8: de-listed shippers stop shipping on delisted_date.
    delist_pool = [i for i in remaining if df.at[i, "onboarded_date"] < date(2025, 6, 1)]
    delist_idx = rng.choice(delist_pool, size=48, replace=False)
    for idx in delist_idx:
        onboard = df.at[idx, "onboarded_date"]
        earliest = max(onboard + timedelta(days=90), START_DATE + timedelta(days=30))
        latest = END_DATE - timedelta(days=30)
        gap = max(1, (latest - earliest).days)
        df.at[idx, "status"] = "de-listed"
        df.at[idx, "delisted_date"] = earliest + timedelta(days=int(rng.integers(0, gap)))

    # Scenario 4: a few established shippers always over-forecast.
    over_pool = [
        i
        for i in remaining
        if i not in delist_idx and df.at[i, "onboarded_date"] < date(2025, 1, 1)
    ]
    over_idx = rng.choice(over_pool, size=12, replace=False)
    df.loc[over_idx, "_overforecast"] = True

    # Size drives how many shipments a visit creates; weekdays drive visit frequency.
    # ~1.6 ship-days/week * 1000 shippers keeps total volume near 300k.
    sizes = rng.choice(["S", "M", "L"], size=n, p=[0.50, 0.35, 0.15])
    df["_size"] = sizes
    weekdays = []
    for _ in range(n):
        # ~1.7 ship-days/week keeps total volume near 300k with the shipment mix below.
        n_days = 1 if rng.random() < 0.42 else 2
        days = sorted(rng.choice(5, size=n_days, replace=False).tolist())
        weekdays.append(frozenset(days))
    df["_ship_weekdays"] = weekdays
    return df


def generate_truck_runs(shippers, nodes, holidays, rng):
    """Build daily direct and milkrun trucks, plus the stops/shipments they will carry.

    Returns the truck_runs table and a pending dict used by later tables so
    shipment -> run -> node and run_stops stay aligned.
    """
    holiday_set = set()
    for r in holidays.itertuples(index=False):
        hd = r.holiday_date
        if isinstance(hd, datetime):
            hd = hd.date()
        holiday_set.add((r.country, hd))

    # Scenario 6: winter weather closures, mostly UK working days.
    winter_days = pd.bdate_range("2025-12-01", "2026-02-27").date
    uk_weather = set(rng.choice(winter_days, size=16, replace=False))
    # A couple of non-UK days so the "mostly UK" pattern is still obvious.
    fr_weather = set(rng.choice(winter_days, size=2, replace=False))

    node_capacity = dict(zip(nodes["node_id"], nodes["daily_capacity_pallets"]))

    by_country = defaultdict(list)
    for rec in shippers.to_dict("records"):
        by_country[rec["country"]].append(rec)

    business_days = list(pd.bdate_range(START_DATE, END_DATE).date)
    deferred = defaultdict(list)  # holiday volume moved to the next working day
    pallet_load_by_node_day = defaultdict(int)

    runs, stops, shipments = [], [], []
    counters = {"run": 0, "ship": 0}

    def next_id(kind, width, prefix):
        counters[kind] += 1
        return f"{prefix}{counters[kind]:0{width}d}"

    def make_run(day, country, run_type, stop_shippers, weather_close):
        """One truck, 1 stop (direct) or 2-4 stops (milkrun), then 1+ shipments per stop."""
        first = stop_shippers[0]
        node_id = first["_home_node_id"]
        peak = PEAK_START <= day <= PEAK_END
        volume_mult = 1.0
        if peak:
            volume_mult = 2.1
            if node_id == BOTTLENECK_NODE:
                volume_mult = 3.2  # extra pressure on the tight node

        pickup_hour = int(rng.integers(5, 10))
        pickup_min = int(rng.choice([0, 15, 30, 45]))
        planned_pickup = datetime.combine(day, time(pickup_hour, pickup_min))

        # Milkruns take longer and miss planned arrival more often (scenario 2).
        if run_type == "direct":
            pickup_delay = int(rng.choice([0, 5, 10, 20, 40, 75], p=[0.35, 0.25, 0.18, 0.12, 0.07, 0.03]))
            drive_min = int(rng.integers(150, 361))
            # Direct trucks usually arrive on or before plan (~12% late).
            arrival_extra = int(rng.choice([-20, -5, 0, 15, 45, 90], p=[0.22, 0.38, 0.28, 0.07, 0.03, 0.02]))
        else:
            pickup_delay = int(rng.choice([5, 15, 30, 45, 70, 100], p=[0.12, 0.18, 0.22, 0.22, 0.16, 0.10]))
            drive_min = int(rng.integers(240, 541))
            # Milkruns are late to the node much more often (scenario 2).
            arrival_extra = int(rng.choice([0, 20, 40, 70, 110, 160], p=[0.18, 0.18, 0.22, 0.22, 0.12, 0.08]))

        if weather_close:
            pickup_delay += 80
            arrival_extra += 100

        actual_pickup = planned_pickup + timedelta(minutes=pickup_delay)
        planned_arrival = planned_pickup + timedelta(minutes=drive_min)
        actual_arrival = planned_arrival + timedelta(minutes=max(arrival_extra, -20))

        # Rare truck no-shows cancel the run (no actual times).
        is_no_show = (not weather_close) and rng.random() < 0.007
        if is_no_show or weather_close:
            actual_pickup = None
            actual_arrival = None
            actual_arrival_date = None
        else:
            actual_arrival_date = actual_arrival.date()

        run_id = next_id("run", 6, "R")
        total_packages = 0
        total_pallets = 0
        has_overforecast = False
        is_partial = rng.random() < 0.018

        for seq, shipper in enumerate(stop_shippers, start=1):
            if shipper["_overforecast"]:
                has_overforecast = True
            size = shipper["_size"]
            if size == "S":
                n_shp = int(rng.integers(1, 4))
            elif size == "M":
                n_shp = int(rng.integers(2, 5))
            else:
                n_shp = int(rng.integers(4, 7))

            picked = 0
            for _ in range(n_shp):
                packages = max(4, int(rng.integers(10, 55) * volume_mult))
                spp = float(rng.uniform(18, 40))
                pallets = max(1, int(round(packages / spp)))
                if is_partial and seq == 1 and picked == 0:
                    # Scenario-friendly partial pickup: fewer pallets at first stop.
                    pallets = max(1, pallets // 2)
                    packages = max(4, packages // 2)
                service = "1DD" if rng.random() < 0.45 else "NDD"
                created = day if rng.random() < 0.8 else day - timedelta(days=1)
                if created < shipper["onboarded_date"]:
                    created = day

                # Scenario 3: once the bottleneck node is full, roll remaining freight.
                overflow_days = 0
                if (
                    node_id == BOTTLENECK_NODE
                    and peak
                    and not is_no_show
                    and not weather_close
                ):
                    already = pallet_load_by_node_day[(node_id, day)]
                    if already + pallets > node_capacity[node_id]:
                        overflow_days = 1 if rng.random() < 0.7 else 2

                if not is_no_show and not weather_close:
                    pallet_load_by_node_day[(node_id, day)] += pallets

                shipments.append(
                    {
                        "shipment_id": next_id("ship", 7, "SH"),
                        "shipper_id": shipper["shipper_id"],
                        "run_id": run_id,
                        "node_id": node_id,
                        "service_level": service,
                        "created_date": created,
                        "packages": packages,
                        "pallets": pallets,
                        "run_type": run_type,
                        "country": country,
                        "is_recent": bool(shipper["_is_recent"]),
                        "is_no_show": is_no_show,
                        "is_weather": weather_close,
                        "overflow_days": overflow_days,
                        "actual_arrival_date": actual_arrival_date,
                    }
                )
                picked += pallets
                total_packages += packages
                total_pallets += pallets

            stops.append(
                {
                    "run_id": run_id,
                    "shipper_id": shipper["shipper_id"],
                    "stop_sequence": seq,
                    "pallets_picked": picked,
                }
            )

        # Size the trailer to the load. Over-forecasters still book extra space
        # (scenario 4: low utilisation next to inflated forecasts).
        if has_overforecast:
            util = float(rng.uniform(0.40, 0.55))
        else:
            util = float(rng.uniform(0.75, 0.95))
        pallet_capacity = max(total_pallets, int(round(total_pallets / util)))

        # Milkruns spread cost over more packages so cost per package is lower.
        if run_type == "milkrun":
            cost = round(float(rng.uniform(2.0, 3.5)) * total_packages, 2)
        else:
            cost = round(float(rng.uniform(4.6, 7.6)) * total_packages, 2)

        runs.append(
            {
                "run_id": run_id,
                "run_date": day,
                "run_type": run_type,
                "carrier": str(rng.choice(CARRIERS)),
                "node_id": node_id,
                "planned_pickup_time": planned_pickup,
                "actual_pickup_time": actual_pickup,
                "planned_arrival_time": planned_arrival,
                "actual_arrival_time": actual_arrival,
                "pallet_capacity": pallet_capacity,
                "pallets_loaded": total_pallets,
                "cost_eur": cost,
                "_is_no_show": is_no_show,
                "_is_weather": weather_close,
                "_is_partial": is_partial,
            }
        )

    for day in business_days:
        for country in COUNTRIES:
            is_holiday = (country, day) in holiday_set
            weather_today = (country == "UK" and day in uk_weather) or (
                country == "FR" and day in fr_weather
            )

            todays = []
            for s in by_country[country]:
                if day < s["onboarded_date"]:
                    continue
                # Scenario 8: no volume after de-list.
                if s["delisted_date"] is not None and day >= s["delisted_date"]:
                    continue
                if day.weekday() in s["_ship_weekdays"]:
                    todays.append(s)

            # Scenario 5: bank holidays shift pickups to the next working day.
            if is_holiday:
                deferred[country].extend(todays)
                continue

            if deferred[country]:
                # Drop deferred visits that crossed a de-list date (scenario 8).
                todays.extend(
                    [
                        s
                        for s in deferred[country]
                        if s["delisted_date"] is None or day < s["delisted_date"]
                    ]
                )
                deferred[country] = []

            if not todays:
                continue

            # Deduplicate shippers if a holiday shift stacked them with a normal ship day.
            seen = set()
            unique = []
            for s in todays:
                if s["shipper_id"] not in seen:
                    seen.add(s["shipper_id"])
                    unique.append(s)
            todays = unique
            rng.shuffle(todays)

            # About a third of visits ride a milkrun with nearby (same-city) shippers.
            n_milk = int(len(todays) * 0.35)
            milk_candidates = todays[:n_milk]
            direct_shippers = todays[n_milk:]
            by_city = defaultdict(list)
            for s in milk_candidates:
                by_city[s["city"]].append(s)

            for city, group in by_city.items():
                leftover = []
                i = 0
                while i < len(group):
                    remaining = len(group) - i
                    if remaining < 2:
                        leftover.extend(group[i:])
                        break
                    n_stops = int(rng.integers(2, 5))
                    n_stops = min(n_stops, remaining)
                    # Avoid leaving a single stranded shipper in this city group.
                    if remaining - n_stops == 1:
                        n_stops = remaining
                        if n_stops > 4:
                            n_stops = remaining - 2
                    chunk = group[i : i + n_stops]
                    i += n_stops
                    if len(chunk) == 1:
                        leftover.append(chunk[0])
                        continue
                    close = weather_today and rng.random() < 0.70
                    make_run(day, country, "milkrun", chunk, close)

                direct_shippers.extend(leftover)

            for s in direct_shippers:
                close = weather_today and rng.random() < 0.70
                make_run(day, country, "direct", [s], close)

    truck_runs = pd.DataFrame(runs)
    pending = {"stops": stops, "shipments": shipments, "runs": runs}
    return truck_runs, pending


def generate_run_stops(pending):
    """One row per shipper visited on each run (1 for direct, 2-4 for milkrun)."""
    return pd.DataFrame(pending["stops"])


def generate_shipments(pending, rng):
    """Apply status, promise, delivery, and hold rules on top of planned shipments."""
    df = pd.DataFrame(pending["shipments"])
    n = len(df)

    created = pd.to_datetime(df["created_date"])
    ndd_offset = rng.integers(2, 4, size=n)  # NDD = created + 2 or 3 days
    promised = created + pd.to_timedelta(
        np.where(df["service_level"].to_numpy() == "1DD", 1, ndd_offset), unit="D"
    )

    arrival = pd.to_datetime(df["actual_arrival_date"])
    delivered = arrival + pd.to_timedelta(df["overflow_days"].to_numpy().astype(int), unit="D")

    status = np.full(n, "Delivered to Node", dtype=object)
    hold_reason = np.full(n, None, dtype=object)

    # Weather closures and no-shows cancel freight still on that truck.
    cancelled = (
        df["is_no_show"].to_numpy()
        | df["is_weather"].to_numpy()
        | (rng.random(n) < 0.006)
    )
    status[cancelled] = "Cancelled"

    # Scenario 1: ~8% of UK shipments sit at customs. Other countries stay at ~0.
    uk = (df["country"].to_numpy() == "UK") & (status != "Cancelled")
    customs = uk & (rng.random(n) < 0.086)
    status[customs] = "On Hold"
    hold_reason[customs] = "At Customs"

    # Scenario 7: recently onboarded shippers have more Shipper Compliance holds.
    open_mask = status == "Delivered to Node"
    recent = df["is_recent"].to_numpy() & open_mask
    old = (~df["is_recent"].to_numpy()) & open_mask
    rec_hold = recent & (rng.random(n) < 0.17)
    old_hold = old & (rng.random(n) < 0.010)
    status[rec_hold | old_hold] = "On Hold"
    hold_reason[rec_hold | old_hold] = "Shipper Compliance"

    # Last few days of the dataset still have work in progress.
    near_end = (created >= pd.Timestamp(END_DATE - timedelta(days=4))) & (
        status == "Delivered to Node"
    )
    roll = rng.random(n)
    status[near_end & (roll < 0.25)] = "Created"
    status[near_end & (roll >= 0.25) & (roll < 0.50)] = "Picked Up"
    status[near_end & (roll >= 0.50) & (roll < 0.78)] = "In Transit"

    # Same-day node arrival still meets 1DD, so force a slice of milkruns
    # (and peak overflow) past promised_date — otherwise on-time looks identical.
    delivered = pd.to_datetime(delivered)
    promised_dt = pd.to_datetime(promised)
    late_date = promised_dt + pd.Timedelta(days=1)
    still_delivered = status == "Delivered to Node"
    force_late = still_delivered & (
        ((df["run_type"].to_numpy() == "milkrun") & (rng.random(n) < 0.22))
        | ((df["run_type"].to_numpy() == "direct") & (rng.random(n) < 0.055))
        | (df["overflow_days"].to_numpy() > 0)
    )
    delivered = delivered.mask(force_late, np.maximum(delivered, late_date))

    delivered_date = np.where(
        status == "Delivered to Node",
        delivered.dt.strftime("%Y-%m-%d").to_numpy(),
        None,
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
    # Keep overflow flags so exceptions can mark peak-season capacity rejections.
    out["_overflow_days"] = df["overflow_days"].to_numpy()
    out["_is_weather"] = df["is_weather"].to_numpy()
    return out


def generate_forecasts(shipments, shippers, rng):
    """Weekly package forecasts. Most shippers land 90-110% attainment; a few ~70%."""
    work = shipments.loc[shipments["status"] != "Cancelled", ["shipper_id", "created_date", "packages"]].copy()
    work["created_date"] = pd.to_datetime(work["created_date"])
    work["week_start_date"] = work["created_date"] - pd.to_timedelta(
        work["created_date"].dt.weekday, unit="D"
    )
    actuals = (
        work.groupby(["shipper_id", "week_start_date"], as_index=False)["packages"]
        .sum()
        .rename(columns={"packages": "actual_packages"})
    )

    over_ids = set(shippers.loc[shippers["_overforecast"], "shipper_id"])
    factors = np.empty(len(actuals))
    is_over = actuals["shipper_id"].isin(over_ids).to_numpy()
    # Scenario 4: chronic over-forecast (actual / forecast ≈ 70%).
    factors[is_over] = rng.uniform(0.66, 0.74, size=is_over.sum())
    factors[~is_over] = rng.uniform(0.90, 1.10, size=(~is_over).sum())
    forecast = np.maximum(1, np.round(actuals["actual_packages"].to_numpy() / factors)).astype(int)

    return pd.DataFrame(
        {
            "shipper_id": actuals["shipper_id"],
            "week_start_date": actuals["week_start_date"].dt.date,
            "forecast_packages": forecast,
        }
    )


def generate_exceptions(truck_runs, shipments, rng):
    """One exception row per planted operational failure, tied to a run and/or shipment."""
    rows = []
    eid = 0

    def add(run_id, shipment_id, etype, on_date, resolved):
        nonlocal eid
        eid += 1
        rows.append(
            {
                "exception_id": f"E{eid:06d}",
                "run_id": run_id,
                "shipment_id": shipment_id,
                "exception_type": etype,
                "exception_date": on_date,
                "resolved_date": resolved,
            }
        )

    runs = truck_runs.copy()
    runs["run_date"] = pd.to_datetime(runs["run_date"]).dt.date
    planned_arr = pd.to_datetime(runs["planned_arrival_time"])
    actual_arr = pd.to_datetime(runs["actual_arrival_time"])
    late_mask = actual_arr.notna() & (actual_arr > planned_arr)
    for r in runs.loc[late_mask].itertuples(index=False):
        add(r.run_id, None, "Late arrival at node", r.run_date, r.run_date)

    no_show = runs["_is_no_show"].astype(bool)
    for r in runs.loc[no_show].itertuples(index=False):
        add(r.run_id, None, "Truck no-show", r.run_date, r.run_date)

    weather = runs["_is_weather"].astype(bool)
    for r in runs.loc[weather].itertuples(index=False):
        resolved = r.run_date + timedelta(days=1)
        add(r.run_id, None, "Weather site closure", r.run_date, resolved)

    partial = runs["_is_partial"].astype(bool)
    for r in runs.loc[partial].itertuples(index=False):
        add(r.run_id, None, "Partial pickup (shipper not ready)", r.run_date, r.run_date)

    customs = shipments["hold_reason"] == "At Customs"
    for s in shipments.loc[customs].itertuples(index=False):
        add(s.run_id, s.shipment_id, "Customs hold", s.created_date, None)

    # NamedTuples from itertuples drop leading underscores, so use records here.
    overflow = shipments.loc[shipments["_overflow_days"].astype(int) > 0]
    for rec in overflow.to_dict("records"):
        extra = int(rec["_overflow_days"])
        resolved = rec["created_date"] + timedelta(days=extra)
        add(rec["run_id"], rec["shipment_id"], "Node capacity rejection", rec["created_date"], resolved)

    # A thin random layer of damaged freight on delivered shipments.
    delivered = shipments.loc[shipments["status"] == "Delivered to Node"]
    n_dmg = max(1, int(len(delivered) * 0.003))
    dmg_idx = rng.choice(delivered.index, size=n_dmg, replace=False)
    for s in delivered.loc[dmg_idx].itertuples(index=False):
        add(s.run_id, s.shipment_id, "Damaged freight", s.created_date, s.delivered_to_node_date)

    return pd.DataFrame(rows)


def _to_sql_dates(df, date_cols, datetime_cols):
    """Store dates/times as ISO text so SQLite stays easy to query."""
    out = df.copy()
    for col in date_cols:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
        out.loc[out[col] == "NaT", col] = None
    for col in datetime_cols:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        out.loc[out[col] == "NaT", col] = None
    return out


def save_database(tables, path="logistics.db"):
    conn = sqlite3.connect(path)
    for name, df in tables.items():
        df.to_sql(name, conn, if_exists="replace", index=False)
    conn.close()


def print_checks(tables):
    print("\nRow counts")
    for name, df in tables.items():
        print(f"  {name:12s} {len(df):,}")

    shipments = tables["shipments"].copy()
    runs = tables["truck_runs"][["run_id", "run_type"]].copy()
    shippers = tables["shippers"][["shipper_id", "country"]].copy()
    merged = shipments.merge(runs, on="run_id", how="left")

    # On-time: delivered on or before promised_date; cancelled rows are excluded.
    active = merged[merged["status"] != "Cancelled"].copy()
    delivered_flag = active["delivered_to_node_date"].notna()
    on_time = delivered_flag & (active["delivered_to_node_date"] <= active["promised_date"].astype(str))
    active["_on_time"] = on_time
    print("\nOn-time rate by run_type (cancelled excluded)")
    for run_type, grp in active.groupby("run_type"):
        rate = grp["_on_time"].mean()
        print(f"  {run_type:8s} {rate:.1%}  (n={len(grp):,})")

    uk = merged.merge(shippers, on="shipper_id", how="left")
    uk = uk[uk["country"] == "UK"]
    customs_pct = (uk["hold_reason"] == "At Customs").mean()
    print(f"\n% UK shipments with customs hold: {customs_pct:.1%}")

    # Attainment = received packages / forecast, by shipper-week, then averaged.
    fc = tables["forecasts"].copy()
    work = shipments.loc[shipments["status"] != "Cancelled", ["shipper_id", "created_date", "packages"]].copy()
    work["week_start_date"] = pd.to_datetime(work["created_date"]) - pd.to_timedelta(
        pd.to_datetime(work["created_date"]).dt.weekday, unit="D"
    )
    work["week_start_date"] = work["week_start_date"].dt.strftime("%Y-%m-%d")
    actuals = work.groupby(["shipper_id", "week_start_date"], as_index=False)["packages"].sum()
    fc["week_start_date"] = fc["week_start_date"].astype(str)
    att = actuals.merge(fc, on=["shipper_id", "week_start_date"], how="inner")
    att["attainment"] = att["packages"] / att["forecast_packages"]
    by_shipper = att.groupby("shipper_id")["attainment"].mean().sort_values()
    print("\nAverage attainment by shipper (lowest 5)")
    for shipper_id, val in by_shipper.head(5).items():
        print(f"  {shipper_id}  {val:.1%}")


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
    shipments = generate_shipments(pending, rng)
    forecasts = generate_forecasts(shipments, shippers, rng)
    exceptions = generate_exceptions(truck_runs, shipments, rng)

    # Drop helper columns that are not part of the published schema.
    shippers_out = shippers[
        ["shipper_id", "name", "country", "city", "onboarded_date", "status", "delisted_date"]
    ].copy()
    nodes_out = nodes[
        ["node_id", "node_type", "country", "city", "daily_capacity_pallets"]
    ].copy()
    truck_runs_out = truck_runs.drop(
        columns=[c for c in truck_runs.columns if c.startswith("_")]
    )
    shipments_out = shipments.drop(
        columns=[c for c in shipments.columns if c.startswith("_")]
    )

    shippers_out = _to_sql_dates(shippers_out, ["onboarded_date", "delisted_date"], [])
    holidays_out = _to_sql_dates(holidays, ["holiday_date"], [])
    truck_runs_out = _to_sql_dates(
        truck_runs_out,
        ["run_date"],
        [
            "planned_pickup_time",
            "actual_pickup_time",
            "planned_arrival_time",
            "actual_arrival_time",
        ],
    )
    shipments_out = _to_sql_dates(
        shipments_out,
        ["created_date", "promised_date", "delivered_to_node_date"],
        [],
    )
    forecasts_out = _to_sql_dates(forecasts, ["week_start_date"], [])
    exceptions_out = _to_sql_dates(exceptions, ["exception_date", "resolved_date"], [])

    tables = {
        "shippers": shippers_out,
        "nodes": nodes_out,
        "truck_runs": truck_runs_out,
        "run_stops": run_stops,
        "shipments": shipments_out,
        "forecasts": forecasts_out,
        "holidays": holidays_out,
        "exceptions": exceptions_out,
    }
    save_database(tables)
    print("Wrote logistics.db")
    print_checks(tables)


if __name__ == "__main__":
    main()
