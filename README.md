# hybrid-eevdf-latency-analysis

I wanted to know what actually happens to a latency-sensitive task on an
Intel hybrid CPU when some batch job is pegging the P-cores. Not benchmark
scores - wakeup latency, the number that decides whether your editor feels
like it's glued to the desk.

So I put together a small test rig on an i7-13650HX (6 P-cores / 12 threads
at 0-11, 6 E-cores at 12-17, kernel 7.1.8-arch1-3), ran `sysbench cpu` on the
P-cores, and poked it with `schbench`. Two setups, 30 runs each, 15 seconds
per run:

- **Exp A (floating):** schbench allowed to use all 18 CPUs (0-17).
- **Exp B (pinned):** schbench locked to the 6 E-cores (12-17).

## What I found

| | Exp A floating | Exp B pinned E-pool |
|---|---|---|
| typical wakeup (p50) | 43 us | 44 us |
| median of the 30 per-run p99.9s | 162 us | 701 us |
| worst run | 2836 us | 2852 us |
| runs with p99.9 over 1 ms | 5 / 30 | 4 / 30 |

In plain English:

- Normal wakeups are fine either way (~43 us). The entire problem is the
  tail.
- Floating usually wins. The task occasionally gets a P-core, so the typical
  bad run is around 162 us. But sometimes the scheduler messes up and you eat
  a 2.8 ms stall out of nowhere.
- Pinning to the E-cores makes the typical tail about 4x worse (701 us).
  Everything is now sharing 6 slow cores, and the E-pool has no slack.
- Pinning is not a magic fix for the worst case, either. 4 of 30 pinned runs
  still went over 1 ms, and one hit 2852 us. It changes where the tail lives,
  it doesn't delete it.

The 2.8 ms stalls have a boring explanation once you look at the traces:
they're wakeup collisions. Two threads get woken onto the same E-core that
was idle a couple of microseconds earlier. One runs a request, the other sits
and waits. I caught one where two workers were placed on CPU 15 four
microseconds apart, and the loser waited 2812 us. There are also windows
where a thread is waiting while another E-core sits idle, which is the
scheduler being less work-conserving than you'd hope.

One more thing from the traces: with the P-cores pinned by sysbench, the
wakeup path stopped using them for schbench entirely (0 of 702 wakeups in the
floating run). "Floating" mostly means "E-pool by default, with a rare
P-core visit when the load balancer bothers."

Long version with the per-run numbers and the trace breakdown:
[TECHNICAL_REPORT.md](TECHNICAL_REPORT.md).

## Paper

The full write-up is [paper/Tail_Wakeup_Latency_Hybrid_CPUs.pdf](paper/Tail_Wakeup_Latency_Hybrid_CPUs.pdf)
(DOCX next to it, generator in `paper/build_paper.py`, figures in
`paper/make_figures.py`). It is archived on Zenodo:
[10.5281/zenodo.23674242](https://doi.org/10.5281/zenodo.23674242).

    @misc{vattikuti2026tailwakeup,
      title        = {Tail Wakeup Latency on Intel Hybrid CPUs: Evaluating Linux
                      CPU Placement and Wakeup Placement Under Mixed Load},
      author       = {Shreyas Vattikuti},
      year         = {2026},
      month        = {oct},
      doi          = {10.5281/zenodo.23674242},
      url          = {https://zenodo.org/records/23674242}
    }

## How to run it

Needs Linux on a hybrid CPU, root (for perf), plus `schbench`, `sysbench`,
and `perf`. Put `schbench` in your PATH or drop the binary next to the script.

    sudo ./phase2/run_rigorous_validation.sh

That does 30 iterations of both experiments (5 s warmup, 15 s measurement,
2 s cooldown) and drops logs, perf traces, and a CSV into a fresh
`phase2/rigorous_results_<timestamp>/` directory.

The CPU ranges are hardcoded for this machine: 0-11 are P-cores with SMT,
12-17 are E-cores. Change the `taskset` masks in the script if your core
numbering is different.

## Where stuff is

- The 30-run rig is `phase2/run_rigorous_validation.sh`. Smaller single-shot
  scripts from earlier passes live in `phase1/`, `phase1.1/`, and `phase1.2/`.
- Raw logs and `.perf` files from the 30-run batch:
  `phase2/rigorous_results_20261019_212023/`.
- Clean N=30 table: `analysis/distribution_data.csv`. The CSV produced by the
  original run had duplicated/wrapped rows, so `analysis/parse_results.py`
  rebuilds it from the logs. Summary stats go to `analysis/SUMMARY_STATS.txt`.
- Trace parser used for the collision analysis:
  `analysis/analyze_sched_trace.py`. It was run against the 30 s capture in
  `phase1.1/phase1_1_results_20261016_042329/perf_switch_events.raw`.

## Caveats

- One machine, one kernel. Case study, not a law of nature.
- The N=30 batch ran under the `powersave` governor inside `perf record`.
  Tracing overhead can bite the pinned setup harder because it has fewer
  cores to hide in. An earlier 10-run batch without tracing had the opposite
  ordering, so don't read the 162 vs 701 as a universal constant.
- Each run has 120 wakeup samples, so p99.9 is basically the worst sample or
  two. Useful as a tail indicator, not a precise percentile.
- The ~1,000,000 us "request latency" in the logs is schbench's `-s 1000000`
  sleep (1 second). Ignore it.
