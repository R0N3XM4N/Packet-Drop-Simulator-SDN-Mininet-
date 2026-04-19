# Packet Drop Simulator — SDN Mininet Project

> **Course:** Computer Networks | PES University, 4th Semester  
> **Controller:** Ryu (OpenFlow 1.3)  
> **Simulator:** Mininet + Open vSwitch (OVS)  
> **Platform:** Mininet VM (Ubuntu 20.04) on VirtualBox

---

## Problem Statement

In traditional networks, packet filtering is configured statically on each individual device. This project demonstrates how **Software Defined Networking (SDN)** achieves the same result centrally and programmatically — using a Ryu controller to install explicit **OpenFlow drop rules** on a virtual switch, simulating selective packet loss between specific hosts.

**Objectives:**
- Install permanent drop rules via OpenFlow 1.3 flow rule installation
- Select specific flows to block (h1 ↔ h2) while allowing all others
- Measure and verify packet loss using `ping` and `iperf`
- Demonstrate controller–switch interaction through packet_in events and match+action logic
- Run a regression test to verify drop rules persist over time

---

## Topology

```
   h1  (10.0.0.1)  ── port 1 ─┐
   h2  (10.0.0.2)  ── port 2 ─┤──  s1 (OVS)  ──►  Ryu Controller (127.0.0.1:6633)
   h3  (10.0.0.3)  ── port 3 ─┘
```

**Design justification:** A single-switch topology was chosen to isolate the packet drop behavior clearly. With one switch, all traffic passes through a single data plane element, making it straightforward to observe the effect of flow rules on specific host pairs. Three hosts provide the minimum setup to demonstrate both blocked and allowed traffic simultaneously.

| Flow    | Policy            | Priority | Timeout  |
|---------|-------------------|----------|----------|
| h1 → h2 | **DROP**          | 200      | Permanent|
| h2 → h1 | **DROP**          | 200      | Permanent|
| h1 ↔ h3 | ALLOW (forward)   | 1        | 30s idle |
| h2 ↔ h3 | ALLOW (forward)   | 1        | 30s idle |
| Unknown | → Controller      | 0        | Permanent|

---

## SDN Logic & Flow Rule Implementation

### Controller Architecture

The controller (`drop_controller.py`) uses two OpenFlow event handlers:

**1. `switch_features_handler` (CONFIG_DISPATCHER)**  
Fires when a switch first connects. Immediately installs:
- A table-miss rule (priority=0) to send unknown packets to the controller
- Two permanent DROP rules (priority=200) for the h1↔h2 pair

This is **proactive rule installation** — drop rules are pushed before any traffic arrives, so blocked packets never reach the controller at all.

**2. `packet_in_handler` (MAIN_DISPATCHER)**  
Handles packets that reach the controller (ARP and allowed IP flows). Implements:
- **MAC learning:** records which port each host's MAC was seen on
- **ARP flooding:** broadcasts ARP so hosts can resolve each other's MACs
- **Learning switch forwarding:** once a MAC is learned, installs a directed forwarding rule instead of flooding

### Match–Action Design

```python
# DROP rule (empty instructions = drop in OpenFlow 1.3)
match = parser.OFPMatch(
    eth_type=0x0800,        # IPv4
    ipv4_src="10.0.0.1",
    ipv4_dst="10.0.0.2"
)
self.add_flow(datapath, priority=200, match=match, actions=[])

# FORWARD rule
match = parser.OFPMatch(in_port=in_port, eth_type=0x0800,
                         ipv4_src=ip.src, ipv4_dst=ip.dst)
actions = [parser.OFPActionOutput(out_port)]
self.add_flow(datapath, priority=1, match=match, actions=actions)
```

Drop rules at priority 200 are always evaluated before forwarding rules at priority 1, guaranteeing blocked traffic is dropped at the switch without ever reaching the controller.

---

## Files

