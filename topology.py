"""
topology.py
-----------
Mininet Topology – Packet Drop Simulator
Course   : Computer Networks (PESU, 4th Semester)

Topology
--------
    h1 (10.0.0.1) ─┐
    h2 (10.0.0.2) ─┤── s1 (OVS, OpenFlow 1.3)  ──►  Ryu Controller (6633)
    h3 (10.0.0.3) ─┘

Usage
-----
    # Terminal 1 – start controller
    ryu-manager drop_controller.py

    # Terminal 2 – start topology
    sudo python3 topology.py
"""

from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info
import time


def build_topology():
    """
    Create and start the Mininet network, then open the CLI for manual testing.
    """
    setLogLevel('info')

    # ── Network setup ─────────────────────────────────────────────────────────
    net = Mininet(
        controller=RemoteController,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=False,
    )

    # ── Controller ────────────────────────────────────────────────────────────
    info("*** Adding Ryu remote controller\n")
    c0 = net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6633,
    )

    # ── Switch ────────────────────────────────────────────────────────────────
    info("*** Adding switch\n")
    s1 = net.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')

    # ── Hosts ─────────────────────────────────────────────────────────────────
    info("*** Adding hosts\n")
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')

    # ── Links (100 Mbps, 1 ms delay) ─────────────────────────────────────────
    info("*** Creating links\n")
    net.addLink(h1, s1, bw=100, delay='1ms')
    net.addLink(h2, s1, bw=100, delay='1ms')
    net.addLink(h3, s1, bw=100, delay='1ms')

    # ── Start network ─────────────────────────────────────────────────────────
    info("*** Starting network\n")
    net.start()

    # Give OVS a moment to connect to the Ryu controller
    info("*** Waiting for controller connection (3s)...\n")
    time.sleep(3)

    # ── Print topology summary ────────────────────────────────────────────────
    info("\n" + "="*60 + "\n")
    info("  Topology:  h1─┐\n")
    info("             h2─┤── s1 ──► Ryu (127.0.0.1:6633)\n")
    info("             h3─┘\n")
    info("  Drop Policy:  h1 ↔ h2  (bidirectional, permanent)\n")
    info("  Allowed  :    h1 ↔ h3,  h2 ↔ h3\n")
    info("="*60 + "\n\n")
    info("  Quick tests:\n")
    info("    mininet> h1 ping -c4 h2   # expect 100% loss\n")
    info("    mininet> h3 ping -c4 h1   # expect   0% loss\n")
    info("    mininet> h3 iperf -s &\n")
    info("    mininet> h1 iperf -c h3   # expect normal throughput\n")
    info("    mininet> h1 iperf -c h2   # expect connection failure\n")
    info("="*60 + "\n\n")

    # ── Open interactive CLI ──────────────────────────────────────────────────
    CLI(net)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    info("*** Stopping network\n")
    net.stop()


if __name__ == '__main__':
    build_topology()
