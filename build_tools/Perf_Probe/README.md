# Perf Probe

Measures the game's frame times without a window, on a fixed walk: through the town, then through the densest wood, then across each sown field (its crop as a new game finds it, or as the save has it). Use it before and after a change that could cost time (new things drawn on the map, a new effect, something worked out per frame) and compare.

```bash
py build_tools/Perf_Probe/perf_probe.py                          # clear midday, starting zoom
py build_tools/Perf_Probe/perf_probe.py --hour 22 --zoom 1.0 --wet   # the heavy case
py build_tools/Perf_Probe/perf_probe.py --spikes 25              # what each frame over 25 ms did
py build_tools/Perf_Probe/perf_probe.py --profile walk.prof      # cProfile of the whole walk
py build_tools/Perf_Probe/perf_probe.py --zooms                  # first frame at each zoom level
py build_tools/Perf_Probe/perf_probe.py --save 1                 # from save slot 1 instead of a new game
```

## Reading it

Each stretch of the walk prints its median, 95th percentile and slowest frame, and how many frames took over 33 ms (below 30 fps). The median is the steady cost; the maximum shows stutters. Garbage collections are listed with their longest pause.

`--spikes MS` profiles every frame, which makes them all slower: read it for *what* a slow frame did, not for its time. Two spikes are the probe's own: the first frame, and the ones where the walk jumps from the town to the wood and on to the fields, each drawing ground the player has not walked to.

To look into a `--profile` file:

```bash
py -c "import pstats; pstats.Stats('walk.prof').sort_stats('tottime').print_stats(30)"
```

## Measured (Oct 2026, on the development PC)

| Case | Before the performance work | After |
|---|---|---|
| Clear midday, starting zoom, median | 6.5–7.5 ms | 3.6–4.5 ms |
| Night, rain, fog, wet ground, zoom 1.0, median | 10.5–12.3 ms | 6.7–7.4 ms |
| First frame of a game | 110 ms | (made while loading) |
| First frame at a new zoom level (hidden Ctrl levels included) | 35–85 ms | 3–5 ms |
| Puddles placed as rain sets in | 8 ms an update, 4 updates | ≤ 1.5 ms an update |
| A townsperson's new route | 20–40 ms in one frame | ≤ 2 ms a frame |

## Imitating a slow PC

The development PC is several times faster per core than a typical office laptop, and Python uses one core. To feel roughly what a slow machine sees, cap the CPU's speed for a while:

1. Control Panel → Power Options → *Change plan settings* → *Change advanced power settings*.
2. *Processor power management* → *Maximum processor state*: set it to 30 % (on battery and plugged in).
3. Run the probe or the game, then set it back to 100 %.

Windows then holds the CPU at that share of its top speed, so the frame times grow about in proportion (this is a rough stand-in: a slow laptop also has less cache and slower memory).

What the probe does not measure: the window's presentation (`pygame.display.flip`, and the GPU scaling of a `SCALED` window), and sound. The FPS in the debug overlay of the real game includes those.
