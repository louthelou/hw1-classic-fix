#!/usr/bin/env python3
"""dockfix_patch.py - in-place fixes for Homeworld 1 Classic (HWRM 2.303 build, 2023-11-08).

Patch groups (every change is same-size and in place: no code cave, file size unchanged):

  dock   (always)   restore floating-point ABS() in aishipFlyToPointAvoidingObjsFunc.  The July-2023
                    rebuild compiled every float absolute value as an integer truncation (CVTTSS2SI /
                    CDQ-XOR-SUB / CVTSI2SS), so GetCollSizeInDirection() returns ~0, "destination
                    obscured" is never reported and strike craft orbit the Kushan mothership forever.
  --full            the same ABS() repair at the remaining sites that matter in flight: descend pitch,
                    bank/pitch tracker, attack-height check, camera easing.
  --video           widescreen and Windows 10/11 fixes:
                      V1 move-disc: cameraRayCast assumed a 4:3 frustum (cursor landed at (4/3)/aspect
                         of its travel at wider ratios) -> scale the look vector by height/width.
                      V2 resolution list: drop the 1600-pixel cap and the five-mode whitelist so the
                         Video options list every mode the display driver reports.
                      V3 settings in HKEY_CURRENT_USER instead of HKEY_LOCAL_MACHINE (the exe opened
                         HKLM for write with an asInvoker manifest: standard users read nothing and
                         ran at 640x480 unless a compat mode turned UAC virtualisation on).
                      V4 default colour depth 32-bit instead of 16-bit (first run on Windows 8+).

Usage:
  python dockfix_patch.py check  <Homeworld.exe>                      state of every known site
  python dockfix_patch.py apply  <Homeworld.exe> [<out.exe>] [--full] [--video]
                                 (default: in place, backup *.orig-2.303 or *.before-dockfix)
  python dockfix_patch.py revert <Homeworld.exe>                      restore every known site
Each site is verified individually, so the patch coexists with other exe mods and refuses to
touch a file where another patch overlaps one of its sites.
"""
import hashlib, os, shutil, struct, sys

ORIGINAL_SHA256 = "421c114e832c56bd1994fe97c342969ef69881bb74399e67bef979c6923df381"   # 2.303, 2023-11-08
PE_SIZE = 3591168

NOP1, NOP2, NOP3, NOP6 = "90", "66 90", "0f 1f 00", "66 0f 1f 44 00 00"
AND_ABS = "25 ff ff ff 7f"           # AND EAX,0x7FFFFFFF
SHL1, SHR1 = "d1 e0", "d1 e8"        # SHL EAX,1 / SHR EAX,1  (together: clear bit 31)
MOVD_EAX_XMM1, MOVD_EAX_XMM2, MOVD_EAX_XMM5 = "66 0f 7e c8", "66 0f 7e d0", "66 0f 7e e8"
MOVD_XMM0_EAX, MOVD_XMM2_EAX = "66 0f 6e c0", "66 0f 6e d0"