| File | Description |
|------|-------------|
| `drop_controller.py` | Ryu SDN controller — proactive drop rules + reactive learning switch |
| `topology.py` | Mininet topology — single switch, 3 hosts, remote Ryu controller |
| `regression_test.py` | Automated regression suite — 11 checks for rule presence, priority, and persistence |
| `run_tests.sh` | Shell script for automated scenario testing |

---

## Setup & Execution

### Prerequisites

```bash
# On Mininet VM (Ubuntu 20.04) — Python 3.8 compatible
pip3 install ryu eventlet==0.30.2
sudo apt-get install -y iperf
```

### Clone the Repository

```bash
git clone https://github.com/R0N3XM4N/Packet-Drop-Simulator-SDN-Mininet-.git
cd Packet-Drop-Simulator-SDN-Mininet-
```

### Run (use tmux for multiple panes)

```bash
tmux                # start multiplexer
# Ctrl+B then " to split panes, Ctrl+B arrow to switch
```

**Pane 1 — Start Ryu controller:**
```bash
ryu-manager drop_controller.py
```

**Pane 2 — Start Mininet topology:**
```bash
sudo mn -c
sudo python3 topology.py
```

---

## Test Scenarios

### Scenario 1 — Blocked Traffic (h1 → h2)

```
mininet> h1 ping -c 10 h2
```

**Expected output:**
```
PING 10.0.0.2 (10.0.0.2) 56(84) bytes of data.

--- 10.0.0.2 ping statistics ---
10 packets transmitted, 0 received, 100% packet loss, time 9071ms
```

**Explanation:** The drop rule installed at priority 200 matches every IPv4 packet from 10.0.0.1 to 10.0.0.2 and discards it at the switch. h2 never receives any packet, so no ICMP reply is generated.

---

### Scenario 2 — Allowed Traffic (h3 → h1)

```
mininet> h3 ping -c 10 h1
```

**Expected output:**
```
PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=11.0 ms
64 bytes from 10.0.0.1: icmp_seq=2 ttl=64 time=5.71 ms
...
--- 10.0.0.1 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9005ms
```

**Explanation:** No drop rule exists for this pair. The controller's learning switch forwards packets normally. All 10 reach h1 and replies return successfully.

---

### Scenario 3 — iperf Throughput (Allowed Path: h1 → h3)

```
mininet> h3 iperf -s &
mininet> h1 iperf -c 10.0.0.3
```

**Expected output:**
```
------------------------------------------------------------
Client connecting to 10.0.0.3, TCP port 5001
------------------------------------------------------------
[  3]  0.0-10.0 sec  ~1100 MBytes  ~90 Mbits/sec
```

**Explanation:** TCP connection succeeds. Normal throughput (~90 Mbps on the 100 Mbps virtual link) confirms the allowed path is fully functional.

---

### Scenario 4 — iperf Blocked Path (h1 → h2)

```
mininet> h2 iperf -s &
mininet> h1 iperf -c 10.0.0.2
```

**Expected output:**
```
connect failed: Connection timed out
```

**Explanation:** The TCP SYN from h1 is silently dropped at the switch before reaching h2. No SYN-ACK is returned. iperf times out, confirming the drop rule is effective at the transport layer as well.

---

## Flow Table

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

**Expected entries:**
```
cookie=0x0, priority=200,ip,nw_src=10.0.0.1,nw_dst=10.0.0.2 actions=drop
cookie=0x0, priority=200,ip,nw_src=10.0.0.2,nw_dst=10.0.0.1 actions=drop
cookie=0x0, priority=1,ip,nw_src=10.0.0.3,nw_dst=10.0.0.1 actions=output:1
cookie=0x0, priority=1,ip,nw_src=10.0.0.1,nw_dst=10.0.0.3 actions=output:3
cookie=0x0, priority=0 actions=CONTROLLER:65535
```

The two `actions=drop` entries at priority 200 are the core of the simulator. They are installed proactively at switch connect and persist indefinitely (`idle_timeout=0, hard_timeout=0`).

---

## Regression Testing

Run **while Mininet and the controller are both active:**

```bash
sudo python3 regression_test.py
```

**What it verifies:**

