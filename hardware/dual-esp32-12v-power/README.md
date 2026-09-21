# Dual ESP32-S3-1.69 12V Power Board

A small 2-layer PCB that takes a single 12V DC input and produces two
independently-switched, independently-fused 5V outputs, each sized to run
one ESP32-S3-1.69 round-LCD dev board (the kind shown breadboarded with a
dual-rail buck module in the reference photo for this project).

Board size: 200 x 132 mm, 2-layer (top signal, bottom solid GND pour).

## How it was built

This board was generated entirely from Python code driving KiCad's
`pcbnew` scripting API (`build_board.py`) rather than drawn by hand in the
KiCad GUI - component placement, net assignment, copper routing and the
ground-pour zone are all produced programmatically. `check_board.py` is a
from-scratch geometric verifier (built because this KiCad 7.0 CLI build
has no `pcb drc` subcommand - that landed in KiCad 8) that checks every
net is actually routed and that no two different-net copper features
(traces or pads) violate clearance on the same layer. The final board
passes that check with zero issues. `fill_zone.py` performs the GND zone
fill (KiCad's `ZONE_FILLER` segfaults when run with no display attached,
so this is run once under `xvfb-run`).

**What was not independently verified:** this environment's network
egress blocks every chip-vendor datasheet host (ti.com, diodes.com,
alldatasheet, lcsc, etc.), so the LM2596 pinout/application-circuit and
the PJ-102A jack pin mapping used below are from well-established,
widely-documented reference designs rather than a freshly pulled
datasheet. **Before ordering assembly or populating parts, cross-check
the LM2596 pinout and the ON/OFF pin behavior against your specific
vendor's datasheet.**

## Circuit description

```
12V IN --[TVS]--[PTC fuse]--[reverse-polarity diode]--> V12 (protected 12V rail)
                                                            |
                                        +-------------------+-------------------+
                                        |                                       |
                                  Channel A                               Channel B
                                  (identical)                             (identical)
```

Each channel is an independent **LM2596T-5.0** (TO-220-5, fixed 5V output,
synchronous-ish buck, 3A capable) with the standard minimal application
circuit:

- `CIN` (100uF/25V) on the regulator input
- `L` (33uH) + `D` (1N5822 catch diode) forming the switching node
- `COUT` (220uF/25V) on the regulated 5V output, with the FEEDBACK pin
  wired straight back to it (this is a **fixed**-output part - FEEDBACK
  still has to be tied to VOUT per the standard LM2596 application
  circuit, it just doesn't need a resistor divider)
- An **EN pull-up + slide switch** on the ON/OFF pin: a 10k resistor
  holds ON/OFF high (regulator OFF) by default, and the slide switch
  pulls it to GND to enable the regulator. This means the switch only
  ever carries a couple of mA, not the load current.
- A **500mA-hold PTC fuse** on the regulated output, in series with a
  power-good LED and a 2-pin 2.54mm header (pin 1 = +5V, pin 2 = GND)
  for wiring to the ESP32-S3-1.69 board.

Shared input protection ahead of both channels:

- **TVS diode** (P6KE15A) across the raw input for surge/ESD clamping
- **PTC resettable fuse** (~2A hold) for overall overcurrent/short
  protection
- **Series Schottky diode** (1N5822) for reverse-polarity protection
  (small ~0.3-0.5V drop, irrelevant with 12V in and a switching
  regulator downstream)
- 100nF ceramic + a green power-good LED

## Why two separate regulators instead of one shared 5V rail

Each ESP32-S3 board gets its own regulator, inductor, output cap, fuse
and switch, so the two channels are electrically independent: a short or
brownout on one ESP32 board can't drag down or reset the other, and each
board can be power-cycled independently with its own slide switch.

## IMPORTANT - verify before you power up an ESP32-S3-1.69 board

The two channels output a fixed **5V**, matching a typical 5V/VIN pin
broken out on ESP32 dev boards (this is what the loose wires in the
reference photo appear to be going into). **Do not** wire this into a
LiPo/battery-only JST-PH connector on your specific board - those are
usually a raw ~3.7-4.2V battery input feeding an onboard charge IC, and
5V there can damage the board. Check your exact ESP32-S3-1.69 variant's
silkscreen/schematic for which pin actually wants 5V before connecting.

## Files

- `dual_esp32_12v_power.kicad_pcb` / `.kicad_pro` - the KiCad 7 project
- `build_board.py` - regenerates the `.kicad_pcb` from scratch
- `check_board.py` - the geometric connectivity/clearance verifier
- `fill_zone.py` - fills the bottom-layer GND zone (run under `xvfb-run`)
- `BOM.csv` - full bill of materials with suggested part numbers
- `gerbers/` - Gerber X2, Excellon drill (PTH/NPTH separated), and a
  CSV placement (position) file
- `dual_esp32_12v_power_gerbers.zip` - the `gerbers/` folder pre-zipped,
  ready to drag-and-drop into PCBWay's instant-quote uploader
- `docs/preview_top.png`, `docs/preview_bottom.png` - rendered top
  copper/silkscreen and bottom copper (GND pour) previews

## Ordering from PCBWay

1. Go to PCBWay's instant quote / PCB Prototype page and upload
   `dual_esp32_12v_power_gerbers.zip` directly - PCBWay auto-reads the
   board outline and layer count from the Gerber set.
2. Suggested options: 2 layers, 1.6mm thickness, 1oz copper, any solder
   mask/silkscreen color, HASL (lead-free) or ENIG finish - all default
   PCBWay options work fine for this design (no fine-pitch/impedance
   requirements).
3. If you want PCBWay to also assemble it (PCBA), upload `BOM.csv` and
   `gerbers/dual_esp32_12v_power-all-pos.csv` (placement file) - you'll
   likely need to fill in / confirm exact distributor part numbers for
   the electrolytic caps, inductor and switch since those were specified
   generically here.
4. Otherwise, hand-solder it yourself - every part on this board is
   through-hole by design.

## Regenerating the board

```
python3 build_board.py          # rebuild dual_esp32_12v_power.kicad_pcb from scratch
python3 check_board.py          # verify: 0 issues expected
xvfb-run -a python3 fill_zone.py  # fill the GND zone (needed before Gerber export)
kicad-cli pcb export gerbers -o gerbers/ dual_esp32_12v_power.kicad_pcb
kicad-cli pcb export drill -o gerbers/ --format excellon --drill-origin absolute --excellon-separate-th dual_esp32_12v_power.kicad_pcb
kicad-cli pcb export pos -o gerbers/dual_esp32_12v_power-all-pos.csv --format csv --units mm --side both dual_esp32_12v_power.kicad_pcb
```

Requires `kicad` (>=7.0, for `pcbnew`/`kicad-cli`) and `xvfb` installed.
