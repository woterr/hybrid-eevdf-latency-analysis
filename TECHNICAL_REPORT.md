# Technical report: hybrid CPU wakeup latency under P-core load

## 1. What was tested

Hardware and software:

- Intel Core i7-13650HX. On this machine CPUs 0-11 are the 6 P-cores with SMT (12 threads), and CPUs 12-17 are the 6 E-cores.
- Kernel 7.1.8-arch1-3, `powersave` governor during the 30-run batch (recorded in `environment_info.txt`).
- Background load: `sysbench cpu --threads=12 --cpu-max-prime=50000000`, pinned to the P-cores (0-11).
- Probe: `schbench -m 2 -t 4 -r 15 -s 1000000`. That is 2 message threads, 4 workers, 15 s runtime, 1 s sleep between requests. 5 s sysbench warmup before each run, 2 s cooldown after.
- Exp A (floating): schbench affinity 0-17.
- Exp B (pinned): schbench affinity 12-17.
- 30 iterations, A then B in each iteration. Every run was recorded with
  `perf record -e sched:sched_switch,sched:sched_wakeup,sched:sched_migrate_task`.

The number that matters is schbench's **Wakeup Latencies** block. The
**Request Latencies** block is all ~1,004,544 us because of the 1 s sleep, not
because anything is broken.

Each 15 s run produces 120 wakeup samples. That means p99.9 is one or two
samples: read a per-run p99.9 as "the worst thing that happened on this run,"
not as a smooth percentile. The N=30 comparison is a comparison of 30 of those
worst-case values per setup.

Data hygiene: the CSV committed by the original run has three wrapped/
duplicated lines per run (`1,723` / `723,174` / `174`). The clean table in
`analysis/distribution_data.csv` is rebuilt from the per-run logs by
`analysis/parse_results.py`. All numbers in this report come from the logs.

## 2. The N=30 numbers

Summary, wakeup latency in microseconds:

| Metric | Exp A floating | Exp B pinned E-pool |
|---|---|---|
| p50, median across runs | 43 | 44 |
| p90, median across runs | 71 | 64.5 |
| p99, median across runs | 137 | 139 |
| p99.9, median across runs | **162** | **701** |
| p99.9, min / max | 79 / 2836 | 119 / 2852 |
| runs with p99.9 > 250 us | 13 / 30 | 19 / 30 |
| runs with p99.9 > 500 us | 12 / 30 | 18 / 30 |
| runs with p99.9 > 1 ms | 5 / 30 | 4 / 30 |
| runs with p99.9 > 2 ms | 1 / 30 | 2 / 30 |

Per-run p99.9 in the same order they were collected:

| Run | Exp A | Exp B | Run | Exp A | Exp B |
|---|---|---|---|---|---|
| 1 | 723 | 174 | 16 | 567 | 120 |
| 2 | 553 | 168 | 17 | 1310 | 703 |
| 3 | 136 | 141 | 18 | 190 | 146 |
| 4 | 899 | 881 | 19 | 137 | 905 |
| 5 | 143 | 665 | 20 | 141 | 1234 |
| 6 | 123 | 1130 | 21 | 1130 | 931 |
| 7 | 1282 | 2348 | 22 | 789 | 193 |
| 8 | 143 | 699 | 23 | 120 | 753 |
| 9 | 140 | 135 | 24 | 79 | 715 |
| 10 | 151 | 138 | 25 | 123 | 797 |
| 11 | 173 | 119 | 26 | 134 | 460 |
| 12 | 2836 | 737 | 27 | 116 | 799 |
| 13 | 853 | 869 | 28 | 80 | 641 |
| 14 | 1626 | 156 | 29 | 138 | 137 |
| 15 | 747 | 2852 | 30 | 252 | 899 |

What the table says:

- Normal wakeups are identical: ~43 us p50 in both setups. The whole
  difference is in the tail.
- Exp A is mostly low (median p99.9 162 us) with a few runs falling off a
  cliff: 5 runs over 1 ms, worst 2836 us.
- Exp B moved the whole tail up: median 701 us, roughly 4x worse than A, and
  more runs in the 250-1000 us range (18 runs over 500 us vs 12 for A).
- Exp B did not remove the cliffs. It had 4 runs over 1 ms and 2 runs over
  2 ms (2348 and 2852 us), so its worst case was slightly *more* frequent
  than A's. Run 7 in Exp B is not a single spike either: the 99.0th percentile
  is 2276 us with 10 samples, meaning about ten wakeups landed around 2.3 ms.
  Pinning changes where the tail lives, it does not delete it.

An earlier 10-run batch (phase 1.2, no perf tracing) had the opposite tail
ordering: median p99.9 was ~103 us pinned vs ~130 us floating, and only
floating had a >1 ms run. The obvious difference is that the N=30 batch wraps
every run in `perf record`, and the pinned setup has fewer cores to absorb
that overhead. Treat the two batches as evidence that this workload is close
to a tipping point, not as a clean ranking.

