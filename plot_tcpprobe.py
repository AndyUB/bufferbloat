'''
Plot cwnd timeseries from ss-based monitoring output.
Replaces tcp_probe (removed in Linux 4.16+) with ss -i polling.
File format: unix_timestamp,cwnd_in_segments
'''
from helper import *
import plot_defaults

from matplotlib.ticker import MaxNLocator
from pylab import figure

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--port', dest="port", default='5001',
                    help="Port filter (kept for CLI compatibility with run.sh)")
parser.add_argument('-f', dest="files", nargs='+', required=True)
parser.add_argument('-o', '--out', dest="out", default=None)

args = parser.parse_args()

def parse_cwnd_file(fname):
    times = []
    cwnds = []
    try:
        for line in open(fname):
            line = line.strip()
            if not line or ',' not in line:
                continue
            parts = line.split(',')
            if len(parts) < 2:
                continue
            try:
                t = float(parts[0])
                cwnd_kb = int(parts[1]) * 1448 / 1024.0
                times.append(t)
                cwnds.append(cwnd_kb)
            except ValueError:
                continue
    except FileNotFoundError:
        print('Warning: %s not found' % fname)
    return times, cwnds

m.rc('figure', figsize=(16, 6))
fig = figure()
ax = fig.add_subplot(111)

for f in args.files:
    times, cwnds = parse_cwnd_file(f)
    if times:
        t0 = times[0]
        times = [t - t0 for t in times]
        ax.plot(times, cwnds, lw=2)

ax.grid(True)
ax.set_xlabel("Seconds")
ax.set_ylabel("cwnd (KB)")
ax.set_title("TCP congestion window (cwnd) timeseries")
ax.xaxis.set_major_locator(MaxNLocator(4))

if args.out:
    print('saving to', args.out)
    plt.savefig(args.out)
else:
    plt.show()
