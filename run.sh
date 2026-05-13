#!/bin/bash
# Note: Mininet must be run as root.  Invoke with: sudo ./run.sh

set -e
cd "$(dirname "$0")"

time=200
bwnet=1.5
# Each link gets 10 ms of one-way delay → two links → 20 ms one-way → ~40 ms RTT.
# (The assignment states 20 ms min RTT; the two-link path doubles to ~40 ms.
#  See README for details.)
delay=10

iperf_port=5001

for qsize in 20 100; do
    dir=bb-q$qsize

    echo "=== Running experiment: qsize=$qsize, dir=$dir ==="
    sudo mn -c 2>/dev/null || true

    python3 bufferbloat.py \
        --bw-host 1000 \
        --bw-net  $bwnet \
        --delay   $delay \
        --dir     $dir \
        --time    $time \
        --maxq    $qsize \
        --cong    reno

    echo "=== Generating plots for qsize=$qsize ==="

    python3 plot_tcpprobe.py -f $dir/cwnd.txt \
        -o $dir/cwnd-iperf.png -p $iperf_port

    python3 plot_queue.py -f $dir/q.txt \
        -o $dir/q.png

    python3 plot_ping.py -f $dir/ping.txt \
        -o $dir/rtt.png

    # Copy plots to top-level directory with required submission names.
    cp $dir/cwnd-iperf.png cwnd-q${qsize}.png
    cp $dir/q.png          buffer-q${qsize}.png
    cp $dir/rtt.png        rtt-q${qsize}.png

    echo "=== Fetch time summary for qsize=$qsize ==="
    cat $dir/fetch_times.txt 2>/dev/null || echo "(no fetch data)"
done

echo ""
echo "=== All done. Deliverable plots: ==="
ls -1 buffer-q*.png cwnd-q*.png rtt-q*.png 2>/dev/null