# (virtual address, original bytes, replacement bytes, note) - all inside FUN_00416720
PATCHES_DOCK = [
    # --- obscured-destination test: GetCollSizeInDirection(avoidobj, destToObjNorm) ---
    (0x417a4d, "f3 0f 2c c2", MOVD_EAX_XMM2, "O1 cvttss2si eax,xmm2 -> movd"),
    (0x417a51, "0f 57 d2",    NOP3,          "O1 xorps xmm2,xmm2 (zeroing for cvtsi2ss) -> nop"),
    (0x417a58, "99",          NOP1,          "O1 cdq -> nop"),
    (0x417a5d, "33 c2",       SHL1,          "O1 xor eax,edx -> shl eax,1"),
    (0x417a65, "2b c2",       SHR1,          "O1 sub eax,edx -> shr eax,1"),
    (0x417a73, "f3 0f 2a d0", MOVD_XMM2_EAX, "O1 cvtsi2ss xmm2,eax -> movd"),
    (0x417a87, "f3 0f 2c c1", MOVD_EAX_XMM1, "O2 cvttss2si eax,xmm1 -> movd"),
    (0x417a8b, "99 33 c2 2b c2", AND_ABS,    "O2 cdq/xor/sub -> and eax,0x7fffffff"),
    (0x417a90, "f3 0f 2a c0", MOVD_XMM0_EAX, "O2 cvtsi2ss xmm0,eax -> movd"),
    (0x417a94, "f3 0f 2c c5", MOVD_EAX_XMM5, "O3 cvttss2si eax,xmm5 -> movd"),
    (0x417a9d, "99 33 c2 2b c2", AND_ABS,    "O3 cdq/xor/sub -> and eax,0x7fffffff"),
    (0x417aa9, "f3 0f 2a c0", MOVD_XMM0_EAX, "O3 cvtsi2ss xmm0,eax -> movd"),
    # --- collidedist = GetCollSizeInDirection(ship,repulsenorm) + GetCollSizeInDirection(avoidobj,repulsenorm) ---
    (0x417698, "f3 0f 2c c1", MOVD_EAX_XMM1, "C1 cvttss2si -> movd"),
    (0x4176a5, "99 33 c2 2b c2", AND_ABS,    "C1 abs"),
    (0x4176bb, "0f 5b db",    NOP3,          "C1 cvtdq2ps xmm3 -> nop"),
    (0x4176c7, "f3 0f 2c c1", MOVD_EAX_XMM1, "C2 cvttss2si -> movd"),
    (0x4176d3, "99",          NOP1,          "C2 cdq -> nop"),
    (0x4176d4, "33 c2",       SHL1,          "C2 xor -> shl"),
    (0x4176da, "2b c2",       SHR1,          "C2 sub -> shr"),
    (0x4176e0, "0f 5b c0",    NOP3,          "C2 cvtdq2ps xmm0 -> nop"),
    (0x41770c, "f3 0f 2c c1", MOVD_EAX_XMM1, "C3 cvttss2si -> movd"),
    (0x417713, "99 33 c2 2b c2", AND_ABS,    "C3 abs"),
    (0x41771c, "0f 5b c0",    NOP3,          "C3 cvtdq2ps xmm0 -> nop"),
    (0x41775d, "f3 0f 2c c1", MOVD_EAX_XMM1, "C4 cvttss2si -> movd"),
    (0x41776c, "99 33 c2 2b c2", AND_ABS,    "C4 abs"),
    (0x417775, "0f 5b d2",    NOP3,          "C4 cvtdq2ps xmm2 -> nop"),
    (0x417790, "f3 0f 2c c1", MOVD_EAX_XMM1, "C5 cvttss2si -> movd"),
    (0x41779c, "99",          NOP1,          "C5 cdq -> nop"),
    (0x41779d, "33 c2",       SHL1,          "C5 xor -> shl"),
    (0x4177a3, "2b c2",       SHR1,          "C5 sub -> shr"),
    (0x4177a9, "0f 5b c0",    NOP3,          "C5 cvtdq2ps xmm0 -> nop"),
    (0x4177d4, "f3 0f 2c c1", MOVD_EAX_XMM1, "C6 cvttss2si -> movd"),
    (0x4177e0, "99 33 c2 2b c2", AND_ABS,    "C6 abs"),
    (0x4177e9, "0f 5b c0",    NOP3,          "C6 cvtdq2ps xmm0 -> nop"),
]


SHL1_ESI, SHR1_ESI = "d1 e6", "d1 ee"      # SHL ESI,1 / SHR ESI,1
MOVD_EAX_XMM0 = "66 0f 7e c0"

