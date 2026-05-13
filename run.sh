#!/bin/bash
# Note: Mininet must be run as root.  Invoke with: sudo ./run.sh

set -e
cd "$(dirname "$0")"

# Ensure matplotlib is available under sudo/root.
python3 -c "import matplotlib" 2>/dev/null || pip3 install matplotlib

time=200
bwnet=1.5
# Each link carries 10 ms of one-way netem delay.
# With two links (h1→s0, s0→h2), one-way propagation = 20 ms → min RTT ≈ 40 ms.
# See README Q3 for the RTT derivation.
delay=10

iperf_port=5001

for qsize in 20 100; do
    dir=bb-q$qsize

    echo "=== Cleaning previous Mininet state ==="
    mn -c 2>/dev/null || true

    echo "=== Running experiment: qsize=$qsize, dir=$dir ==="
    python3 bufferbloat.py \
        --bw-host 1000 \
        --bw-net  $bwnet \
        --delay   $delay \
        --dir     $dir \
        --time    $time \
        --maxq    $qsize \
        --cong    reno

    # The experiment dirs are owned by root; make them world-readable for plotting.
    chown -R "$(logname):$(logname)" "$dir" 2>/dev/null || true

    echo "=== Generating plots for qsize=$qsize ==="
    python3 plot_tcpprobe.py -f $dir/cwnd.txt \
        -o $dir/cwnd-iperf.png -p $iperf_port

    python3 plot_queue.py -f $dir/q.txt \
        -o $dir/q.png

    python3 plot_ping.py -f $dir/ping.txt \
        -o $dir/rtt.png

    # Copy to top-level with required submission names.
    cp $dir/cwnd-iperf.png cwnd-q${qsize}.png
    cp $dir/q.png          buffer-q${qsize}.png
    cp $dir/rtt.png        rtt-q${qsize}.png

    echo "=== Fetch time summary for qsize=$qsize ==="
    cat $dir/fetch_times.txt 2>/dev/null || echo "(no fetch data)"
done

echo ""
echo "=== All done. Deliverable plots: ==="
ls -1 buffer-q*.png cwnd-q*.png rtt-q*.png 2>/dev/null
