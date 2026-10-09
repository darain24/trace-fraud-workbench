"""Write a small, seeded, fully synthetic dataset in the benchmark's shape.

Nothing here is derived from benchmark rows. Customers, cards, devices, amounts and
case narratives are drawn from a fixed seed, and the policy README is original text.
The columns and value vocabularies are the ones `scripts/ingest.py` reads, so ingest,
provisioning, fitting and the twenty-case run all work on it unchanged, in minutes
rather than hours (about 1.5% of the benchmark's size).

The closed cases plant the shapes the evidence model is meant to separate: card
testing, takeover from a device the account already knows, multi-day runs in a new
billing region, velocity bursts against a card's own rhythm, home-region activity
alongside an out-of-region run, and the cleared alerts that look like fraud until the
cardholder answers -- a new phone, a trip, one big intended purchase. One device
profile is shared by a small ring across customers. The bank's risk score is drawn
independently of the outcome inside the alert population, as it must be: it decides
which alerts get opened, never which ones are fraud.

    uv run python scripts/generate_demo_data.py            # writes data/raw/
    uv run python scripts/generate_demo_data.py --out DIR  # anywhere else
"""

import argparse
import csv
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tracework.config import DATA, DEMO_MARKER

SEED = 20161001
START = datetime(2016, 7, 1)
END = datetime(2017, 1, 1)
HISTORY_START = datetime(2016, 7, 8)
HISTORY_END = datetime(2016, 11, 5)
N_CUSTOMERS = 150
N_HISTORY = 240
FIRST_TXN_ID = 5_000_001
FILES = [
    "transactions.csv",
    "identity.csv",
    "case_pack.csv",
    "closed_cases_history.csv",
    "README.md",
]

TXN_COLUMNS = (
    ["TransactionID", "TransactionDT", "TransactionAmt", "ProductCD"]
    + [f"card{i}" for i in range(1, 7)]
    + ["addr1", "addr2", "dist1", "dist2", "P_emaildomain", "R_emaildomain"]
    + [f"C{i}" for i in range(1, 15)]
    + [f"D{i}" for i in range(1, 16)]
    + [f"M{i}" for i in range(1, 10)]
    + [f"V{i}" for i in range(1, 340)]
    + ["customer_id", "ts", "channel", "risk_score"]
)
IDENTITY_COLUMNS = (
    ["TransactionID"]
    + [f"id_{i:02d}" for i in range(1, 39)]
    + ["DeviceType", "DeviceInfo"]
)
CASE_COLUMNS = [
    "case_id",
    "opened_at",
    "trigger_type",
    "trigger_text",
    "flagged_txn_id",
    "card_id",
    "customer_id",
    "risk_score",
]
HISTORY_COLUMNS = [
    "case_id",
    "customer_id",
    "card_id",
    "opened_at",
    "closed_at",
    "outcome",
    "pattern",
    "first_fraud_txn_id",
    "txn_ids",
    "n_txns",
    "exposure_usd",
    "connected_card_ids",
    "actions_taken",
    "report_filed",
    "analyst_notes",
]

# (DeviceType, DeviceInfo, id_30 OS, id_31 browser, id_33 screen). Common handsets
# deliberately collide across customers: a shared profile is a lead, not an identity.
DEVICES = [
    ("desktop", "Windows", "Windows 10", "chrome 63.0", "1920x1080"),
    ("desktop", "Windows", "Windows 7", "ie 11.0 for desktop", "1366x768"),
    ("desktop", "Windows", "Windows 10", "firefox 57.0", "1920x1080"),
    ("desktop", "Windows", "Windows 10", "edge 16.0", "1366x768"),
    ("desktop", "Windows", "Windows 8.1", "chrome 62.0", "1600x900"),
    ("desktop", "MacOS", "Mac OS X 10_12_6", "safari generic", "2560x1600"),
    ("desktop", "MacOS", "Mac OS X 10_13_1", "chrome 62.0", "1440x900"),
    ("mobile", "iOS Device", "iOS 11.1.2", "mobile safari 11.0", "2208x1242"),
    ("mobile", "iOS Device", "iOS 11.2.1", "mobile safari 11.0", "1334x750"),
    ("mobile", "iOS Device", "iOS 10.3.3", "mobile safari 10.0", "1334x750"),
    (
        "mobile",
        "SM-G930V Build/NRD90M",
        "Android 7.0",
        "chrome 62.0 for android",
        "1920x1080",
    ),
    (
        "mobile",
        "SM-J700M Build/MMB29K",
        "Android 6.0.1",
        "chrome 61.0 for android",
        "1280x720",
    ),
    (
        "mobile",
        "Moto G (5) Build/NPP25.137",
        "Android 7.0",
        "chrome 63.0 for android",
        "1920x1080",
    ),
    (
        "mobile",
        "Pixel Build/OPR3.170623",
        "Android 8.0.0",
        "chrome 63.0 for android",
        "1920x1080",
    ),
    ("mobile", "iOS Device", "", "mobile safari generic", ""),
    ("desktop", "Windows", "", "chrome 63.0", ""),
]
FRAUD_DEVICES = [
    ("desktop", "Linux", "Linux", "chrome 49.0", "800x600"),
    ("desktop", "Windows", "Windows XP", "firefox 45.0", "1024x768"),
    ("mobile", "rv:52.0", "Android 4.4.2", "chrome 49.0 for android", "480x800"),
    ("desktop", "Windows", "Windows 7", "chrome 55.0", "1280x800"),
]
RING_DEVICE = ("desktop", "Windows", "Windows Vista", "opera 49.0", "1280x1024")
FRAUD_PROXIES = ["IP_PROXY:ANONYMOUS", "IP_PROXY:HIDDEN", "IP_PROXY:TRANSPARENT"]
EMAILS = [
    "gmail.com",
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "anonymous.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
    "comcast.net",
]
NETWORKS = [
    "visa",
    "visa",
    "visa",
    "mastercard",
    "mastercard",
    "american express",
    "discover",
]
ONLINE_PRODUCTS = ["H", "R", "C", "S"]
ONLINE_WEIGHTS = [4, 4, 3, 1]


