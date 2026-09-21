#!/usr/bin/env python3
import pcbnew
PCB = "/tmp/claude-0/-home-user-oauth/0f1d15c6-a9bb-5fd8-8382-79124ea4582f/scratchpad/pcb/dual_esp32_12v_power.kicad_pcb"
board = pcbnew.LoadBoard(PCB)
filler = pcbnew.ZONE_FILLER(board)
ok = filler.Fill(board.Zones())
print("fill ok:", ok)
board.Save(PCB)
print("saved")
