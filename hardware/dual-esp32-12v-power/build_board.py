#!/usr/bin/env python3
"""
Programmatically builds dual_esp32_12v_power.kicad_pcb using pcbnew's Python API.

Board: single 12V DC input -> reverse-polarity diode + PTC fuse + TVS protection ->
shared V12 bus -> two independent LM2596-5.0 (TO-220-5, fixed 5V) buck channels,
each with its own EN switch, output PTC fuse, power-good LED and 2-pin 5V/GND
header, for powering two ESP32-S3-1.69 dev boards independently from one input.

Routing is F.Cu point-to-point traces (arbitrary angle - DRC only cares about
clearance, not 45/90deg convention) with a GND copper pour on B.Cu. Layout
offsets were hand-derived so nets do not cross; verified with check_board.py.
"""
import os
import pcbnew

FP_ROOT = "/usr/share/kicad/footprints"
MM = pcbnew.FromMM
def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))

board = pcbnew.BOARD()

# ---------------------------------------------------------------- net table
NET_NAMES = [
    "GND",
    "VIN_RAW", "VIN_FUSED", "V12",
    "EN_A", "SWA_5V", "V5A_PRE", "V5A_OUT", "LEDA_MID",
    "EN_B", "SWB_5V", "V5B_PRE", "V5B_OUT", "LEDB_MID",
    "PWRLED_MID",
]
nets = {}
for n in NET_NAMES:
    ni = pcbnew.NETINFO_ITEM(board, n)
    board.Add(ni)
    nets[n] = ni

def pad_net(fp, num, netname):
    pad = fp.FindPadByNumber(str(num))
    if pad is None:
        raise RuntimeError(f"{fp.GetReference()}: no pad '{num}'")
    pad.SetNet(nets[netname])

def place(lib, name, ref, x, y, rot=0):
    fp = pcbnew.FootprintLoad(f"{FP_ROOT}/{lib}.pretty", name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {lib}:{name}")
    fp.SetReference(ref)
    fp.SetPosition(V(x, y))
    if rot:
        fp.SetOrientationDegrees(rot)
    board.Add(fp)
    fp.Reference().SetVisible(True)
    fp.Value().SetVisible(False)
    return fp

def pad_xy(fp, num):
    p = fp.FindPadByNumber(str(num)).GetPosition()
    return p.x, p.y  # internal units (nm)

# ================================================================== ROUTING
POWER_W = 1.0
BUS_W = 1.2
SIGNAL_W = 0.4

def seg(net, p1, p2, width_mm):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(int(p1[0]), int(p1[1])))
    t.SetEnd(pcbnew.VECTOR2I(int(p2[0]), int(p2[1])))
    t.SetWidth(MM(width_mm))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(nets[net])
    board.Add(t)

def route(net, pts, width_mm):
    """pts: list of (x,y) in internal units. Connect consecutively."""
    for i in range(len(pts) - 1):
        seg(net, pts[i], pts[i + 1], width_mm)

def P(fp, num):
    return pad_xy(fp, num)

def OFF(base_xy, dx_mm, dy_mm):
    return (base_xy[0] + MM(dx_mm), base_xy[1] + MM(dy_mm))

