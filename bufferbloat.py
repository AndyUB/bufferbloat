#!/usr/bin/env python3
"Problem Set 2: Bufferbloat"

from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from mininet.cli import CLI

from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser

from monitor import monitor_qlen

import sys
import os
import math

parser = ArgumentParser(description="Bufferbloat tests")
parser.add_argument('--bw-host', '-B',
                    type=float,
                    help="Bandwidth of host links (Mb/s)",
                    default=1000)

parser.add_argument('--bw-net', '-b',
                    type=float,
                    help="Bandwidth of bottleneck (network) link (Mb/s)",
                    required=True)

parser.add_argument('--delay',
                    type=float,
                    help="Link propagation delay (ms)",
                    required=True)

parser.add_argument('--dir', '-d',
                    help="Directory to store outputs",
                    required=True)

parser.add_argument('--time', '-t',
                    help="Duration (sec) to run the experiment",
                    type=int,
                    default=10)

parser.add_argument('--maxq',
                    type=int,
                    help="Max buffer size of network interface in packets",
                    default=100)

# Linux uses CUBIC-TCP by default that doesn't have the usual sawtooth
# behaviour.  For those who are curious, invoke this script with
# --cong cubic and see what happens...
# sysctl -a | grep cong should list some interesting parameters.
parser.add_argument('--cong',
                    help="Congestion control algorithm to use",
                    default="reno")

# Expt parameters
args = parser.parse_args()

class BBTopo(Topo):
    "Simple topology for bufferbloat experiment."

    def build(self, n=2):
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        # Switch s0 sits between h1 (fast LAN) and h2 (slow WAN link).
        switch = self.addSwitch('s0')

        # h1 <-> s0: fast 1 Gb/s LAN link, 10 ms one-way delay.
        # Adding h1 first makes this s0-eth1.
        self.addLink(h1, switch,
                     bw=args.bw_host,
                     delay='%dms' % args.delay,
                     use_htb=True)

        # s0 <-> h2: slow 1.5 Mb/s bottleneck, 10 ms one-way delay,
        # maxq-packet buffer (the link we study for bufferbloat).
        # Adding h2 second makes this s0-eth2 — the interface we monitor.
        self.addLink(switch, h2,
                     bw=args.bw_net,
                     delay='%dms' % args.delay,
                     max_queue_size=args.maxq,
                     use_htb=True)


# ── cwnd monitoring via ss (replaces removed tcp_probe kernel module) ──────

def start_cwnd_monitor(net, outfile):
    """Poll ss -i inside h1's namespace every 100 ms; write timestamp,cwnd."""
    h1 = net.get('h1')
    # grep -o 'cwnd:[0-9]*' works without PCRE (-P) so it's portable.
    cmd = (
        "while true; do "
        "  T=$(date +%%s.%%N); "
        "  CWND=$(ss -i dst :5001 2>/dev/null "
        "         | grep -o 'cwnd:[0-9]*' | cut -d: -f2 | head -1); "
        "  [ -n \"$CWND\" ] && printf '%%s,%%s\\n' \"$T\" \"$CWND\"; "
        "  sleep 0.1; "
        "done > %s"
    ) % outfile
    return h1.popen(cmd, shell=True)


# ── Simple wrappers around monitoring utilities ────────────────────────────

def start_qmon(iface, interval_sec=0.1, outfile="q.txt"):
    monitor = Process(target=monitor_qlen,
                      args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor

def start_iperf(net):
    h1 = net.get('h1')
    h2 = net.get('h2')
    print("Starting iperf server on h2...")
    # -w 16m: large receive window so the flow is not receiver-window limited.
    server = h2.popen("iperf -s -w 16m")
    sleep(1)
    print("Starting iperf client on h1 (long-lived flow to h2)...")
    client = h1.popen("iperf -c %s -t %d" % (h2.IP(), args.time))
    return [server, client]

def start_webserver(net):
    h1 = net.get('h1')
    # Run webserver from the bufferbloat directory so http/index.html is served
    # at URL path /http/index.html.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    proc = h1.popen("cd %s && python3 http/webserver.py" % script_dir,
                    shell=True)
    sleep(1)
    return [proc]

def start_ping(net):
    """Ping h2 from h1 at 10 Hz, recording RTTs to ping.txt."""
    h1 = net.get('h1')
    h2 = net.get('h2')
    # -i 0.1 → one ping every 100 ms (10 per second)
    proc = h1.popen(
        "ping -i 0.1 %s > %s/ping.txt" % (h2.IP(), args.dir),
        shell=True
    )
    return proc

def measure_fetch_times(net):
    """Fetch index.html from h1's webserver 3 times from h2; return elapsed seconds."""
    h1 = net.get('h1')
    h2 = net.get('h2')
    url = "http://%s/http/index.html" % h1.IP()
    times = []
    for _ in range(3):
        # Time a single wget inside h2's namespace.
        start = time()
        h2.cmd("wget -q -O /dev/null %s" % url)
        times.append(time() - start)
    return times


def bufferbloat():
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)
    os.system("sysctl -w net.ipv4.tcp_congestion_control=%s" % args.cong)
    topo = BBTopo()
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    dumpNodeConnections(net.hosts)
    net.pingAll()

    # ── Start monitoring ────────────────────────────────────────────────────
    cwnd_monitor = start_cwnd_monitor(net, '%s/cwnd.txt' % args.dir)

    # s0-eth2 is the bottleneck interface (switch side toward h2).
    qmon = start_qmon(iface='s0-eth2',
                      outfile='%s/q.txt' % args.dir)

    # ── Start traffic generators ────────────────────────────────────────────
    iperf_procs = start_iperf(net)
    ping_proc   = start_ping(net)
    webserver_procs = start_webserver(net)
    sleep(1)  # let everything initialise

    # ── Periodic webpage fetch measurements ────────────────────────────────
    all_fetch_times = []
    start_time = time()
    while True:
        sleep(5)
        now = time()
        delta = now - start_time
        ftimes = measure_fetch_times(net)
        all_fetch_times.extend(ftimes)
        print("Fetch times this round: %s" % [round(t, 3) for t in ftimes])
        if delta > args.time:
            break
        print("%.1fs left..." % (args.time - delta))

    # ── Summarise fetch times ───────────────────────────────────────────────
    if all_fetch_times:
        avg_t = sum(all_fetch_times) / len(all_fetch_times)
        variance = sum((t - avg_t) ** 2 for t in all_fetch_times) / len(all_fetch_times)
        std_t = math.sqrt(variance)
        print("\nWebpage fetch time statistics:")
        print("  Samples : %d" % len(all_fetch_times))
        print("  Average : %.3f s" % avg_t)
        print("  Std Dev : %.3f s" % std_t)
        with open('%s/fetch_times.txt' % args.dir, 'w') as fh:
            fh.write("samples=%d avg=%.3f std=%.3f\n" % (
                len(all_fetch_times), avg_t, std_t))
            for t in all_fetch_times:
                fh.write("%.3f\n" % t)

    # ── Teardown ────────────────────────────────────────────────────────────
    cwnd_monitor.terminate()
    qmon.terminate()
    ping_proc.terminate()
    for p in iperf_procs + webserver_procs:
        p.terminate()
    net.stop()
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()

if __name__ == "__main__":
    bufferbloat()