def poisson(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def fmt(ts):
    return ts.isoformat(sep=" ")


def money(x):
    return f"{x:.2f}"


class World:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.txns = []
        self.history = []
        self.cases = []
        self.busy = {}
        r = self.rng
        self.regions = [f"{x}.0" for x in sorted(r.sample(range(110, 540), 40))]
        self.customers = [self.customer(i) for i in range(N_CUSTOMERS)]
        for c in self.customers:
            self.background(c, START, END)

    # --- population ----------------------------------------------------------
    def customer(self, i, rate=None):
        r = self.rng
        cid = f"C{10101 + i:05d}"
        homes = r.sample(self.regions[:24], 1 if r.random() < 0.65 else 2)
        cards = []
        for k in range(1 if r.random() < 0.7 else 2):
            cards.append(
                {
                    "id": f"{cid}-K{k + 1}",
                    "customer": cid,
                    "card1": str(r.randint(1000, 18390)),
                    "card2": f"{r.randint(100, 600)}.0",
                    "card3": "150.0" if r.random() < 0.9 else "185.0",
                    "card4": r.choice(NETWORKS),
                    "card5": f"{r.choice([102, 117, 166, 224, 226, 229])}.0",
                    "card6": "debit" if r.random() < 0.7 else "credit",
                }
            )
        devices = r.sample(DEVICES, 1 if r.random() < 0.6 else 2)
        return {
            "id": cid,
            "homes": homes,
            "cards": cards,
            "devices": devices,
            "rate": rate
            if rate is not None
            else min(0.8, max(0.08, r.lognormvariate(-1.3, 0.55))),
            "median": round(min(260.0, max(18.0, r.lognormvariate(4.0, 0.55))), 2),
            "online": r.uniform(0.25, 0.7),
            "email": r.choice(EMAILS),
            "addr2": "87.0" if r.random() < 0.95 else r.choice(["60.0", "96.0"]),
        }

    def background(self, c, start, end):
        r = self.rng
        day = start
        while day < end:
            for _ in range(poisson(r, c["rate"])):
                ts = day + timedelta(seconds=r.randint(7 * 3600, 23 * 3600 + 1800))
                card = c["cards"][0] if r.random() < 0.75 else r.choice(c["cards"])
                amount = round(max(1.0, c["median"] * r.lognormvariate(0, 0.6)), 2)
                if r.random() < c["online"]:
                    device = None
                    if r.random() < 0.85:
                        device = (
                            c["devices"][0]
                            if r.random() < 0.75
                            else r.choice(c["devices"])
                        )
                    self.add(
                        c, card, ts, amount, "online", device=device, planted=False
                    )
                else:
                    self.add(c, card, ts, amount, "in_person", planted=False)
            day += timedelta(days=1)

    def add(
        self,
        c,
        card,
        ts,
        amount,
        channel,
        *,
        region=None,
        device=None,
        id_15=None,
        proxy="",
        m=None,
        risk=None,
        product=None,
        planted=True,
    ):
        r = self.rng
        if channel == "in_person":
            product = "W"
            region = r.choice(c["homes"]) if region is None else region
            device = None
            m = m or self.flags(0)
        else:
            product = product or r.choices(ONLINE_PRODUCTS, ONLINE_WEIGHTS)[0]
            # addr1 is the billing region, so an online purchase carries the
            # cardholder's own region wherever the purchase was made.
            if region is None:
                region = r.choice(c["homes"]) if r.random() < 0.92 else ""
            if m is None:
                m = {f"M{i}": "" for i in range(1, 10)}
                if r.random() < 0.4:
                    m["M6"] = "F" if r.random() < 0.3 else "T"
        if risk is None:
            risk = min(0.79, max(0.01, r.betavariate(1.5, 9)))
        t = {
            "seq": len(self.txns),
            "customer": c,
            "card": card,
            "ts": ts.replace(microsecond=0),
            "amount": amount,
            "channel": channel,
            "product": product,
            "region": region,
            "device": device,
            "id_15": id_15,
            "proxy": proxy,
            "m": m,
            "risk": round(risk, 2),
            "planted": planted,
            "dead": False,
        }
        self.txns.append(t)
        return t

    def flags(self, n_false):
        """The nine encoded match fields. They are unnamed Vesta features; this only
        controls how many read F, never what any of them means."""
        r = self.rng
        m = {
            "M1": "T",
            "M2": "F" if r.random() < 0.05 else "T",
            "M3": "F" if r.random() < 0.08 else "T",
            "M4": r.choice(["M0", "M0", "M1", "M2"]),
            "M5": r.choice(["", "", "F", "T"]) if r.random() < 0.6 else "",
            "M6": "F" if r.random() < 0.2 else "T",
            "M7": "" if r.random() < 0.6 else "F" if r.random() < 0.1 else "T",
            "M8": "" if r.random() < 0.6 else "T",
            "M9": "" if r.random() < 0.6 else "T",
        }
        if n_false:
            for k in r.sample(["M2", "M3", "M5", "M6", "M7"], n_false):
                m[k] = "F"
        return m

    def quiet(self, c, start, end, card=None, channel=None):
        """Drop background activity in a window, so a planted shape stays the shape."""
        for t in self.txns:
            if (
                not t["planted"]
                and t["customer"] is c
                and start <= t["ts"] <= end
                and (card is None or t["card"] is card)
                and (channel is None or t["channel"] == channel)
            ):
                t["dead"] = True

    def reserve(self, c, start, end):
        spans = self.busy.setdefault(c["id"], [])
        if any(s < end and start < e for s, e in spans):
            return False
        spans.append((start, end))
        return True

    def away(self, c):
        options = [x for x in self.regions if x not in c["homes"]]
        return self.rng.choice(options)

    def amount(self, c, lo, hi):
        return round(c["median"] * self.rng.uniform(lo, hi), 2)

    # --- episodes ------------------------------------------------------------
    # Each returns the transactions in time order plus the closed-case fields.
    def card_testing(self, c, card, t0, id_15=None):
        r = self.rng
        device, proxy = r.choice(FRAUD_DEVICES), r.choice(FRAUD_PROXIES)
        id_15 = id_15 or r.choice(["New", "Unknown"])
        times = sorted(
            t0 + timedelta(minutes=r.uniform(0, 35)) for _ in range(r.randint(3, 5))
        )
        txns = [
            self.add(
                c,
                card,
                ts,
                round(r.uniform(0.5, 4.99), 2),
                "online",
                device=device,
                id_15=id_15,
                proxy=proxy,
                product="C",
            )
            for ts in times
        ]
        big = round(r.uniform(150, 900), 2)
        txns.append(
            self.add(
                c,
                card,
                times[-1] + timedelta(minutes=r.uniform(4, 15)),
                big,
                "online",
                device=device,
                id_15=id_15,
                proxy=proxy,
                product=r.choice(["C", "H"]),
            )
        )
        note = r.choice(
            [
                f"{len(times)} online authorisations under $5 inside an hour, then a ${big:,.2f} "
                "purchase on the same card. Cardholder denied all of them; card blocked and reissued.",
                f"Card testing: {len(times)} micro-authorisations followed by a ${big:,.2f} online "
                "purchase within the hour. Cardholder did not recognise any of it.",
            ]
        )
        return txns, "confirmed_fraud", "card_testing", note

    def takeover(self, c, card, t0, in_person_last=False):
        r = self.rng
        device = c["devices"][0]
        proxy = "" if r.random() < 0.7 else "IP_PROXY:TRANSPARENT"
        n_false = r.choice([2, 2, 3])
        txns = []
        for _ in range(r.randint(2, 4)):
            ts = t0 + timedelta(hours=r.uniform(0, 30))
            txns.append(
                self.add(
                    c,
                    card,
                    ts,
                    self.amount(c, 1.5, 5),
                    "online",
                    device=device,
                    id_15="Found",
                    proxy=proxy,
                    m=self.flags(n_false),
                )
            )
        for _ in range(r.randint(1, 2)):
            ts = t0 + timedelta(hours=r.uniform(2, 30))
            txns.append(
                self.add(
                    c,
                    card,
                    ts,
                    self.amount(c, 1.5, 4),
                    "in_person",
                    m=self.flags(n_false),
                )
            )
        txns.sort(key=lambda t: t["ts"])
        if in_person_last:
            txns.append(
                self.add(
                    c,
                    card,
                    txns[-1]["ts"] + timedelta(hours=r.uniform(1, 4)),
                    self.amount(c, 2, 4),
                    "in_person",
                    m=self.flags(3),
                )
            )
        exposure = sum(t["amount"] for t in txns)
        note = r.choice(
            [
                "Online purchases from the device profile already on the account, alongside "
                "card-present use the same day; several encoded match fields disagreed. Cardholder "
                f"confirmed the account had been accessed without them. ${exposure:,.2f} across "
                f"{len(txns)} transactions.",
                f"Account takeover. {len(txns)} transactions in about a day, online and in person, "
                "from the customer's own known device. Credentials reset, card blocked.",
            ]
        )
        return txns, "confirmed_fraud", "account_takeover", note

    def cnp(self, c, card, t0, n=None, hours=None, device=None):
        r = self.rng
        n = n or r.randint(2, 5)
        hours = hours or r.uniform(2, 20)
        roll = r.random()
        if device is None:
            device, id_15 = (
                (c["devices"][0], "Found")
                if roll < 0.6
                else (None, None)
                if roll < 0.85
                else (c["devices"][0], "Unknown")
            )
        else:
            id_15 = "Found"
        product = r.choice(["C", "H", "R"])
        txns = [
            self.add(
                c,
                card,
                t0
                + timedelta(hours=hours * i / max(1, n - 1))
                + timedelta(minutes=r.uniform(-10, 10))
                if i
                else t0,
                self.amount(c, 1, 4),
                "online",
                device=device,
                id_15=id_15,
                product=product,
            )
            for i in range(n)
        ]
        txns.sort(key=lambda t: t["ts"])
        note = r.choice(
            [
                f"{n} online purchases over {hours:.0f} hours that the cardholder did not "
                "recognise. No change of device on the account. Card blocked.",
                f"Card-not-present fraud: {n} online charges, ${sum(t['amount'] for t in txns):,.2f} "
                "in total. Card details likely compromised; cardholder still had the card.",
            ]
        )
        return txns, "confirmed_fraud", "card_not_present_fraud", note

    def cnp_new_device(self, c, card, t0, device=None, proxy=None):
        r = self.rng
        device = device or r.choice(FRAUD_DEVICES)
        proxy = (
            r.choice(FRAUD_PROXIES)
            if proxy is None and r.random() < 0.6
            else proxy or ""
        )
        id_15 = "New" if r.random() < 0.5 else "Unknown"
        txns = sorted(
            (
                self.add(
                    c,
                    card,
                    t0 + timedelta(hours=r.uniform(0, 10)) if i else t0,
                    self.amount(c, 1.2, 4),
                    "online",
                    device=device,
                    id_15=id_15,
                    proxy=proxy,
                )
                for i in range(r.randint(1, 4))
            ),
            key=lambda t: t["ts"],
        )
        note = r.choice(
            [
                "Online purchases from a device profile never seen on the account"
                + (" behind a proxy" if proxy else "")
                + ". Cardholder denied making them; card blocked.",
                f"{len(txns)} online transaction(s) from an unfamiliar device. The cardholder was "
                "not using a new device and did not recognise the charges.",
            ]
        )
        return txns, "confirmed_fraud", "card_not_present_new_device", note

    def out_of_region(self, c, card, t0, days=None, concurrent=False):
        r = self.rng
        region = self.away(c)
        days = days or r.randint(2, 4)
        txns = []
        for d in range(days):
            for _ in range(r.randint(1, 3)):
                ts = t0 + timedelta(days=d, hours=r.uniform(0, 10))
                txns.append(
                    self.add(
                        c, card, ts, self.amount(c, 1, 3), "in_person", region=region
                    )
                )
        txns.sort(key=lambda t: t["ts"])
        if concurrent:
            self.home_activity(c, txns[-1]["ts"])
        note = r.choice(
            [
                f"Card-present use across {days} days in billing region {region}, outside every "
                "region on the customer's history"
                + (", while the customer kept shopping at home" if concurrent else "")
                + ". Cardholder still had the card; counterfeit suspected.",
                f"Out-of-region run: {len(txns)} card-present purchases in region {region} over "
                f"{days} days. Cardholder had not travelled. Card blocked and reissued.",
            ]
        )
        return txns, "confirmed_fraud", "out_of_region_use", note

    def home_activity(self, c, until):
        r = self.rng
        for _ in range(r.randint(5, 7)):
            ts = until - timedelta(hours=r.uniform(1, 40))
            self.add(
                c,
                r.choice(c["cards"]),
                ts,
                self.amount(c, 0.5, 1.5),
                "in_person",
                region=r.choice(c["homes"]),
                planted=True,
            )

    def new_phone(self, c, card, t0, scale=(0.6, 2)):
        r = self.rng
        phone = r.choice(
            [d for d in DEVICES if d[0] == "mobile" and d not in c["devices"]]
        )
        t = self.add(
            c, card, t0, self.amount(c, *scale), "online", device=phone, id_15="New"
        )
        for x in self.txns:
            if (
                x["customer"] is c
                and not x["planted"]
                and x["device"]
                and x["ts"] > t0
                and r.random() < 0.6
            ):
                x["device"] = phone
        c["devices"].append(phone)
        note = r.choice(
            [
                "Cardholder confirmed the purchase; it was made from a new phone set up that week. "
                "Closed, no fraud.",
                "New device on the account. Customer verified the transaction when contacted; "
                "they had replaced their handset.",
            ]
        )
        return [t], "cleared", "none", note

    def trip(self, c, card, t0, days=None, concurrent=False):
        r = self.rng
        region = self.away(c)
        days = days or (1 if r.random() < 0.7 else r.randint(2, 3))
        if not concurrent:
            self.quiet(
                c,
                t0 - timedelta(hours=6),
                t0 + timedelta(days=days),
                channel="in_person",
            )
        txns = sorted(
            (
                self.add(
                    c,
                    card,
                    t0 + timedelta(days=d, hours=r.uniform(0, 9)) if d or i else t0,
                    self.amount(c, 0.7, 2),
                    "in_person",
                    region=region,
                )
                for d in range(days)
                for i in range(r.randint(1, 3))
            ),
            key=lambda t: t["ts"],
        )
        if concurrent:
            self.home_activity(c, txns[-1]["ts"])
        note = r.choice(
            [
                f"Card-present purchases in region {region} while the cardholder was travelling. "
                "Confirmed by the cardholder. Closed, no fraud.",
                f"Customer was away for {days} day(s) and confirmed the spending in region "
                f"{region}. No fraud.",
            ]
        )
        return txns, "cleared", "none", note

    def big_purchase(self, c, card, t0, channel=None):
        r = self.rng
        channel = channel or ("in_person" if r.random() < 0.6 else "online")
        self.quiet(c, t0 - timedelta(hours=48), t0 + timedelta(hours=24), card=card)
        amount = self.amount(c, 3.5, 8)
        device = c["devices"][0] if channel == "online" and r.random() < 0.4 else None
        t = self.add(c, card, t0, amount, channel, device=device)
        note = r.choice(
            [
                f"Single purchase of ${amount:,.2f}, several times the customer's usual spend. "
                "Cardholder confirmed it was intended. Closed, no fraud.",
                "One large purchase with no change in card activity around it. Customer confirmed "
                "it; closed without action.",
            ]
        )
        return [t], "cleared", "none", note

    def plain(self, c, card, t0, channel=None):
        r = self.rng
        channel = channel or ("online" if r.random() < c["online"] else "in_person")
        device = c["devices"][0] if channel == "online" and r.random() < 0.4 else None
        t = self.add(c, card, t0, self.amount(c, 0.6, 1.8), channel, device=device)
        note = r.choice(
            [
                "Cardholder recognised the transaction when contacted. Closed, no fraud.",
                "Routine purchase flagged by the model. Customer confirmed it; no further action.",
            ]
        )
        return [t], "cleared", "none", note

    # --- closed cases --------------------------------------------------------
    def close(self, c, card, txns, outcome, pattern, note, connected=(), alert=None):
        r = self.rng
        txns = sorted(txns, key=lambda t: (t["ts"], t["seq"]))
        # The alert lands on the first transaction of the episode. Inside the alert
        # population the score is drawn independently of the outcome.
        if alert is None:
            alert = outcome == "cleared" or r.random() < 0.7
        txns[0]["risk"] = round(r.uniform(0.82, 0.97), 2) if alert else txns[0]["risk"]
        opened = txns[-1]["ts"] + timedelta(minutes=r.randint(10, 360))
        closed = opened + timedelta(hours=r.randint(12, 140))
        fraud = outcome == "confirmed_fraud"
        exposure = round(sum(t["amount"] for t in txns), 2) if fraud else 0.0
        report = fraud and (exposure > 1000 or bool(connected))
        actions = (
            ["CREATE_CASE", "BLOCK_CARD"] + (["FILE_REPORT"] if report else [])
            if fraud
            else ["VERIFY_WITH_CUSTOMER", "CLOSE_NO_FRAUD"]
        )
        self.history.append(
            {
                "customer": c,
                "card": card,
                "opened": opened.replace(microsecond=0),
                "closed": closed.replace(microsecond=0),
                "outcome": outcome,
                "pattern": pattern,
                "txns": txns,
                "exposure": exposure,
                "connected": list(connected),
                "actions": actions,
                "report": report,
                "note": note,
            }
        )

    def plant_history(self, reserved):
        r = self.rng
        mix = [
            (self.cnp, 16),
            (self.cnp_new_device, 12),
            (self.takeover, 14),
            (self.out_of_region, 12),
            (self.card_testing, 3),
            (self.new_phone, 14),
            (self.trip, 9),
            (self.big_purchase, 9),
            (self.plain, 8),
        ]
        kinds, weights = zip(*mix)
        span = (HISTORY_END - HISTORY_START).total_seconds()
        placed = 0
        while placed < N_HISTORY:
            c = r.choice(self.customers)
            if c["id"] in reserved:
                continue
            t0 = HISTORY_START + timedelta(seconds=r.uniform(0, span))
            t0 = t0.replace(hour=r.randint(8, 21))
            if not self.reserve(c, t0 - timedelta(days=3), t0 + timedelta(days=10)):
                continue
            kind = r.choices(kinds, weights)[0]
            kwargs = {}
            if kind == self.out_of_region:
                kwargs["concurrent"] = r.random() < 0.4
            if kind == self.trip:
                kwargs["concurrent"] = r.random() < 0.3
            txns, outcome, pattern, note = kind(c, r.choice(c["cards"]), t0, **kwargs)
            self.close(c, txns[0]["card"], txns, outcome, pattern, note)
            placed += 1

    # --- the device ring -----------------------------------------------------
    def plant_ring(self, victims):
        """Three customers' cards run repeated new-device, proxy-marked purchases
        through one rare device profile in early November. Each is closed as
        confirmed fraud before the open case that reaches the same profile."""
        r = self.rng
        cards = [v["cards"][0] for v in victims]
        for i, v in enumerate(victims):
            t0 = datetime(2016, 11, 1 + 3 * i, r.randint(9, 20))
            self.reserve(v, t0 - timedelta(days=3), t0 + timedelta(days=10))
            txns = [
                self.add(
                    v,
                    cards[i],
                    t0 + timedelta(hours=r.uniform(0, 72)) if k else t0,
                    self.amount(v, 1.5, 4),
                    "online",
                    device=RING_DEVICE,
                    id_15="New",
                    proxy=r.choice(FRAUD_PROXIES[:2]),
                )
                for k in range(r.randint(2, 3))
            ]
            others = [cd["id"] for cd in cards if cd is not cards[i]]
            note = (
                "Repeated purchases from a device profile shared with other customers' cards, "
                "each time marked new and behind a proxy. Matches none of the documented "
                "patterns; escalated and reported."
            )
            pattern = "undocumented" if i < 2 else "card_not_present_new_device"
            self.close(
                v,
                cards[i],
                txns,
                "confirmed_fraud",
                pattern,
                note,
                connected=others,
                alert=False,
            )

    # --- the twenty open cases -----------------------------------------------
    def plant_cases(self):
        r = self.rng
        pool = sorted(self.customers, key=lambda c: c["id"])
        r.shuffle(pool)
        used = set()

        def pick(test=lambda c: True):
            for c in pool:
                if c["id"] not in used and test(c):
                    used.add(c["id"])
                    return c
            raise RuntimeError("no customer fits the case spec")

        def special(i, rate, start):
            c = self.customer(N_CUSTOMERS + i, rate=rate)
            self.background(c, start, END)
            self.customers.append(c)
            used.add(c["id"])
            return c

        regular = lambda c: 0.22 <= c["rate"] <= 0.6  # noqa: E731
        slow = lambda c: 0.12 <= c["rate"] <= 0.3 and len(c["cards"]) == 1  # noqa: E731

        def day(d, h):
            return datetime(2016, 11, 12) + timedelta(
                days=d, hours=h, minutes=r.randint(0, 59)
            )

        specs = []  # (trigger_type, customer, card, flagged txn, risk)

        def case(trigger, c, txns, flagged=None, risk=None):
            flagged = flagged or txns[-1]
            if risk is not None:
                flagged["risk"] = risk
            specs.append((trigger, c, flagged))

        def plant(c, t0, days=6):
            self.reserve(c, t0 - timedelta(days=3), t0 + timedelta(days=days))

        # 001 card testing
        c, t0 = pick(regular), day(1, 13)
        plant(c, t0)
        txns, *_ = self.card_testing(c, c["cards"][0], t0, id_15="Unknown")
        case("risk_score", c, txns, risk=0.88)
        # 002 takeover from the account's own known device, reported by the customer
        c, t0 = pick(regular), day(3, 10)
        plant(c, t0)
        txns, *_ = self.takeover(c, c["cards"][0], t0)
        online = [t for t in txns if t["channel"] == "online"]
        case("customer_report", c, txns, flagged=online[-1])
        # 003 multi-day run in a new billing region
        c, t0 = pick(regular), day(4, 11)
        plant(c, t0)
        txns, *_ = self.out_of_region(c, c["cards"][0], t0, days=3)
        case("risk_score", c, txns, risk=0.79)
        # 004 velocity burst against the card's own rhythm
        c, t0 = pick(slow), day(6, 9)
        plant(c, t0)
        txns, *_ = self.cnp(c, c["cards"][0], t0, n=6, hours=13, device=c["devices"][0])
        case("analyst_request", c, txns)
        # 005 out-of-region use while the customer keeps shopping at home
        c, t0 = pick(regular), day(7, 12)
        plant(c, t0)
        txns, *_ = self.out_of_region(c, c["cards"][0], t0, days=2, concurrent=True)
        case("customer_report", c, txns)
        # 006 cleared shape: a new phone
        c, t0 = pick(regular), day(9, 19)
        plant(c, t0)
        txns, *_ = self.new_phone(c, c["cards"][0], t0)
        case("risk_score", c, txns, risk=0.86)
        # 007 cleared shape: a one-day trip
        c, t0 = pick(regular), day(10, 10)
        plant(c, t0)
        txns, *_ = self.trip(c, c["cards"][0], t0, days=1)
        case("risk_score", c, txns, risk=0.74)
        # 008 cleared shape: one big intended purchase
        c, t0 = pick(regular), day(12, 15)
        plant(c, t0)
        txns, *_ = self.big_purchase(c, c["cards"][0], t0, channel="in_person")
        case("risk_score", c, txns, risk=0.90)
        # 009 the ring's device profile reaches a fourth customer
        c, t0 = pick(regular), day(10, 21)
        plant(c, t0)
        self.quiet(
            c, t0 - timedelta(days=2), t0 + timedelta(days=2), card=c["cards"][0]
        )
        txns, *_ = self.cnp_new_device(
            c, c["cards"][0], t0, device=RING_DEVICE, proxy="IP_PROXY:ANONYMOUS"
        )
        for t in txns:
            t["id_15"] = "New"
        case("risk_score", c, txns, flagged=txns[0], risk=0.84)
        # 010 disputed charge that matches a monthly recurring amount
        c = special(0, 0.35, START)
        charge = r.randint(19, 49) + 0.99
        months = [datetime(2016, m, 14, 6, r.randint(0, 59)) for m in range(7, 13)]
        for ts in months:
            self.add(
                c,
                c["cards"][0],
                ts,
                charge,
                "online",
                product="S",
                device=c["devices"][0],
            )
        plant(c, months[-1])
        case("customer_report", c, [self.txns[-1]])
        # 011 card-not-present fraud from a recognised device
        c, t0 = pick(regular), day(15, 11)
        plant(c, t0)
        txns, *_ = self.cnp(c, c["cards"][0], t0, n=3, hours=5, device=c["devices"][0])
        case("risk_score", c, txns, risk=0.63)
        # 012 new device behind a proxy, reported by the customer
        c, t0 = pick(regular), day(16, 20)
        plant(c, t0)
        txns, *_ = self.cnp_new_device(c, c["cards"][0], t0, proxy="IP_PROXY:HIDDEN")
        case("customer_report", c, txns)
        # 013 takeover that ends in card-present use
        c, t0 = pick(regular), day(18, 9)
        plant(c, t0)
        txns, *_ = self.takeover(c, c["cards"][0], t0, in_person_last=True)
        case("risk_score", c, txns, risk=0.81)
        # 014 cleared shape: an ordinary purchase
        c, t0 = pick(regular), day(19, 17)
        plant(c, t0)
        txns, *_ = self.plain(c, c["cards"][0], t0, channel="in_person")
        case("risk_score", c, txns, risk=0.57)
        # 015 a customer with almost no history
        t0 = day(21, 14)
        c = special(1, 0.3, t0 - timedelta(days=14))
        plant(c, t0)
        txns, *_ = self.cnp(c, c["cards"][0], t0, n=2, hours=3)
        case("customer_report", c, txns)
        # 016 cleared shape: a new phone, larger purchase
        c, t0 = pick(regular), day(23, 12)
        plant(c, t0)
        txns, *_ = self.new_phone(c, c["cards"][0], t0, scale=(2, 3))
        case("risk_score", c, txns, risk=0.69)
        # 017 new-region run on a customer with a cleared trip on file
        c = pick(regular)
        earlier = datetime(2016, 9, 10, 11)
        self.reserve(c, earlier - timedelta(days=3), earlier + timedelta(days=10))
        txns, outcome, pattern, note = self.trip(c, c["cards"][0], earlier, days=2)
        self.close(c, c["cards"][0], txns, outcome, pattern, note)
        t0 = day(25, 10)
        plant(c, t0)
        txns, *_ = self.out_of_region(c, c["cards"][0], t0, days=3)
        case("analyst_request", c, txns)
        # 018 a heavy run of online purchases
        c, t0 = pick(regular), day(27, 8)
        plant(c, t0)
        txns, *_ = self.cnp(c, c["cards"][0], t0, n=9, hours=36)
        case("risk_score", c, txns, risk=0.52)
        # 019 reported card-not-present fraud above the reporting threshold
        c, t0 = pick(lambda c: regular(c) and c["median"] >= 90), day(29, 13)
        plant(c, t0)
        txns, *_ = self.cnp(c, c["cards"][0], t0, n=4, hours=8)
        for t in txns:
            t["amount"] = round(r.uniform(520, 800), 2)
        case("customer_report", c, txns)
        # 020 cleared shape: a two-day trip while family shops at home
        c, t0 = pick(regular), day(31, 11)
        plant(c, t0)
        txns, *_ = self.trip(c, c["cards"][0], t0, days=2, concurrent=True)
        case("risk_score", c, txns, risk=0.77)

        for i, (trigger, c, f) in enumerate(specs, 1):
            if trigger != "risk_score" and f["risk"] >= 0.8:
                f["risk"] = round(r.uniform(0.1, 0.5), 2)
            delay = (
                timedelta(hours=r.uniform(20, 60))
                if trigger == "customer_report"
                else timedelta(minutes=r.randint(3, 40))
            )
            self.cases.append(
                {
                    "id": f"DEMO-{i:03d}",
                    "trigger": trigger,
                    "customer": c,
                    "card": f["card"],
                    "flagged": f,
                    "opened": (f["ts"] + delay).replace(microsecond=0),
                }
            )
        return used

    # --- output --------------------------------------------------------------
    def finalise(self):
        live = sorted(
            (t for t in self.txns if not t["dead"]), key=lambda t: (t["ts"], t["seq"])
        )
        seen = {}
        for i, t in enumerate(live):
            t["id"] = str(FIRST_TXN_ID + i)
            if t["device"] and t["id_15"] is None:
                known = seen.setdefault(t["customer"]["id"], [])
                t["id_15"] = (
                    "Unknown"
                    if self.rng.random() < 0.04
                    else "Found"
                    if t["device"] in known
                    else "New"
                )
            if t["device"]:
                seen.setdefault(t["customer"]["id"], []).append(t["device"])
        self.live = live
        self.history.sort(key=lambda h: (h["opened"], h["customer"]["id"]))


def trigger_text(case):
    f = case["flagged"]
    what = "online purchase" if f["channel"] == "online" else "card-present purchase"
    when = f["ts"].strftime("%d %b %Y")
    amount = f"${f['amount']:,.2f}"
    if case["trigger"] == "risk_score":
        return f"Transaction model alert: {what} of {amount} on {when} scored {f['risk']:.2f}."
    if case["trigger"] == "customer_report":
        return (
            f"Cardholder reports an unrecognised {what} of {amount} on {when} and says "
            "they did not make it."
        )
    return (
        f"Analyst request: review the {what} of {amount} on {when} and the related "
        "activity on this card."
    )


def write(world, out):
    r = world.rng
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "transactions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, TXN_COLUMNS, restval="", lineterminator="\n")
        w.writeheader()
        for t in world.live:
            c, card = t["customer"], t["card"]
            row = {
                "TransactionID": t["id"],
                "TransactionDT": int((t["ts"] - START).total_seconds()),
                "TransactionAmt": money(t["amount"]),
                "ProductCD": t["product"],
                **{f"card{i}": card[f"card{i}"] for i in range(1, 7)},
                "addr1": t["region"],
                "addr2": c["addr2"] if t["region"] else "",
                "P_emaildomain": c["email"]
                if t["channel"] == "online" or r.random() < 0.5
                else "",
                "C1": r.randint(1, 4),
                "C2": r.randint(1, 4),
                "C13": r.randint(1, 30),
                "C14": r.randint(1, 4),
                "D1": r.randint(0, 400),
                **t["m"],
                "customer_id": c["id"],
                "ts": fmt(t["ts"]),
                "channel": t["channel"],
                "risk_score": f"{t['risk']:.2f}",
            }
            w.writerow(row)
    with open(out / "identity.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, IDENTITY_COLUMNS, restval="", lineterminator="\n")
        w.writeheader()
        for t in world.live:
            if not t["device"]:
                continue
            kind, info, os_, browser, screen = t["device"]
            found = "Found" if t["id_15"] == "Found" else "NotFound"
            w.writerow(
                {
                    "TransactionID": t["id"],
                    "id_01": f"{-5.0 * r.randint(0, 4):.1f}",
                    "id_02": f"{r.randint(1000, 600000)}.0",
                    "id_11": "100.0",
                    "id_12": found,
                    "id_15": t["id_15"],
                    "id_23": t["proxy"],
                    "id_28": t["id_15"] if t["id_15"] in ("New", "Found") else "",
                    "id_29": found,
                    "id_30": os_,
                    "id_31": browser,
                    "id_32": "24.0" if kind == "desktop" else "32.0",
                    "id_33": screen,
                    "id_35": "T",
                    "id_36": "F",
                    "id_37": "T",
                    "id_38": r.choice(["T", "F"]),
                    "DeviceType": kind,
                    "DeviceInfo": info,
                }
            )
    with open(out / "closed_cases_history.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, HISTORY_COLUMNS, lineterminator="\n")
        w.writeheader()
        for i, h in enumerate(world.history, 1):
            fraud = h["outcome"] == "confirmed_fraud"
            w.writerow(
                {
                    "case_id": f"CC-{i:04d}",
                    "customer_id": h["customer"]["id"],
                    "card_id": h["card"]["id"],
                    "opened_at": fmt(h["opened"]),
                    "closed_at": fmt(h["closed"]),
                    "outcome": h["outcome"],
                    "pattern": h["pattern"],
                    "first_fraud_txn_id": h["txns"][0]["id"] if fraud else "",
                    "txn_ids": "|".join(t["id"] for t in h["txns"]),
                    "n_txns": len(h["txns"]),
                    "exposure_usd": money(h["exposure"]),
                    "connected_card_ids": "|".join(h["connected"]),
                    "actions_taken": "|".join(h["actions"]),
                    "report_filed": "Yes" if h["report"] else "No",
                    "analyst_notes": h["note"],
                }
            )
    with open(out / "case_pack.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, CASE_COLUMNS, lineterminator="\n")
        w.writeheader()
        for case in world.cases:
            w.writerow(
                {
                    "case_id": case["id"],
                    "opened_at": fmt(case["opened"]),
                    "trigger_type": case["trigger"],
                    "trigger_text": trigger_text(case),
                    "flagged_txn_id": case["flagged"]["id"],
                    "card_id": case["card"]["id"],
                    "customer_id": case["customer"]["id"],
                    "risk_score": f"{case['flagged']['risk']:.2f}",
                }
            )
    (out / "README.md").write_text(README)
    (out / DEMO_MARKER).write_text(
        "Synthetic demo data from scripts/generate_demo_data.py\n"
    )


def generate(out, seed=SEED):
    world = World(seed)
    reserved = world.plant_cases()
    ring = [c for c in world.customers if c["id"] not in reserved][:3]
    world.plant_ring(ring)
    world.plant_history(reserved | {c["id"] for c in ring})
    world.finalise()
    write(world, out)
    return {
        "transactions": len(world.live),
        "identity_records": sum(1 for t in world.live if t["device"]),
        "historical_cases": len(world.history),
        "cases": len(world.cases),
        "seed": seed,
        "out": str(out),
    }


README = """\
# Trace demo dataset (synthetic)

This directory was written by `scripts/generate_demo_data.py`. Every customer, card,
device, amount and case narrative in it is synthetic and drawn from a fixed seed, so
the same seed always produces the same files. It has the column layout of the
benchmark Trace was built against, at about 1.5% of the size, so the whole pipeline
runs on a laptop in minutes. No row here describes a real person or a real
transaction, and nothing in it is copied from the benchmark.

## Files

- `transactions.csv`: one row per card transaction. IEEE-CIS-style columns, then
  `customer_id`, `ts`, `channel` and the bank's `risk_score`.
- `identity.csv`: device and network fields for the transactions that have them.
- `closed_cases_history.csv`: closed investigations with outcome, pattern and notes.
- `case_pack.csv`: the twenty open cases, `DEMO-001` to `DEMO-020`.

# Fraud Policy

This is the bank's policy for card-fraud investigations. It is written for this
synthetic dataset. Trace applies it deterministically, and no real banking,
customer or regulatory action is ever taken.

### 1. Purpose

Stop losses to the cardholder without stopping the cardholder. Actions that affect
the customer are taken on evidence about the activity, never on the alert score
alone. Monitoring is the default containment step, because it limits further
exposure at no cost to a legitimate customer.

### 2. Actions and approval

Actions that do not affect the customer run automatically: ALLOW_TRANSACTION,
MONITOR_CARD, MONITOR_CONNECTED_CARDS, WARN_CUSTOMER, VERIFY_WITH_CUSTOMER,
STEP_UP_AUTH, GENERATE_REPORT, CREATE_CASE, ESCALATE_TO_ANALYST and CLOSE_NO_FRAUD.

DECLINE_TRANSACTION needs level-1 (L1) approval. BLOCK_CARD needs L1 approval when the
exposure is $2,500 or less, and level-2 (L2) approval above that. BLOCK_ALL_CARDS
and FILE_REPORT always need L2 approval.

A fraud finding that rests on behavioural evidence alone, with no cardholder denial,
goes to an analyst before any action that affects the customer.

### 3. Decision rules

R1. A weak or single-signal case is verified with the cardholder before anything is
blocked.

R2. A cardholder's denial is direct evidence. Recommend blocking the card, with the
approval its exposure requires, and record the case.

R3. A cardholder's confirmation settles the transaction question. Close with no fraud.

R4. If the cardholder does not reply within 24 hours, monitor the card. A pending
authorisation may be declined with L1 approval. Escalate to an analyst when the
exposure is above $500.

R5. Card testing is at least three online transactions under $5 on one card inside an
hour, followed by a larger purchase. Decline it and require step-up
authentication. If a purchase over $100 has already cleared, recommend blocking the
card.

R6. Several cards belonging to different customers that run repeated suspicious
activity through one shared device profile, corroborated by prior confirmed cases,
are connected activity. Monitor the connected cards and consider a report.

R7. When a disputed charge matches an earlier recurring amount, verify with the
cardholder and explain the recurring-charge possibility. Do not assert a merchant's
identity; the dataset does not carry one.

R8. Conflicting evidence, or an uncertain case with more than $500 exposed, goes to an
analyst.

R9. Activity that matches none of the documented patterns but repeats across
customers is escalated to an analyst and considered for a report.

### 3a. A case is not a report

CREATE_CASE opens an internal investigation record. FILE_REPORT is an external
suspicious-activity report. A report needs strong suspicion together with either
more than $1,000 exposed or corroborated connected activity, and every report has a
case behind it.

### 4. Exposure

Exposure is the total amount of the transactions found to be part of the episode.
It drives the approval route and the reporting threshold, so the episode is scoped
narrowly: the same card, the same channel, close in time to the flagged transaction.

### 5. Gathering more evidence

When the evidence cannot decide, ask the cardholder whether they made the flagged
transaction. In this environment every reply is simulated and labelled as simulated.

### 6. Stopping

Close a case when at least two independent findings point the same way. Otherwise
request the evidence that would move it.

### 7. Explaining

Every claim cites the transactions, cards, devices or prior cases it rests on, and
states which way it points.

# Answer Format

Each investigation produces one JSON answer, validated against
`docs/answer.schema.json`. It has three parts: `case` (status, verdict, probability,
pattern, affected transactions, exposure, evidence and similar prior cases), `sar`
(whether a report is filed, and why) and `next_best_actions` (the initial and final
recommended actions, each with its approval route, and what changed between them).

# Dataset notes

## The five known fraud patterns

card_testing: several tiny online authorisations on one card inside an hour, then a
larger purchase once the card is known to work.

account_takeover: someone else operating the customer's account, often from a device
the account already knows, mixing online and card-present use while the encoded
match fields disagree.

card_not_present_fraud: online purchases with stolen card details, usually in a short
run, while the cardholder still holds the card.

card_not_present_new_device: online purchases from a device profile the account has
never used. Taken alone this is weak: most new devices are cardholders with new
phones.

out_of_region_use: card-present purchases in a billing region the customer has no
history in, sustained over more than one day.

Activity that is clearly fraud but fits none of these is `undocumented`. Cleared
cases carry the pattern `none`.

## Regulatory references

These references describe the general framework the policy is modelled on. This
dataset is synthetic and nothing here is legal advice.

Suspicious activity reporting by US banks is governed by 31 CFR 1020.320. The bank's
internal threshold for considering a report is lower than the regulatory one.

Cardholder disputes of unauthorised electronic transfers fall under Regulation E
(12 CFR 1005), and credit card billing errors under Regulation Z (12 CFR 1026).

## Things to know

addr1 is an anonymised billing-region code, not a location. It supports "this region
is new for this customer", never distance or travel time.

The V, C, D, M and id_ columns are unnamed features. Count them and compare them; do
not give them meanings.

A device profile is DeviceInfo, OS, browser and screen combined. Common handsets
collide across customers, so a shared profile is a lead, not an identity.

The risk score decides which alerts are opened. Within the opened alerts it is drawn
independently of the outcome, so it is not evidence.

Card IDs appear only on transactions anchored by a case or a closed investigation.
Ingest propagates a card ID only where that anchor is unambiguous.

## Rules

Use only what was known when the case was opened: transactions up to `opened_at`, and
closed cases whose `closed_at` falls before it. Cite the IDs behind every claim. Never
take a real action; this is a workbench, not a bank.
"""


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=DATA / "raw")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument(
        "--force", action="store_true", help="overwrite files this script did not write"
    )
    args = p.parse_args()
    present = [f for f in FILES if (args.out / f).exists()]
    if present and not (args.out / DEMO_MARKER).exists() and not args.force:
        raise SystemExit(
            f"{args.out} already holds {', '.join(present)} that this script did not "
            "write (the full benchmark?). Move them aside, or pass --force."
        )
    report = generate(args.out, args.seed)
    print("\n".join(f"{k}: {v}" for k, v in report.items()))


if __name__ == "__main__":
    main()