# --full: the other three ABS() sites in the same function plus three elsewhere.
#  A: zdistanceleft = ABS(dest.z - ship.z)            (magnitude; truncation < 1 unit)
#  B: ABS(distcheck) > maxdistconsider                 (magnitude; truncation < 1 unit)
#  C: zdistanceleft = dz * ABS(ship->aidescend)        (fraction -> truncated to 0: disables descend pitch)
PATCHES_FULL = [
    (0x416871, "f3 0f 2c c0", MOVD_EAX_XMM0, "A cvttss2si eax,xmm0 -> movd"),
    (0x416879, "99",          NOP1,          "A cdq -> nop"),
    (0x41687c, "33 f2",       SHL1_ESI,      "A xor esi,edx -> shl esi,1"),
    (0x41687e, "2b f2",       SHR1_ESI,      "A sub esi,edx -> shr esi,1"),
    (0x41689c, "0f 5b d2",    NOP3,          "A cvtdq2ps xmm2 -> nop"),
    (0x416ebc, "f3 0f 2c c1", MOVD_EAX_XMM1, "B cvttss2si eax,xmm1 -> movd"),
    (0x416ec6, "99",          NOP1,          "B cdq -> nop"),
    (0x416ec9, "33 f2",       SHL1_ESI,      "B xor esi,edx -> shl esi,1"),
    (0x416ecb, "2b f2",       SHR1_ESI,      "B sub esi,edx -> shr esi,1"),
    (0x416ed1, "0f 5b c9",    NOP3,          "B cvtdq2ps xmm1 -> nop"),
    (0x417d91, "f3 0f 2c c0", MOVD_EAX_XMM0, "C cvttss2si eax,xmm0 -> movd"),
    (0x417d9f, "99 33 c2 2b c2", AND_ABS,    "C cdq/xor/sub -> and eax,0x7fffffff"),
    (0x417da8, "0f 5b d2",    NOP3,          "C cvtdq2ps xmm2 -> nop"),
    # aitrackHeadingWithBankPitchFunc: actualpitchturn = (1 - ABS(dotprodheading)) * pitchturn
    (0x41ba97, "f3 0f 2c c5", MOVD_EAX_XMM5, "D cvttss2si eax,xmm5 -> movd"),
    (0x41ba9b, "99 33 c2 2b c2", AND_ABS,    "D cdq/xor/sub -> and eax,0x7fffffff"),
    (0x41baa7, "0f 5b c0",    NOP3,          "D cvtdq2ps xmm0 -> nop"),
    # command layer: ABS(cross-product component) compared with a threshold
    (0x4420c6, "f3 0f 2c c0", MOVD_EAX_XMM0, "E cvttss2si eax,xmm0 -> movd"),
    (0x4420ca, "99 33 c2 2b c2", AND_ABS,    "E cdq/xor/sub -> and eax,0x7fffffff"),
    (0x4420cf, "f3 0f 2a d0", MOVD_XMM2_EAX, "E cvtsi2ss xmm2,eax -> movd"),
    # camera easing: if (ABS(diff) < rate) snap else step by rate*diff/ABS(diff)
    (0x4bea1f, "f3 0f 2c c1", MOVD_EAX_XMM1, "F cvttss2si eax,xmm1 -> movd"),
    (0x4bea23, "99 33 c2 2b c2", AND_ABS,    "F cdq/xor/sub -> and eax,0x7fffffff"),
    (0x4bea2c, "0f 5b db",    NOP3,          "F cvtdq2ps xmm3 -> nop"),
]

# --video ------------------------------------------------------------------------------------
# V1  cameraRayCast clone FUN_0042aa70 (the only compiled copy; called from pieplate.c with the
#     mouse position and MAIN_WindowWidth/Height).  Original maps the cursor to a plane of width 1
#     and height H/W and scales the unit look vector by 0.49 - exact for 4:3 only.  Correct for any
#     aspect: scale the look vector by (H/W) * 0.49/0.75 instead.  Done with the frame slot S0+0,
#     which the function never uses: the prologue is re-encoded with CVTSI2SS (3 bytes shorter
#     than MOVD+CVTDQ2PS, four times) to make room for a MOVSS that stashes H/W there; the 1.0
#     that starts the look-vector normalisation (1/len) is then read from that slot, and the 0.49
#     constant (used by this function only) becomes 0.49/0.75.
RAYCAST_PROLOGUE_OLD = (
    "66 0f 6e 15 0c 1d 6d 00 66 0f 6e 0d c0 2c 7d 00 0f 5b c9 a1 54 9c 73 00 56 83 ec 08 8b f1 "
    "0f 5b d2 66 0f 6e 1d c4 2c 7d 00 f3 0f 5e ca 0f 5b db f3 0f 5c 0d 64 e6 66 00 f3 0f 10 68 38 "
    "f3 0f 10 60 1c 0f 28 c5 f3 0f 5c 60 10 f3 0f 11 4c 24 34 66 0f 6e 0d 08 1d 6d 00 0f 5b c9 "
    "f3 0f 59 ec f3 0f 5e d9 f3 0f 5e ca f3 0f 5c 1d 64 e6 66 00 f3 0f 10 50 20 f3 0f 5c 50 14 "
    "f3 0f 11 64 24 1c f3 0f 59 d9")