| # | Check | Condition |
|---|-------|-----------|
| 1 | Drop rules installed | h1→h2 and h2→h1 entries with `actions=drop` |
| 2 | Allowed pairs not blocked | No drop entry for h1↔h3 or h2↔h3 |
| 3 | Table-miss rule exists | `priority=0` sends unknowns to controller |
| 4 | Drop rule priority | Both drop rules have `priority ≥ 100` |
| 5 | Persistence (30s wait) | Drop rules still present after 30 seconds |

**Expected output:**
```
════════════════════════════════════════════════════════════
  Packet Drop Simulator – Regression Test Suite
════════════════════════════════════════════════════════════
  [PASS]  DROP rule 10.0.0.1 → 10.0.0.2
  [PASS]  DROP rule 10.0.0.2 → 10.0.0.1
  [PASS]  No DROP for 10.0.0.1 → 10.0.0.3
  [PASS]  No DROP for 10.0.0.3 → 10.0.0.1
  [PASS]  No DROP for 10.0.0.2 → 10.0.0.3
  [PASS]  No DROP for 10.0.0.3 → 10.0.0.2
  [PASS]  Table-miss rule (priority=0, send to CONTROLLER)
  [PASS]  DROP rule 10.0.0.1→10.0.0.2 priority=200
  [PASS]  DROP rule 10.0.0.2→10.0.0.1 priority=200
  [PASS]  DROP rule 10.0.0.1→10.0.0.2 still present after 30s
  [PASS]  DROP rule 10.0.0.2→10.0.0.1 still present after 30s

  RESULTS: 11/11 tests passed
  [PASS]  All regression tests PASSED.
════════════════════════════════════════════════════════════
```

---

## Proof of Execution

### Controller Running — Drop Rules Installed
![controller](screenshots/controller.png)

### Scenario 1 — Blocked: h1 ping h2 (100% packet loss)
![ping_blocked](screenshots/ping_blocked.png)

### Scenario 2 — Allowed: h3 ping h1 (0% packet loss)
![ping_allowed](screenshots/ping_allowed.png)

### Scenario 3 — iperf Allowed Path: h1 → h3
![iperf_allowed](screenshots/iperf_allowed.png)

### Scenario 4 — iperf Blocked Path: h1 → h2
![iperf_blocked](screenshots/iperf_blocked.png)

### Flow Table (ovs-ofctl dump-flows s1)
![flow_table](screenshots/flow_table.png)

### Regression Test — All 11 Tests Passed
![regression](screenshots/regression.png)

---

## SDN Concepts Demonstrated

| Concept | Implementation |
|---------|---------------|
| Control / Data Plane Separation | Ryu (controller) programs OVS (switch) over OpenFlow |
| Proactive Rule Installation | Drop rules pushed at switch connect, before any traffic |
| Reactive Forwarding | packet_in used for learning-switch on allowed flows |
| Match–Action Pipeline | `OFPMatch(ipv4_src, ipv4_dst)` + `actions=[]` (drop) |
| Priority-Based Matching | Drop at 200 always wins over forward at 1 |
| Flow Rule Permanence | `idle_timeout=0, hard_timeout=0` — rules never expire |
| OpenFlow 1.3 | `OFPFlowMod`, `OFPPacketIn`, `OFPPacketOut`, `OFPInstructionActions` |

---

## References

1. OpenFlow Switch Specification v1.3.0 — Open Networking Foundation (2012).
   https://opennetworking.org/wp-content/uploads/2014/10/openflow-spec-v1.3.0.pdf

2. Ryu SDN Framework Documentation.
   https://ryu.readthedocs.io/en/latest/

3. Mininet Documentation & Walkthrough.
   http://mininet.org/walkthrough/

4. Open vSwitch Project.
   https://www.openvswitch.org/

5. Kaur, K., Singh, J., & Ghumman, N. S. (2014). Mininet as Software Defined Networking Testing Platform. International Conference on Communication, Computing & Systems.

6. Nayak, A. K., et al. (2009). Resonance: Dynamic Access Control for Enterprise Networks. ACM Workshop on Research on Enterprise Networking.
