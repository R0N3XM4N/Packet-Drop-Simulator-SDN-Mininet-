"""
drop_controller.py
------------------
Ryu SDN Controller – Packet Drop Simulator
Course   : Computer Networks (PESU, 4th Semester)
Protocol : OpenFlow 1.3

Topology
--------
    h1 (10.0.0.1) ─┐
    h2 (10.0.0.2) ─┤── s1 (OVS)
    h3 (10.0.0.3) ─┘

Drop Policy
-----------
  h1 ↔ h2  →  DROPPED  (bidirectional, priority=200, permanent)
  h1 ↔ h3  →  ALLOWED  (learning-switch forwarding)
  h2 ↔ h3  →  ALLOWED  (learning-switch forwarding)

Test Scenarios
--------------
  Scenario 1 (Blocked) : h1 ping h2   → 100% packet loss
  Scenario 2 (Allowed) : h3 ping h1   →   0% packet loss
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, arp
import logging

# ── Drop policy: (src_ip, dst_ip) pairs that will be permanently blocked ─────
DROP_RULES = [
    ("10.0.0.1", "10.0.0.2"),   # h1 → h2
    ("10.0.0.2", "10.0.0.1"),   # h2 → h1  (bidirectional block)
]

PRIORITY_TABLE_MISS = 0     # lowest  – send unknown packets to controller
PRIORITY_FORWARD    = 1     # normal  – learned forwarding entries
PRIORITY_DROP       = 200   # highest – explicit drop rules


class DropController(app_manager.RyuApp):
    """
    Packet Drop Simulator Controller.

    On switch connect  → installs permanent DROP rules for the blocked pair,
                         installs table-miss to send unknowns to controller.
    On packet_in       → ARP is flooded; other IP traffic uses learning-switch
                         forwarding (drop rules at the switch prevent blocked
                         pairs from ever reaching packet_in).
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(DropController, self).__init__(*args, **kwargs)
        # mac_to_port[dpid][mac] = out_port
        self.mac_to_port = {}
        self.logger.setLevel(logging.DEBUG)

    # ── Helper: send a FlowMod to the switch ─────────────────────────────────

    def add_flow(self, datapath, priority, match, actions,
                 idle_timeout=0, hard_timeout=0):
        """
        Install a flow rule on the given datapath.

        idle_timeout=0 / hard_timeout=0  → rule never expires (permanent).
        Pass non-zero values for soft expiry rules.
        """
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser

        # Empty actions list means DROP (no OFPIT_APPLY_ACTIONS at all)
        if actions:
            inst = [parser.OFPInstructionActions(
                        ofproto.OFPIT_APPLY_ACTIONS, actions)]
        else:
            inst = []   # explicit drop – no instructions

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    # ── Switch handshake: install table-miss + permanent drop rules ───────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser   = datapath.ofproto_parser
        ofproto  = datapath.ofproto

        self.logger.info("[SWITCH] Datapath %s connected.", datapath.id)

        # 1. Table-miss: send unmatched packets to controller
        match   = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, PRIORITY_TABLE_MISS, match, actions)
        self.logger.info("[FLOW] Installed table-miss rule (priority=0).")

        # 2. Permanent DROP rules for the blocked pairs
        for (src_ip, dst_ip) in DROP_RULES:
            match = parser.OFPMatch(
                eth_type=0x0800,        # IPv4
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )
            # Empty actions → DROP
            self.add_flow(datapath, PRIORITY_DROP, match, actions=[],
                          idle_timeout=0, hard_timeout=0)
            self.logger.info(
                "[FLOW] DROP rule installed: %s → %s (priority=%d, permanent)",
                src_ip, dst_ip, PRIORITY_DROP
            )

    # ── Packet-In handler: learning switch for non-blocked traffic ────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg      = ev.msg
        datapath = msg.datapath
        parser   = datapath.ofproto_parser
        ofproto  = datapath.ofproto
        dpid     = datapath.id

        pkt     = packet.Packet(msg.data)
        eth     = pkt.get_protocol(ethernet.ethernet)
        ip_pkt  = pkt.get_protocol(ipv4.ipv4)
        arp_pkt = pkt.get_protocol(arp.arp)

        dst     = eth.dst
        src     = eth.src
        in_port = msg.match['in_port']

        # ── MAC learning ──────────────────────────────────────────────────────
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # ── Decide output port ────────────────────────────────────────────────

        if arp_pkt:
            # ARP: always flood so hosts can resolve MACs
            out_port = ofproto.OFPP_FLOOD
            self.logger.debug(
                "[ARP]  dpid=%s  %s → %s  in_port=%s  flood",
                dpid, src, dst, in_port
            )

        elif ip_pkt:
            # Safety net: if a blocked IP pair somehow reaches packet_in
            # (e.g., controller started after switch was already running),
            # drop it explicitly here too.
            if (ip_pkt.src, ip_pkt.dst) in DROP_RULES:
                self.logger.warning(
                    "[DROP] Blocked packet reached controller: %s → %s",
                    ip_pkt.src, ip_pkt.dst
                )
                return  # do not forward

            out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
            self.logger.info(
                "[FWD]  dpid=%s  %s→%s  in_port=%s  out_port=%s",
                dpid, ip_pkt.src, ip_pkt.dst, in_port, out_port
            )

        else:
            # Non-IP, non-ARP (e.g., LLDP, IPv6): flood
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # ── Install a forwarding flow rule (skip for pure floods) ─────────────
        if out_port != ofproto.OFPP_FLOOD:
            if ip_pkt:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_type=0x0800,
                    ipv4_src=ip_pkt.src,
                    ipv4_dst=ip_pkt.dst,
                )
            else:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_src=src,
                    eth_dst=dst,
                )
            self.add_flow(datapath, PRIORITY_FORWARD, match, actions,
                          idle_timeout=30, hard_timeout=0)

        # ── Send packet out ───────────────────────────────────────────────────
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data,
        )
        datapath.send_msg(out)