RAYCAST_PROLOGUE_NEW = (
    "f3 0f 2a 15 0c 1d 6d 00 "      # cvtsi2ss xmm2,[MAIN_WindowWidth]
    "f3 0f 2a 0d c0 2c 7d 00 "      # cvtsi2ss xmm1,[mouseCursorX]
    "a1 54 9c 73 00 "               # mov eax,[mrCamera]
    "56 83 ec 08 8b f1 "            # push esi; sub esp,8; mov esi,ecx
    "f3 0f 2a 1d c4 2c 7d 00 "      # cvtsi2ss xmm3,[mouseCursorY]
    "f3 0f 5e ca "                  # divss xmm1,xmm2            x/W
    "f3 0f 5c 0d 64 e6 66 00 "      # subss xmm1,[0.5]           px
    "f3 0f 10 68 38 f3 0f 10 60 1c 0f 28 c5 f3 0f 5c 60 10 "   # camera up.z / look.x loads (unchanged)
    "f3 0f 11 4c 24 34 "            # movss [esp+0x34],xmm1      store px
    "f3 0f 2a 0d 08 1d 6d 00 "      # cvtsi2ss xmm1,[MAIN_WindowHeight]
    "f3 0f 59 ec "                  # mulss xmm5,xmm4            (unchanged)
    "f3 0f 5e d9 "                  # divss xmm3,xmm1            y/H
    "f3 0f 5e ca "                  # divss xmm1,xmm2            H/W
    "f3 0f 11 4c 24 0c "            # movss [esp+0xc],xmm1       NEW: stash H/W in the unused slot
    "f3 0f 5c 1d 64 e6 66 00 "      # subss xmm3,[0.5]           py
    "f3 0f 10 50 20 f3 0f 5c 50 14 f3 0f 11 64 24 1c "         # look.y, store look.x (unchanged)
    "f3 0f 59 d9 "                  # mulss xmm3,xmm1            py*H/W (unchanged)
    + NOP6)
