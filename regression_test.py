"""
regression_test.py
------------------
Regression Test Suite – Packet Drop Simulator
Course   : Computer Networks (PESU, 4th Semester)

Purpose
-------
Verifies that:
  1. Drop rules for h1 ↔ h2 are present in the OVS flow table.
  2. Drop rules persist after 30 seconds (permanence test).
  3. No spurious drop rules exist for allowed pairs (h1↔h3, h2↔h3).

Run AFTER starting Ryu and Mininet:
    sudo python3 regression_test.py

Return codes
------------
  0 → all tests passed
  1 → one or more tests failed
"""

import subprocess
import sys
import time

# ── Configuration ─────────────────────────────────────────────────────────────

SWITCH         = "s1"
OFPROTO        = "OpenFlow13"
PERSISTENCE_DELAY = 30      # seconds to wait before re-checking

# Rules that MUST be present (drop rules)
EXPECTED_DROPS = [
    {"src": "10.0.0.1", "dst": "10.0.0.2"},   # h1 → h2
    {"src": "10.0.0.2", "dst": "10.0.0.1"},   # h2 → h1
]

# Pairs that must NOT have drop rules
ALLOWED_PAIRS = [
    ("10.0.0.1", "10.0.0.3"),   # h1 ↔ h3
    ("10.0.0.3", "10.0.0.1"),
    ("10.0.0.2", "10.0.0.3"),   # h2 ↔ h3
    ("10.0.0.3", "10.0.0.2"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS  = "\033[92m[PASS]\033[0m"
FAIL  = "\033[91m[FAIL]\033[0m"
INFO  = "\033[94m[INFO]\033[0m"
WARN  = "\033[93m[WARN]\033[0m"

results = []


def dump_flows(switch=SWITCH):
    """Return raw output of ovs-ofctl dump-flows."""
    cmd = ["sudo", "ovs-ofctl", "-O", OFPROTO, "dump-flows", switch]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                       universal_newlines=True)
        return out
    except subprocess.CalledProcessError as e:
        print(f"{FAIL} Could not dump flows: {e.output}")
        sys.exit(1)


def rule_is_drop(line: str) -> bool:
    """A flow entry is a drop rule if its actions field is empty."""
    # OVS prints 'actions=drop' explicitly in OF1.3
    return "actions=drop" in line or "actions=" not in line.split("priority")[1] if "priority" in line else False


def find_drop_rule(flow_dump: str, src_ip: str, dst_ip: str) -> bool:
    """
    Return True if a drop rule matching src_ip → dst_ip is found.
    Checks for both 'actions=drop' and empty actions list.
    """
    for line in flow_dump.splitlines():
        if f"nw_src={src_ip}" in line or f"ipv4_src={src_ip}" in line:
            if f"nw_dst={dst_ip}" in line or f"ipv4_dst={dst_ip}" in line:
                # Verify it is indeed a drop action
                if "actions=drop" in line or \
                   (line.strip().endswith("actions=") ) or \
                   ("actions=" in line and line.split("actions=")[1].strip() in ("", "drop")):
                    return True
    return False


def find_any_drop_rule(flow_dump: str, src_ip: str, dst_ip: str) -> bool:
    """Return True if ANY rule (drop or not) matches this src/dst pair."""
    for line in flow_dump.splitlines():
        has_src = f"nw_src={src_ip}" in line or f"ipv4_src={src_ip}" in line
        has_dst = f"nw_dst={dst_ip}" in line or f"ipv4_dst={dst_ip}" in line
        if has_src and has_dst and ("actions=drop" in line):
            return True
    return False


def record(name: str, passed: bool, detail: str = ""):
    tag = PASS if passed else FAIL
    print(f"  {tag}  {name}")
    if detail:
        print(f"         {detail}")
    results.append(passed)


# ── Test functions ────────────────────────────────────────────────────────────

def test_drop_rules_present(flow_dump: str):
    print("\n── Test 1: Drop rules installed for h1 ↔ h2 ──────────────────")
    for rule in EXPECTED_DROPS:
        src, dst = rule["src"], rule["dst"]
        found = find_drop_rule(flow_dump, src, dst)
        record(
            f"DROP rule {src} → {dst}",
            found,
            "Rule not found in flow table!" if not found else ""
        )


def test_allowed_pairs_not_blocked(flow_dump: str):
    print("\n── Test 2: Allowed pairs have no drop rules ───────────────────")
    for (src, dst) in ALLOWED_PAIRS:
        has_drop = find_any_drop_rule(flow_dump, src, dst)
        record(
            f"No DROP for {src} → {dst}",
            not has_drop,
            "Unexpected drop rule found!" if has_drop else ""
        )


def test_table_miss_present(flow_dump: str):
    print("\n── Test 3: Table-miss (priority=0) rule exists ─────────────")
    has_miss = any(
        "priority=0" in line and "CONTROLLER" in line
        for line in flow_dump.splitlines()
    )
    record("Table-miss rule (priority=0, send to CONTROLLER)", has_miss,
           "Table-miss rule missing — controller may not handle unknown packets." if not has_miss else "")


def test_rule_persistence():
    print(f"\n── Test 4: Drop rules persist after {PERSISTENCE_DELAY}s ──────────────")
    print(f"  {INFO} Waiting {PERSISTENCE_DELAY} seconds...")
    time.sleep(PERSISTENCE_DELAY)
    flow_dump = dump_flows()
    for rule in EXPECTED_DROPS:
        src, dst = rule["src"], rule["dst"]
        found = find_drop_rule(flow_dump, src, dst)
        record(
            f"DROP rule {src} → {dst} still present after {PERSISTENCE_DELAY}s",
            found,
            "Rule expired — check idle_timeout/hard_timeout!" if not found else ""
        )


def test_drop_rule_priority(flow_dump: str):
    print("\n── Test 5: Drop rules have higher priority than forwarding rules ─")
    # Extract priorities for drop rules
    for rule in EXPECTED_DROPS:
        src, dst = rule["src"], rule["dst"]
        drop_priority = None
        for line in flow_dump.splitlines():
            has_src = f"nw_src={src}" in line or f"ipv4_src={src}" in line
            has_dst = f"nw_dst={dst}" in line or f"ipv4_dst={dst}" in line
            if has_src and has_dst:
                # Extract priority value
                for token in line.split(","):
                    token = token.strip()
                    if token.startswith("priority="):
                        try:
                            drop_priority = int(token.split("=")[1])
                        except (ValueError, IndexError):
                            pass
        if drop_priority is not None:
            record(
                f"DROP rule {src}→{dst} priority={drop_priority} (expected ≥ 100)",
                drop_priority >= 100,
                f"Priority {drop_priority} may be too low — forwarding rules could match first." if drop_priority < 100 else ""
            )
        else:
            record(f"DROP rule {src}→{dst} priority readable", False,
                   "Could not parse priority from flow dump.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Packet Drop Simulator – Regression Test Suite")
    print(f"  Switch : {SWITCH}  |  Protocol : {OFPROTO}")
    print("=" * 60)

    # Initial dump
    print(f"\n{INFO} Fetching flow table from {SWITCH}...")
    flow_dump = dump_flows()
    print(f"\n{INFO} Raw flow table:\n")
    for line in flow_dump.strip().splitlines():
        print(f"    {line}")

    # Run tests
    test_drop_rules_present(flow_dump)
    test_allowed_pairs_not_blocked(flow_dump)
    test_table_miss_present(flow_dump)
    test_drop_rule_priority(flow_dump)
    test_rule_persistence()     # waits PERSISTENCE_DELAY seconds

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed}/{total} tests passed")
    if passed == total:
        print(f"  {PASS}  All regression tests PASSED.")
    else:
        failed = [i + 1 for i, r in enumerate(results) if not r]
        print(f"  {FAIL}  {total - passed} test(s) FAILED: checks #{', #'.join(map(str, failed))}")
    print("=" * 60 + "\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
