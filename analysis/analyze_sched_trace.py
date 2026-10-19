#!/usr/bin/env python3
"""Analyze a `perf script` text dump of scheduler events.

Reconstructs, from sched_wakeup / sched_switch / sched_migrate_task records:

  1. wakeup -> first-run delay for schbench threads
  2. whether the wakeup target CPU was already occupied (a "collision")
  3. how many E-cores were truly idle at wakeup time
  4. intervals where a runnable schbench thread waits while an E-core is idle
  5. schbench migration counts between the P- and E-core domains

The runqueue model is an approximation: a wakeup adds the task to the target
CPU's queue, a switch removes the next task from the queue, and a switch with
prev_state=R leaves the previous task queued. It is good enough to spot
collisions and idle-core mismatches, not a replacement for `perf sched`.

Usage: python3 analysis/analyze_sched_trace.py <perf_script_output>
"""
import re
import sys
from collections import Counter, defaultdict

LINE_RE = re.compile(
    r"^\s*(?P<comm>.+?)\s+(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+"
    r"(?P<ts>\d+\.\d+):\s+sched:sched_(?P<ev>wakeup|switch|migrate_task):\s+(?P<body>.*)$"
)
KV_RE = re.compile(r"(\w+)=(\S+)")
P_CORES = set(range(0, 12))
E_CORES = set(range(12, 18))


def is_idle(comm):
    return comm is None or comm.startswith("swapper")


def pctl(vals, p):
    vals = sorted(vals)
    if not vals:
        return float("nan")
    k = (len(vals) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def main(path):
    running = {}
    queues = defaultdict(set)
    pid_comm = {}
    pending = defaultdict(list)

    delays = []
    slow = []
    wake_count = 0
    occupied = 0
    occupied_running = 0
    wake_on_busy_while_idle_other = 0
    migrations = Counter()

    mismatch_open = None
    mismatch_intervals = []

    def check_idle_mismatch(ts):
        nonlocal mismatch_open
        runnable = [p for pids in queues.values() for p in pids if pid_comm.get(p) == "schbench"]
        idle_e = [c for c in E_CORES if is_idle(running.get(c)) and not queues.get(c)]
        if runnable and idle_e:
            if mismatch_open is None:
                mismatch_open = (ts, list(runnable), list(idle_e))
        elif mismatch_open is not None:
            mismatch_intervals.append((mismatch_open[0], ts, mismatch_open[1], mismatch_open[2]))
            mismatch_open = None

    for line in open(path, errors="replace"):
        m = LINE_RE.match(line)
        if not m:
            continue
        ev = m.group("ev")
        ts = float(m.group("ts"))
        cpu = int(m.group("cpu"))
        b = dict(KV_RE.findall(m.group("body")))

        if ev == "wakeup":
            comm = b.get("comm", "")
            pid = int(b.get("pid", -1))
            tgt = int(b.get("target_cpu", -1))
            pid_comm[pid] = comm
            if comm == "schbench":
                wake_count += 1
                tgt_idle = is_idle(running.get(tgt)) and not (queues.get(tgt, set()) - {pid})
                if not tgt_idle:
                    occupied += 1
                if not is_idle(running.get(tgt)):
                    occupied_running += 1
                other_idle = [
                    c for c in E_CORES
                    if c != tgt and is_idle(running.get(c)) and not queues.get(c)
                ]
                if not tgt_idle and other_idle:
                    wake_on_busy_while_idle_other += 1
                pending[pid].append({
                    "ts": ts, "tgt": tgt, "tgt_idle": tgt_idle,
                    "other_idle": other_idle,
                    "race": is_idle(running.get(tgt)) and bool(queues.get(tgt, set()) - {pid}),
                })
            queues[tgt].add(pid)
            check_idle_mismatch(ts)

        elif ev == "switch":
            ppid, pstate = int(b.get("prev_pid", -1)), b.get("prev_state", "?")
            npid, ncomm = int(b.get("next_pid", -1)), b.get("next_comm", "")
            if pstate.startswith("R"):
                queues[cpu].add(ppid)
            else:
                queues[cpu].discard(ppid)
            queues[cpu].discard(npid)
            running[cpu] = ncomm
            if ncomm == "schbench":
                q = pending.get(npid)
                if q:
                    w = q.pop(0)
                    w["delay"] = (ts - w["ts"]) * 1e6
                    w["run_cpu"] = cpu
                    delays.append(w["delay"])
                    if w["delay"] >= 100:
                        slow.append(w)
            check_idle_mismatch(ts)

        elif ev == "migrate_task":
            pid = int(b.get("pid", -1))
            o, d = int(b.get("orig_cpu", -1)), int(b.get("dest_cpu", -1))
            queues[o].discard(pid)
            queues[d].add(pid)
            pid_comm[pid] = b.get("comm", "")
            if pid_comm[pid] == "schbench":
                kind = ("P->E" if o in P_CORES and d in E_CORES else
                        "E->P" if o in E_CORES and d in P_CORES else
                        "within-P" if o in P_CORES and d in P_CORES else
                        "within-E" if o in E_CORES and d in E_CORES else "other")
                migrations[kind] += 1
            check_idle_mismatch(ts)

    print("trace:", path)
    print("schbench wakeups=%d matched=%d slow(>=100us)=%d" % (wake_count, len(delays), len(slow)))
    print("wakeup->first-run delay: p50=%.1f p90=%.1f p99=%.1f p99.9=%.1f max=%.1f us" % (
        pctl(delays, 50), pctl(delays, 90), pctl(delays, 99), pctl(delays, 99.9), max(delays)))
    print("target CPU already occupied at wakeup: %d/%d (%.1f%%)" % (
        occupied, wake_count, 100.0 * occupied / wake_count))
    print("  target CPU was running another task: %d" % occupied_running)
    print("wakeups that picked a busy E-core while another E-core was idle: %d (%.1f%%)" % (
        wake_on_busy_while_idle_other, 100.0 * wake_on_busy_while_idle_other / wake_count))
    print("schbench migrations:", dict(migrations))
    print("slow wakeups with a target collision: %d/%d" % (
        sum(1 for w in slow if not w["tgt_idle"]), len(slow)))
    print("slow wakeups where the target looked idle but had a pending wakee (placement race): %d" % (
        sum(1 for w in slow if w["race"])))
    print("slow wakeups that ran on a different CPU than the target: %d" % (
        sum(1 for w in slow if w.get("run_cpu") != w["tgt"])))
    print("idle-core mismatches: %d intervals, total %.1f ms, longest %.2f ms" % (
        len(mismatch_intervals),
        sum(t - s for s, t, _, _ in mismatch_intervals) * 1000,
        max((t - s for s, t, _, _ in mismatch_intervals), default=0.0) * 1000))
    print("\nslowest wakeups:")
    for w in sorted(slow, key=lambda x: -x["delay"])[:10]:
        print("  %8.1f us target=%2d run=%2d target_idle=%s other_idle_E=%d" % (
            w["delay"], w["tgt"], w["run_cpu"], w["tgt_idle"], len(w["other_idle"])))
    print("\nlongest idle-core mismatches:")
    for s, t, runnable, idle_e in sorted(mismatch_intervals, key=lambda x: -(x[1] - x[0]))[:8]:
        print("  %8.2f ms runnable_pids=%s idle_E=%s" % ((t - s) * 1000, runnable, idle_e))


if __name__ == "__main__":
    main(sys.argv[1])
