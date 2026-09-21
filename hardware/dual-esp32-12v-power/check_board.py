#!/usr/bin/env python3
"""
Geometric sanity checker for dual_esp32_12v_power.kicad_pcb, standing in for
`kicad-cli pcb drc` (not available in this KiCad 7.0 CLI build):

1. Every non-GND, non-explicitly-NC pad has at least one track/via endpoint
   touching it (no dangling/unrouted pads).
2. No two F.Cu track segments belonging to DIFFERENT nets pass within
   clearance of each other (would be a short).
3. No F.Cu track segment of one net passes within clearance of a THT pad
   belonging to a DIFFERENT net (also a short, since THT pads have copper
   on every layer).
"""
import pcbnew
from shapely.geometry import LineString, Point

PCB = "/tmp/claude-0/-home-user-oauth/0f1d15c6-a9bb-5fd8-8382-79124ea4582f/scratchpad/pcb/dual_esp32_12v_power.kicad_pcb"
CLEARANCE_MM = 0.2

board = pcbnew.LoadBoard(PCB)
mm = pcbnew.ToMM

# Intentionally-unconnected pads (NC throws, jack switch pin)
IGNORE = {("J1", "2"), ("SWA", "3"), ("SWB", "3")}

# ---- gather pads ----
pads = []  # (ref, num, net, x, y, is_tht)
for fp in board.GetFootprints():
    ref = fp.GetReference()
    for pad in fp.Pads():
        num = pad.GetNumber()
        net = pad.GetNetname()
        pos = pad.GetPosition()
        is_tht = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        pads.append((ref, num, net, mm(pos.x), mm(pos.y), is_tht, pad.GetSizeX() and mm(max(pad.GetSizeX(), pad.GetSizeY()))/2))

# ---- gather F.Cu tracks ----
segs = []  # (net, LineString, width_mm)
for t in board.GetTracks():
    if t.Type() != pcbnew.PCB_TRACE_T:
        continue
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    s, e = t.GetStart(), t.GetEnd()
    segs.append((t.GetNetname(), LineString([(mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))]), mm(t.GetWidth())))

print(f"pads: {len(pads)}   F.Cu segments: {len(segs)}")

# ---- check 1: every non-GND pad (not in IGNORE, not "") has a touching segment ----
print("\n=== Unrouted-pad check ===")
problems = 0
for ref, num, net, x, y, is_tht, rad in pads:
    if net in ("", "GND") or (ref, num) in IGNORE:
        continue
    p = Point(x, y)
    touched = any(seg.distance(p) < 0.15 for (n, seg, w) in segs if n == net)
    if not touched:
        print(f"  UNROUTED: {ref}.{num} (net {net}) at ({x:.2f},{y:.2f})")
        problems += 1
if not problems:
    print("  OK - every non-GND pad has copper touching it")

# ---- check 2: cross-net segment-to-segment clearance ----
print("\n=== Segment-vs-segment short check (different nets) ===")
n = len(segs)
for i in range(n):
    net_i, geom_i, w_i = segs[i]
    for j in range(i + 1, n):
        net_j, geom_j, w_j = segs[j]
        if net_i == net_j:
            continue
        d = geom_i.distance(geom_j)
        needed = w_i / 2 + w_j / 2 + CLEARANCE_MM
        if d < needed:
            print(f"  SHORT RISK: {net_i!r} vs {net_j!r}  dist={d:.3f}mm < needed={needed:.3f}mm")
            print(f"      seg_i={list(geom_i.coords)}  seg_j={list(geom_j.coords)}")
            problems += 1
if problems == 0:
    print("  (checked further below too)")

# ---- check 3: segment-to-foreign-pad clearance ----
print("\n=== Segment-vs-foreign-pad short check ===")
for ref, num, net, x, y, is_tht, rad in pads:
    if net == "":
        continue
    p = Point(x, y)
    for (sn, geom, w) in segs:
        if sn == net or sn == "":
            continue
        d = geom.distance(p)
        needed = (rad or 0.4) + w / 2 + CLEARANCE_MM
        if d < needed:
            print(f"  SHORT RISK: pad {ref}.{num} (net {net}) too close to track net {sn!r}: dist={d:.3f} needed={needed:.3f}")
            problems += 1

print(f"\nTOTAL ISSUES: {problems}")
