#!/usr/bin/env bash
# run_tests.sh
# ─────────────────────────────────────────────────────────────────────────────
# Automated test runner for Packet Drop Simulator
# Runs from INSIDE the Mininet CLI or via:
#   sudo mn --topo single,3 --controller=remote --switch ovsk,protocols=OpenFlow13 \
#        --test "source run_tests.sh"
#
# For a self-contained demo, execute the commands in this file manually
# from the Mininet CLI prompt.
# ─────────────────────────────────────────────────────────────────────────────

set -e
SWITCH="s1"
OFPROTO="OpenFlow13"

divider() { echo; echo "────────────────────────────────────────────────────"; }

# ── 0. Flush any stale Mininet state ─────────────────────────────────────────
echo "Cleaning up previous Mininet state..."
sudo mn -c 2>/dev/null || true

# ── 1. Display flow table immediately after controller starts ─────────────────
divider
echo "STEP 1 – Current Flow Table (should contain drop rules)"
divider
sudo ovs-ofctl -O "$OFPROTO" dump-flows "$SWITCH"

# ── 2. Scenario A: Blocked traffic – h1 ping h2 (expect 100% loss) ───────────
divider
echo "SCENARIO A – h1 → h2 (BLOCKED, expect 100% packet loss)"
divider
sudo mn --topo single,3 \
        --controller=remote \
        --switch ovsk,protocols=OpenFlow13 \
        --test "h1 ping -c 10 h2" 2>&1 | tail -20

# ── 3. Scenario B: Allowed traffic – h3 ping h1 (expect 0% loss) ─────────────
divider
echo "SCENARIO B – h3 → h1 (ALLOWED, expect 0% packet loss)"
divider
sudo mn --topo single,3 \
        --controller=remote \
        --switch ovsk,protocols=OpenFlow13 \
        --test "h3 ping -c 10 h1" 2>&1 | tail -20

# ── 4. iperf throughput test (allowed path: h1 ↔ h3) ─────────────────────────
divider
echo "IPERF – h1 → h3 (ALLOWED, expect normal TCP throughput)"
divider
# Start iperf server on h3, run client from h1 for 5 seconds
sudo mn --topo single,3 \
        --controller=remote \
        --switch ovsk,protocols=OpenFlow13 \
        --test "h3 iperf -s -D; sleep 1; h1 iperf -c 10.0.0.3 -t 5" 2>&1 | tail -20

# ── 5. iperf blocked path: h1 ↔ h2 (expect connection refused / no traffic) ──
divider
echo "IPERF – h1 → h2 (BLOCKED, expect connection failure)"
divider
sudo mn --topo single,3 \
        --controller=remote \
        --switch ovsk,protocols=OpenFlow13 \
        --test "h2 iperf -s -D; sleep 1; h1 iperf -c 10.0.0.2 -t 5 -i 1" 2>&1 | tail -20

# ── 6. Final flow table dump ──────────────────────────────────────────────────
divider
echo "STEP 6 – Final Flow Table"
divider
sudo ovs-ofctl -O "$OFPROTO" dump-flows "$SWITCH"

divider
echo "All test scenarios complete."
echo "Run: sudo python3 regression_test.py  for automated regression checks."
divider