PATCHES_VIDEO = [
    (0x42aa79, RAYCAST_PROLOGUE_OLD, RAYCAST_PROLOGUE_NEW, "V1 raycast prologue: stash H/W"),
    (0x42abeb, "f3 0f 10 0d fc e6 66 00", "f3 0f 10 4c 24 04 " + NOP2, "V1 look 1/len starts from H/W instead of 1.0"),
    (0x66e660, "48 e1 fa 3e", "da 40 27 3f", "V1 constant 0.49 -> 0.49/0.75"),
    # The exe is ASLR-relocated (DYNAMICBASE; it loads at e.g. 0x70000), so every absolute
    # operand the loader fixes up has a .reloc entry naming its offset.  The re-encoded prologue
    # moved five of those operands and dropped the one at 0x42abef: move the entries with them
    # (page 0x42a000 block, entries are u16 = type<<12 | offset) and turn the dropped one into
    # an ABSOLUTE (type 0) no-op.  Without this the loader corrupts the new code and the game
    # crashes on the first move order.
    (0x88c938, "7d 3a 85 3a 8d 3a 9e 3a ad 3a cd 3a e4 3a ef 3b",
               "7d 3a 85 3a 8a 3a 98 3a a4 3a c4 3a de 3a 00 00", "V1 .reloc entries follow the moved operands"),
    # V2 rinEnumDisplayModes callback FUN_00626d60: width <= 1600 -> width <= 0x7fffffff
    (0x626d9e, "81 fa 40 06 00 00", "81 fa ff ff ff 7f", "V2 drop the 1600-wide cap"),
    # V2 rinSortModes FUN_00626b40: jump straight to the devstat check, skipping the 5-mode whitelist
    (0x626c0b, "81 fe 00 04 00 00 7f 3d", "e9 6d 00 00 00 " + NOP3, "V2 accept every enumerated mode"),
    # V3 registry hive HKEY_LOCAL_MACHINE (0x80000002) -> HKEY_CURRENT_USER (0x80000001)
    (0x6344f1, "68 02 00 00 80", "68 01 00 00 80", "V3 utyVariablesLoad: HKLM -> HKCU"),
    (0x63463f, "68 02 00 00 80", "68 01 00 00 80", "V3 utyVariablesSave: HKLM -> HKCU"),
    (0x633f06, "68 02 00 00 80", "68 01 00 00 80", "V3 key open: HKLM -> HKCU"),
    (0x633f32, "68 02 00 00 80", "68 01 00 00 80", "V3 key create: HKLM -> HKCU"),
    (0x610344, "68 02 00 00 80", "68 01 00 00 80", "V3 CmdLine value: HKLM -> HKCU"),
    # V4 MAIN_WindowDepth initial value 16 -> 32
    (0x6d1d38, "10 00 00 00", "20 00 00 00", "V4 default colour depth 32-bit"),
    # V5 first-run resolution = desktop.  Image defaults for MAIN_WindowHeight/Width become 0
    # (= "nothing stored"); WinMain's call to utyVariablesLoad is redirected through a 55-byte
    # INT3 gap after FUN_005c3cd0 that calls it and then, if the width is still 0, stores
    # GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN).  Position-independent (call/pop EBX, all
    # operands EBX-relative) so it needs no .reloc entries; EBX saved; ECX/EDX are dead there.
    (0x6d1d08, "e0 01 00 00 80 02 00 00", "00 00 00 00 00 00 00 00", "V5 image defaults 640x480 -> 0 (unset)"),
    (0x5c3f79, "cc " * 54 + "cc",
               "e8 72 03 07 00 "                 # call utyVariablesLoad (0x6342f0)
               "53 "                            # push ebx
               "e8 00 00 00 00 5b "             # call $+5 / pop ebx        -> ebx = 0x5c3f84 (relocated)
               "83 bb 88 dd 10 00 00 "          # cmp dword [ebx+0x10dd88],0  (MAIN_WindowWidth 0x6d1d0c)
               "75 1c "                         # jnz done
               "6a 00 ff 93 f8 f2 09 00 "       # push 0; call [ebx+0x9f2f8]  (IAT GetSystemMetrics 0x66327c)
               "89 83 88 dd 10 00 "             # mov [ebx+0x10dd88],eax
               "6a 01 ff 93 f8 f2 09 00 "       # push 1; call [ebx+0x9f2f8]
               "89 83 84 dd 10 00 "             # mov [ebx+0x10dd84],eax      (MAIN_WindowHeight 0x6d1d08)
               "5b c3 "                         # done: pop ebx; ret
               "cc cc cc cc", "V5 cave: unset size -> desktop size"),
    (0x6130ab, "e8 40 12 02 00", "e8 c9 0e fb ff", "V5 WinMain calls the cave instead of utyVariablesLoad"),
    # V6 rinAddMode (FUN_00626ad0, 104 bytes): append -> ordered insert by height, then width, so
    # the Video options list reads smallest to largest (rinSortModes keeps 16-bit before 32-bit).
    # ecx = device, edx = width, [ebp+8] = height, [ebp+0xc] = depth; node = {w, h, depth, next}.
    # The new code needs 74 of the 104 bytes; the remaining 30 host the V7 stub below.
    (0x626ad0, "55 8b ec 53 56 57 6a 10 8b f2 8b d9 e8 7a 13 02 00 8b 4d 0c 8b f8 8b 55 08 83 c4 04 "
               "c7 47 0c 00 00 00 00 89 37 89 57 04 89 4f 08 8b 8b 8c 00 00 00 85 c9 75 0e 89 bb 8c "
               "00 00 00 89 4f 0c 5f 5e 5b 5d c3 8b 41 0c 85 c0 74 0f",
               "55 8b ec 53 56 57 "               # push ebp; mov ebp,esp; push ebx/esi/edi
               "6a 10 8b f2 8b d9 "               # push 16; esi = width; ebx = device
               "e8 7a 13 02 00 "                  # call malloc (same position as the original)
               "8b f8 83 c4 04 "                  # edi = node; add esp,4
               "8b 4d 0c 8b 55 08 "               # ecx = depth; edx = height
               "89 37 89 57 04 89 4f 08 "         # node->w, ->h, ->depth
               "8d 83 8c 00 00 00 "               # eax = &device->modes (link to patch)
               "8b 08 85 c9 74 10 "               # loop: ecx = *link; if null -> insert
               "39 51 04 7c 06 7f 09 "            # cmp cur->h,new h: less -> next; greater -> insert
               "39 31 77 05 "                     # cmp cur->w,new w: above -> insert
               "8d 41 0c eb ea "                  # next: link = &cur->next; jmp loop
               "89 4f 0c 89 38 "                  # insert: new->next = cur; *link = new
               "5f 5e 5b 5d c3",                  # pop edi/esi/ebx/ebp; ret
               "V6 rinAddMode: ordered insert by height, then width"),
    # V7 live resolution change keeps the old projection aspect: rndAspectRatio (0x7d2ca8) is
    # written only by rndInit at start-up, and the in-game Accept path (FUN_004afea0 ->
    # FUN_006119b0 renderer reload) never recomputes it, so after switching to a different
    # aspect the frustum is still the old one and the move disc (and the picture) are off.
    # The Accept path's call to the reload is redirected through a 29-byte stub in the tail of
    # rinAddMode that recomputes width/height (x87, position-independent via call/pop eax; eax
    # is dead there) and tail-jumps into the reload.
    (0x4b01c5, "e8 e6 17 16 00", "e8 50 69 17 00", "V7 options Accept calls the aspect stub, which jumps to the renderer reload"),
    (0x626b1a, "66 0f 1f 44 00 00 8b c8 8b 41 0c 85 c0 75 f7 89 79 0c c7 47 0c 00 00 00 00 5f 5e 5b 5d c3",
               "e8 00 00 00 00 58 "               # call $+5; pop eax        -> eax = 0x626b1f (relocated)
               "db 80 ed b1 0a 00 "               # fild dword [eax+0xab1ed]   (MAIN_WindowWidth 0x6d1d0c)
               "da b0 e9 b1 0a 00 "               # fidiv dword [eax+0xab1e9]  (MAIN_WindowHeight 0x6d1d08)
               "d9 98 89 c1 1a 00 "               # fstp dword [eax+0x1ac189]  (rndAspectRatio 0x7d2ca8)
               "e9 79 ae fe ff "                  # jmp FUN_006119b0
               "cc", "V7 stub: rndAspectRatio = width / height, then the renderer reload"),
]

