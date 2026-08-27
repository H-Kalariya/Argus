"""
Seed the Medusa identity graph with demo scenarios showcasing each attack tier.

Scenarios:
  A) Legitimate users      -> no triggers, APPROVE
  B) Tier 1 bot-speed      -> 3+ accounts on one device in ~10 minutes -> BLOCK
  C) Tier 2 human mule     -> 2 accounts on one device within 24h -> STEP_UP
  D) Tier 3 long-game mule -> 4 accounts, one device fingerprint, spread over ~5 days -> FLAG

All identifiers are fake/test values.
"""

import time
from graph_db import MedusaIdentityGraph

HOUR = 3600
DAY = 24 * HOUR
MIN = 60


def seed(graph: MedusaIdentityGraph):
    graph.reset()
    now = time.time()

    # ---------------------------------------------------------------
    # A) Legitimate users — distinct devices, distinct everything.
    # ---------------------------------------------------------------
    legit = [
        ("user_priya", "Priya (legit)", "device_A1", "ip_10.0.0.5", "priya@example.com"),
        ("user_arjun", "Arjun (legit)", "device_B2", "ip_10.0.0.9", "arjun@example.com"),
    ]
    for uid, label, dev, ip, email in legit:
        graph.add_account(uid, label, created_at=now - 2 * DAY)
        graph.add_signal(uid, "device_fingerprint", dev, created_at=now - 2 * DAY)
        graph.add_signal(uid, "ip_address", ip, created_at=now - 2 * DAY)
        graph.add_signal(uid, "email", email, created_at=now - 2 * DAY)

    # ---------------------------------------------------------------
    # B) Tier 1 — Bot-speed attack. 3 accounts, same device, ~10 min.
    #    Scripted account creation / card testing.
    # ---------------------------------------------------------------
    bot_device = "device_BOT_ff31"
    bot_ip = "ip_45.9.12.200"
    for i in range(3):
        uid = f"bot_acct_{i+1}"
        t = now - (10 * MIN) + i * (3 * MIN)  # all within the last 10 minutes
        graph.add_account(uid, f"Bot account #{i+1}", created_at=t)
        graph.add_signal(uid, "device_fingerprint", bot_device, created_at=t)
        graph.add_signal(uid, "ip_address", bot_ip, created_at=t)
        graph.add_signal(uid, "email", f"winner{i+1}83@tempmail.io", created_at=t)
        # bots fail liveness (no real human performing the challenge)
        graph.add_signal(uid, "failed_liveness", bot_device, created_at=t)

    # ---------------------------------------------------------------
    # C) Tier 2 — Human-speed mule. 2 accounts, same device, within 24h.
    # ---------------------------------------------------------------
    mule2_device = "device_MULE_7a2c"
    for i in range(2):
        uid = f"mule24h_acct_{i+1}"
        t = now - (20 * HOUR) + i * (3 * HOUR)  # both within last 24h
        graph.add_account(uid, f"Mule (24h) #{i+1}", created_at=t)
        graph.add_signal(uid, "device_fingerprint", mule2_device, created_at=t)
        graph.add_signal(uid, "ip_address", "ip_103.5.44.7", created_at=t)
        graph.add_signal(uid, "email", f"raj.k{i+1}@gmail.com", created_at=t)

    # ---------------------------------------------------------------
    # D) Tier 3 — Long-game mule ring. 4 accounts, same fingerprint,
    #    spread over ~5 days, different emails. Patient recruitment.
    # ---------------------------------------------------------------
    ring_device = "device_RING_e91b"
    ring_offsets = [5 * DAY, 4 * DAY, 2 * DAY, 6 * HOUR]  # spread across the week
    ring_emails = ["deepak.m@yahoo.com", "sanjay.trader@outlook.com",
                   "meena_1988@rediffmail.com", "vikas.gupta@gmail.com"]
    for i, off in enumerate(ring_offsets):
        uid = f"ring_acct_{i+1}"
        t = now - off
        graph.add_account(uid, f"Mule ring #{i+1}", created_at=t)
        graph.add_signal(uid, "device_fingerprint", ring_device, created_at=t)
        graph.add_signal(uid, "ip_address", "ip_59.144.20.88", created_at=t)
        graph.add_signal(uid, "email", ring_emails[i], created_at=t)

    return {
        "legit_signal": ("device_fingerprint", "device_A1"),
        "tier1_signal": ("device_fingerprint", bot_device),
        "tier2_signal": ("device_fingerprint", mule2_device),
        "tier3_signal": ("device_fingerprint", ring_device),
    }


if __name__ == "__main__":
    g = MedusaIdentityGraph()
    keys = seed(g)
    print("Seeded scenarios:")
    for name, (stype, sval) in keys.items():
        tiers = g.check_velocity_tiers(stype, sval)
        print(f"  {name}: {sval} -> {tiers}")
    g.close()