## 3. What the scheduler traces show

### 3.1 Wakeup placement follows the load, not the task

Wakeup targets for schbench, from the phase 1 captures (single runs,
`stat_wakeup_targets.txt`):

| Setup | Wakeups targeting P-cores | Wakeups targeting E-cores |
|---|---|---|
| Idle baseline | 541 / 730 | 189 / 730 |
| Exp A, P-cores loaded | 0 / 702 | 702 / 702 |
| Exp B, P-cores loaded | 0 / 719 | 719 / 719 |

With the P-cores pegged, the wakeup path stops putting schbench on them at
all. Every wakeup lands on the E-pool, even in the "floating" setup. Floating
still lets the load balancer move a thread across the boundary occasionally:
the phase 1 floating run had 1 E→P migration and 1 P→E migration out of 119
schbench migrations; everything else was E→E churn. The pinned run had 70
migrations, all within the E-pool. So "floating" in this test is really
"E-pool by default, P-core as a rare bonus."

That rare P-core visit is the most plausible reason floating has the better
typical tail. It is also unstable: the same placement machinery that lets a
thread cross to a P-core is what occasionally produces the multi-millisecond
collisions below.

### 3.2 The 2.8 ms stalls are wakeup collisions

Reconstructed from the 30 s phase 1.1 trace of the floating setup
(`analysis/analyze_sched_trace.py`, 707 matched wakeup→first-run pairs):

- p50 2.0 us, p90 15.0 us, p99 188.5 us, p99.9 2807 us, max 2812 us.
- 61 of 707 wakeups (8.6%) landed on a CPU that already had other runnable
  work. In 54 of those the target CPU was actively running another task; in 7
  it had another wakee queued but not yet switched in.
- All 9 slow wakeups (>=100 us) had a target collision. 4 of the 9 are
  placement races: the target looked idle in the switch stream, but another
  task had already been woken to the same CPU and had not run yet.
- 13 of 707 wakeups (1.8%) picked a busy E-core while a different E-core was
  sitting idle.
- The runqueue model finds 602 short windows where a runnable schbench thread
  waited while at least one E-core was idle, 10.6 ms in total over the 30 s
  trace. The longest is 3.76 ms, with a thread queued on CPU 17 and CPU 14
  idle.

The worst event is the clean example. At t=119.828122 a worker was woken and
placed on CPU 15, which was idle. At t=119.828126 - four microseconds later -
a second worker was also placed on CPU 15, still idle as far as the wakeup
path could see. The first worker then ran a full request on CPU 15; the second
worker sat in the runqueue for 2812 us before it got the CPU. Same story for
the 2805 us event on CPU 17. This is not an E-core being slow. It is two
wakeups racing for the same just-idle core, with the loser paying for the
winner's whole time slice.

Two things make it worse on a hybrid chip:

1. The P-cores are excluded by placement while loaded, so 6+ schbench threads
   and whatever kernel work appears all compete for 6 E-cores.
2. Idle E-cores are not consistently used. In 13 of 707 wakeups the scheduler
   chose an occupied E-core while another E-core was idle, and the mismatch
   windows show runnable threads waiting with idle cores nearby for up to
   3.76 ms. Work-conserving on paper, not always in practice at this
   resolution.

The phase 1.1 schbench log for the same run reports a p99.9 of 837 us and a
max of 836 us. The trace sees larger stalls (2812 us) because it timestamps
every `sched_wakeup` → first `sched_switch` pair, including wakeups schbench
does not sample. Both views agree on the mechanism: the tail is made of
collisions, not of general slowness.

## 4. Caveats

- One machine, one kernel (6.6+ EEVDF scheduler), one governor setting. This
  is a case study, not a universal rule.
- The N=30 batch ran under `powersave` and inside `perf record`. Both can add
  tail latency, and Exp B is more exposed to it because it has fewer cores.
  The phase 1.1 trace ran under the `performance` governor, so its absolute
  numbers are not directly comparable to the N=30 table.
- p99.9 over 120 samples is a tail indicator, effectively the max.
- The runqueue reconstruction is an approximation (wakeups, switches, and
  migrations only). It is good enough to show collisions and idle-core
  mismatches, but it is not `perf sched`.
- Absolute migration counts differ between phase 1 (10-15 s captures) and the
  phase 1.1 30 s trace; compare the pattern, not the exact counts.

## 5. Things worth trying next

- Rerun N=30 under the `performance` governor and without `perf record`, to
  separate the workload from the measurement overhead.
- Reserve a fixed slice of P-cores for the latency-sensitive thread (cgroup
  cpuset, or uclamp hints) instead of all-or-nothing pinning.
- Check E-core C-state exit latency and IRQ affinity: some of the ~700 us
  pinned tail may not be scheduling at all.
- Longer runs and more samples per run, so p99.9 is an actual percentile.
- Try the same rig on a kernel with a different EEVDF tuning or on a CPU with
  a different P/E layout to see how much of this is Intel-specific.