# ============================================================= INPUT SECTION
# Ordered left-to-right in strict electrical order so nothing needs to route
# backwards over an already-placed net: J1 -> {D_TVS, C_IN0} spurs -> F_IN ->
# D_REV -> {R_PWR/LED_PWR, V12 bus} - i.e. VIN_RAW spurs sit BEFORE the fuse,
# never after it.
J1    = place("Connector_BarrelJack", "BarrelJack_CUI_PJ-102AH_Horizontal", "J1", 20, 14)
D_TVS = place("Diode_THT", "D_DO-15_P10.16mm_Horizontal", "D1", 45, 14, rot=90)
C_IN0 = place("Capacitor_THT", "C_Disc_D10.0mm_W2.5mm_P5.00mm", "C1", 65, 14, rot=90)
F_IN  = place("Fuse", "Fuse_Bourns_MF-RG400", "F1", 85, 14)
D_REV = place("Diode_THT", "D_DO-201AD_P12.70mm_Horizontal", "D2", 105, 14)
LED_PWR = place("LED_THT", "LED_D3.0mm_Horizontal_O6.35mm_Z2.0mm", "LED1", 140, 10)
R_PWR   = place("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "R1", 140, 20, rot=90)

pad_net(J1, 1, "GND")
pad_net(J1, 3, "VIN_RAW")
pad_net(F_IN, 1, "VIN_RAW")
pad_net(F_IN, 2, "VIN_FUSED")
pad_net(D_TVS, 1, "VIN_RAW")
pad_net(D_TVS, 2, "GND")
pad_net(D_REV, 1, "VIN_FUSED")
pad_net(D_REV, 2, "V12")
pad_net(C_IN0, 1, "VIN_RAW")
pad_net(C_IN0, 2, "GND")
pad_net(R_PWR, 1, "V12")
pad_net(R_PWR, 2, "PWRLED_MID")
pad_net(LED_PWR, 1, "PWRLED_MID")
pad_net(LED_PWR, 2, "GND")

route("VIN_RAW", [P(J1, 3), P(D_TVS, 1)], BUS_W)
route("VIN_RAW", [P(D_TVS, 1), P(C_IN0, 1)], BUS_W)
route("VIN_RAW", [P(C_IN0, 1), P(F_IN, 1)], BUS_W)
route("VIN_FUSED", [P(F_IN, 2), P(D_REV, 1)], BUS_W)
route("V12", [P(D_REV, 2), P(R_PWR, 1)], SIGNAL_W)
route("PWRLED_MID", [P(R_PWR, 2), P(LED_PWR, 1)], SIGNAL_W)

# =============================================================== CHANNELS ==
# Relative layout (mm) around U's pin-1 position (Ubase). Hand-verified to
# avoid same-layer crossings - see design notes above.
#   BUS_Y = -16      shared V12 bus row (CIN, REN sit on it)
#   DC    = (+1.7,-8)      catch diode, between bus and U
#   U     = (0,0)          TO-220-5: pin1 V12,pin2 SW5,pin3 GND,pin4 PRE,pin5 EN
#   SW    = (+20,0)        on/off switch, same row as U
#   L     = (0,+16)         inductor: pin1 SW5 (under U.2), pin2 PRE
#   COUT  = (0,+32)         output cap, PRE
#   FOUT  = (+15.24,+32)    output fuse: pin1 PRE, pin2 OUT
#   RLED  = (+20.34,+48)    LED series resistor: pin1 OUT, pin2 LEDMID
#   J     = (+20.34,+64)    output header: pin1 OUT, pin2 GND
#   LED   = (+27.96,+64)    indicator LED: pin1(anode) LEDMID, pin2(cathode) GND

def build_channel(tag, ubx, uby):
    EN, SW5, PRE, OUT, LMID = f"EN_{tag}", f"SW{tag}_5V", f"V5{tag}_PRE", f"V5{tag}_OUT", f"LED{tag}_MID"

    U    = place("Package_TO_SOT_THT", "TO-220-5_Vertical", f"U{tag}", ubx, uby)
    CIN  = place("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", f"C{tag}1", ubx - 20, uby - 16, rot=90)
    REN  = place("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", f"R{tag}1", ubx + 20, uby - 16, rot=270)
    DC   = place("Diode_THT", "D_DO-201AD_P12.70mm_Horizontal", f"D{tag}1", ubx + 4, uby - 12)
    SW   = place("Button_Switch_THT", "SW_Slide_SPDT_Straight_CK_OS102011MS2Q", f"SW{tag}", ubx + 20, uby)
    L    = place("Inductor_THT", "L_Axial_L11.0mm_D4.5mm_P15.24mm_Horizontal_Fastron_MECC", f"L{tag}", ubx, uby + 16)
    COUT = place("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", f"C{tag}2", ubx, uby + 32)
    FOUT = place("Fuse", "Fuse_Bourns_MF-RHT050", f"F{tag}1", ubx + 15.24, uby + 32)
    RLED = place("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", f"R{tag}2", ubx + 20.34, uby + 48)
    J    = place("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", f"J{tag}", ubx + 20.34, uby + 64, rot=90)
    LED  = place("LED_THT", "LED_D3.0mm_Horizontal_O6.35mm_Z2.0mm", f"LED{tag}", ubx + 27.96, uby + 64)

    pad_net(U, 1, "V12"); pad_net(U, 2, SW5); pad_net(U, 3, "GND"); pad_net(U, 4, PRE); pad_net(U, 5, EN)
    pad_net(CIN, 1, "V12"); pad_net(CIN, 2, "GND")
    pad_net(REN, 1, "V12"); pad_net(REN, 2, EN)
    pad_net(DC, 1, SW5); pad_net(DC, 2, "GND")
    pad_net(SW, 1, EN); pad_net(SW, 2, "GND")   # pad 3 (other throw) left NC
    pad_net(L, 1, SW5); pad_net(L, 2, PRE)
    pad_net(COUT, 1, PRE); pad_net(COUT, 2, "GND")
    pad_net(FOUT, 1, PRE); pad_net(FOUT, 2, OUT)
    pad_net(RLED, 1, OUT); pad_net(RLED, 2, LMID)
    pad_net(J, 1, OUT); pad_net(J, 2, "GND")
    pad_net(LED, 1, LMID); pad_net(LED, 2, "GND")

    # --- V12: drop from the shared bus row (uby-16, where CIN/REN already sit) down to U.1 ---
    bus_at_U = (P(U, 1)[0], P(CIN, 1)[1])  # (ubx, uby-16): point on bus row directly above U.1
    route("V12", [bus_at_U, P(U, 1)], POWER_W)

    # --- SW5: U.2 up to DC (freewheel diode), and down to L.1 ---
    route(SW5, [P(U, 2), P(DC, 1)], POWER_W)
    route(SW5, [P(U, 2), P(L, 1)], POWER_W)

    # --- PRE: U.4 -> (detour clear of U.5) -> L.2 -> {COUT.1, FOUT.1} ---
    u4 = P(U, 4)
    pre_detour = (u4[0], u4[1] + MM(6))  # drop straight down, clear of U.5 before heading to L.2
    route(PRE, [u4, pre_detour], POWER_W)
    route(PRE, [pre_detour, P(L, 2)], POWER_W)
    route(PRE, [P(L, 2), P(COUT, 1)], POWER_W)
    route(PRE, [P(L, 2), P(FOUT, 1)], POWER_W)

    # --- EN: REN.2 -> U.5 -> SW.1 ---
    route(EN, [P(REN, 2), P(U, 5)], SIGNAL_W)
    route(EN, [P(U, 5), P(SW, 1)], SIGNAL_W)

    # --- OUT: FOUT.2 -> RLED.1 -> J.1 ---
    route(OUT, [P(FOUT, 2), P(RLED, 1)], POWER_W)
    route(OUT, [P(RLED, 1), P(J, 1)], POWER_W)

    # --- LEDMID: RLED.2 -> LED.1 ---
    route(LMID, [P(RLED, 2), P(LED, 1)], SIGNAL_W)

    return dict(U=U, CIN=CIN, REN=REN, DC=DC, SW=SW, L=L, COUT=COUT, FOUT=FOUT, RLED=RLED, J=J, LED=LED)

A = build_channel("A", 50, 50)
B = build_channel("B", 150, 50)

# --- shared V12 bus: one straight horizontal run at y=34 through CIN_A, REN_A,
#     the D_REV drop point, CIN_B, REN_B (all exactly on this line), plus the
#     single vertical drop down from D_REV.2 to join it. ---
bus_y = P(A["CIN"], 1)[1]                       # 34mm, same for both channels
drev_drop = (P(D_REV, 2)[0], bus_y)
route("V12", [P(A["REN"], 1), P(A["CIN"], 1)], BUS_W)
route("V12", [P(A["CIN"], 1), drev_drop], BUS_W)
route("V12", [drev_drop, P(B["CIN"], 1)], BUS_W)
route("V12", [P(B["CIN"], 1), P(B["REN"], 1)], BUS_W)
route("V12", [P(D_REV, 2), drev_drop], BUS_W)

# ============================================================== SILKSCREEN ==
def label(text, x, y, size_mm=2.0, thickness_mm=0.3, layer=None, rot=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(V(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(MM(size_mm), MM(size_mm)))
    t.SetTextThickness(MM(thickness_mm))
    t.SetLayer(layer if layer is not None else pcbnew.F_SilkS)
    if rot:
        t.SetTextAngleDegrees(rot)
    board.Add(t)

label("DUAL ESP32-S3 12V POWER BOARD", 5, 4, size_mm=2.5)
label("12V DC IN", 10, 26)
label("+", 15.5, 8, size_mm=2.5)
label("PWR", 132, 8)
for tag, c in (("A", A), ("B", B)):
    jx, jy = pcbnew.ToMM(P(c["J"], 1)[0]), pcbnew.ToMM(P(c["J"], 1)[1])
    label(f"CH-{tag} 5V OUT (pin1=+5V)", jx - 10, jy - 6, size_mm=1.4)
    label("ON", c["SW"] and pcbnew.ToMM(P(c["SW"], 2)[0]) - 2, pcbnew.ToMM(P(c["SW"], 2)[1]) + 4, size_mm=1.0)

# =============================================================== MOUNTING ==
MH = []
for i, (x, y) in enumerate([(8, 8), (192, 8), (8, 122), (192, 122)], start=1):
    MH.append(place("MountingHole", "MountingHole_3.2mm_M3", f"MH{i}", x, y))

# ============================================================ BOARD OUTLINE
x_min, y_min = -2, -2
x_max, y_max = 198, 130
edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetStart(V(x_min, y_min))
edge.SetEnd(V(x_max, y_max))
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetWidth(MM(0.15))
board.Add(edge)

# =================================================================== GND ZONE (bottom copper)
zone = pcbnew.ZONE(board)
zone.SetLayer(pcbnew.B_Cu)
zone.SetNet(nets["GND"])
zone.SetZoneName("GND_POUR_BOTTOM")
margin = 2.0
outline = zone.Outline()
outline.NewOutline()
for (cx, cy) in [(x_min + margin, y_min + margin), (x_max - margin, y_min + margin),
                 (x_max - margin, y_max - margin), (x_min + margin, y_max - margin)]:
    outline.Append(MM(cx), MM(cy))
zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
zone.SetMinThickness(MM(0.2))
board.Add(zone)
# NB: zone is intentionally left unfilled here - pcbnew's ZONE_FILLER segfaults
# in this headless (no wx app) scripting context. kicad-cli computes a fresh
# zone fill itself for gerber/SVG export, so this is not needed here.

# ================================================================ save
OUT_DIR = "/tmp/claude-0/-home-user-oauth/0f1d15c6-a9bb-5fd8-8382-79124ea4582f/scratchpad/pcb"
os.makedirs(OUT_DIR, exist_ok=True)
pcb_path = f"{OUT_DIR}/dual_esp32_12v_power.kicad_pcb"
board.Save(pcb_path)
print("Saved board to", pcb_path)
print("Board size (mm):", x_max - x_min, "x", y_max - y_min)