# Bytes an earlier build of this tool left at a site; apply upgrades them to the current
# replacement and revert restores the original, instead of refusing them as foreign.
LEGACY = {
    0x626b1a: ["cc " * 29 + "cc"],      # v3 build 9cb2b4ca: INT3 padding after the 74-byte insert
}

GROUPS = [("dock", PATCHES_DOCK), ("full", PATCHES_FULL), ("video", PATCHES_VIDEO)]
ALL_PATCHES = PATCHES_DOCK + PATCHES_FULL + PATCHES_VIDEO
PATCHES = PATCHES_DOCK                      # default selection (apply without flags)
if "--full" in sys.argv:
    sys.argv.remove("--full"); PATCHES = PATCHES + PATCHES_FULL
if "--video" in sys.argv:
    sys.argv.remove("--video"); PATCHES = PATCHES + PATCHES_VIDEO


def hx(s):
    return bytes.fromhex(s.replace(" ", ""))


for _va, _old, _new, _note in ALL_PATCHES:
    assert len(hx(_old)) == len(hx(_new)), "size mismatch at %#x (%s)" % (_va, _note)


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    out = []
    for i in range(nsec):
        o = pe + 24 + optsz + 40 * i
        vsize, va, rsize, raw = struct.unpack_from("<IIII", d, o + 8)
        out.append((base + va, max(vsize, rsize), raw))
    return out


def va2off(secs, va):
    for start, size, raw in secs:
        if start <= va < start + size:
            return raw + (va - start)
    raise ValueError("VA %#x not in any section" % va)


def classify(d, patches=None):
    """Per-site state so the patch coexists with other exe mods: each slot is 'original',
    'patched' or 'foreign' (bytes that are neither - some other patch touched them)."""
    secs = sections(d)
    out = []
    for va, old, new, note in (patches or PATCHES):
        off = va2off(secs, va)
        cur = bytes(d[off:off + len(hx(old))])
        if cur == hx(old):
            state = "original"
        elif cur == hx(new):
            state = "patched"
        elif any(cur == hx(b) for b in LEGACY.get(va, [])):
            state = "legacy"
        else:
            state = "foreign"
        out.append((va, state, cur, note))
    return out


def status(d, patches=None):
    if len(d) != PE_SIZE:
        return "not the 2.303 build (size %d)" % len(d)
    states = [s for _, s, _, _ in classify(d, patches)]
    if all(s == "original" for s in states):
        return "original"
    if all(s == "patched" for s in states):
        return "patched"
    return "mixed (%d original, %d patched, %d from an earlier build, %d foreign of %d sites)" % (
        states.count("original"), states.count("patched"), states.count("legacy"), states.count("foreign"), len(states))


def transform(d, patches, forward=True):
    """Apply (forward) or revert the given sites.  Sites already in the target state are
    skipped, so the tool is idempotent; a site holding foreign bytes aborts the run untouched."""
    d = bytearray(d); secs = sections(d)
    changed = skipped = 0
    for va, state, cur, note in classify(bytes(d), patches):
        want, src = ("patched", "original") if forward else ("original", "patched")
        if state == want:
            skipped += 1
            continue
        if state not in (src, "legacy"):
            raise RuntimeError("site %#x (%s) holds foreign bytes %s - another exe patch overlaps; aborting"
                               % (va, note, cur.hex(" ")))
        off = va2off(secs, va)
        new = next(hx(n if forward else o) for v, o, n, _ in patches if v == va)
        d[off:off + len(new)] = new
        changed += 1
    print("sites changed: %d, already in target state: %d" % (changed, skipped))
    return bytes(d)


def report(d):
    for name, group in GROUPS:
        print("  group %-6s %2d sites: %s" % (name, len(group), status(d, group)))


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    cmd, path = argv[1], argv[2]
    d = open(path, "rb").read()
    sha = hashlib.sha256(d).hexdigest()
    print("file: %s  size: %d  sha256: %s" % (path, len(d), sha))
    if len(d) != PE_SIZE:
        sys.exit("refusing: this is not the 2.303 (2023-11-08) Homeworld.exe this patch was made for")
    report(d)
    if cmd == "check":
        return
    patches = ALL_PATCHES if cmd == "revert" else PATCHES
    foreign = [(va, cur, note) for va, s, cur, note in classify(d, patches) if s == "foreign"]
    if foreign:
        for va, cur, note in foreign:
            print("  foreign bytes at %#x (%s): %s" % (va, note, cur.hex(" ")))
        sys.exit("refusing: another exe patch overlaps %d site(s) above; nothing changed" % len(foreign))
    if cmd == "apply":
        out = argv[3] if len(argv) > 3 else path
        if out == path:
            # keep a copy of whatever was there: the pristine original gets the canonical name,
            # an exe already modified by other mods is kept under a different name
            bak = path + (".orig-2.303" if sha == ORIGINAL_SHA256 else ".before-dockfix")
            if not os.path.exists(bak):
                shutil.copy2(path, bak); print("backup: " + bak)
        new = transform(d, patches, True)
        open(out, "wb").write(new)
        print("written: %s  sha256: %s" % (out, hashlib.sha256(new).hexdigest()))
        report(new)
    elif cmd == "revert":
        new = transform(d, patches, False)
        open(path, "wb").write(new)
        h = hashlib.sha256(new).hexdigest()
        print("reverted: sha256 %s %s" % (h, "(matches original)" if h == ORIGINAL_SHA256 else "(other modifications remain)"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
