"""MAHM reader: thread-safety under Afterburner restarts + power-unit handling.
A helper subprocess owns a spec-built 'MAHMSharedMemory' section and keeps
flipping it to 0xDEAD / destroying / recreating it while 4 threads read."""
import ctypes, os, struct, subprocess, sys, threading, time
from ctypes import wintypes
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NAME = f"GopTestMAHM_{os.getpid()}"   # never the real Afterburner section
ENTRY = 1324


def image(power_units="%"):
    ents = [("GPU temperature", "C", 55.0, 0, 0x00), ("GPU voltage", "V", 1.05, 0, 0x40),
            ("Power", power_units, 85.0 if power_units == "%" else 250.0, 0, 0x60),
            ("Core clock", "MHz", 2745.0, 0, 0x20), ("CPU power", "W", 90.0, 0xFFFFFFFF, 0x100)]
    hdr = struct.pack("<IIIIIIII", 0x4D41484D, 0x00020000, 32, len(ents), ENTRY, int(time.time()), 0, 0)
    body = b""
    for n, u, v, g, sid in ents:
        e = bytearray(ENTRY)
        e[0:len(n)] = n.encode(); e[260:260 + len(u)] = u.encode()
        struct.pack_into("<ffffIII", e, 1300, v, 0.0, 100.0, 0, g, sid)[0:0] if False else None
        struct.pack_into("<f", e, 1300, v)
        struct.pack_into("<II", e, 1316, g, sid)
        body += bytes(e)
    return hdr + body


HELPER = r'''
import ctypes, sys, time, struct
from ctypes import wintypes
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateFileMappingW.restype = wintypes.HANDLE
k.CreateFileMappingW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]
k.MapViewOfFile.restype = ctypes.c_void_p
k.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
k.CloseHandle.argtypes = [wintypes.HANDLE]
img = bytes.fromhex(sys.argv[1]); secs = float(sys.argv[2])
INVALID = wintypes.HANDLE(-1)
end = time.time() + secs
cycles = 0
while time.time() < end:
    h = k.CreateFileMappingW(INVALID, None, 0x04, 0, 1 << 16, sys.argv[3])
    v = k.MapViewOfFile(h, 0x0002, 0, 0, 0)
    ctypes.memmove(v, img, len(img))
    for _ in range(20):                      # live, then "shutting down", then live ...
        time.sleep(0.004)
        ctypes.memmove(v, struct.pack("<I", 0xDEAD), 4)
        time.sleep(0.002)
        ctypes.memmove(v, img[:4], 4)
    ctypes.memmove(v, struct.pack("<I", 0xDEAD), 4)
    k.UnmapViewOfFile(v); k.CloseHandle(h)   # Afterburner exits
    time.sleep(0.01)
    cycles += 1
print(cycles)
'''

# live section for the whole lifetime of the helper (no flapping)
STATIC = HELPER.split("end = time.time()")[0] + """
h = k.CreateFileMappingW(INVALID, None, 0x04, 0, 1 << 16, sys.argv[3])
v = k.MapViewOfFile(h, 0x0002, 0, 0, 0)
ctypes.memmove(v, img, len(img))
time.sleep(secs)
k.UnmapViewOfFile(v); k.CloseHandle(h)
"""

import core.mahm_reader as mr
mr.MAHM_SHARED_MEMORY_NAME = NAME
from core.mahm_reader import MAHMReader, section_ready

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

# 1) power units + basic parse (static section)
for units, want in (("%", 0.0), ("W", 250.0)):
    hp = subprocess.Popen([sys.executable, "-c", STATIC, image(units).hex(), "1.5", NAME],
                          stdout=subprocess.PIPE)
    time.sleep(0.25)
    r = MAHMReader()
    d = r.read()
    check(d.available and abs(d.gpu_voltage_mv - 1050) < 0.5 and abs(d.core_clock - 2745) < 0.01,
          f"parse ok ({units}): {d.gpu_voltage_mv:.0f} mV, {d.core_clock:.0f} MHz")
    check(abs(d.gpu_power_w - want) < 0.01, f"'Power' in {units!r} -> gpu_power_w={d.gpu_power_w}")
    check(abs(d.gpu_temp - 55) < 0.01, "CPU power (0x100, global) does not overwrite GPU temp")
    ents = r.debug_entries()
    check(len(ents) == 5 and ents[1][0] == "GPU voltage", "debug_entries lists all sources")
    check(section_ready(), "section_ready() True while the section is live")
    r.close(); hp.wait()
    time.sleep(0.2)
    check(not section_ready(), "section_ready() False after it is gone")

# 2) stress: 4 threads (3 read, 1 reopen) while the section flaps
hp = subprocess.Popen([sys.executable, "-c", HELPER, image().hex(), "8", NAME], stdout=subprocess.PIPE, text=True)
r = MAHMReader()
stop = threading.Event()
stats = {"reads": 0, "avail": 0, "bad": 0, "reopen": 0, "errors": 0}
lock = threading.Lock()
def reader():
    while not stop.is_set():
        try:
            d = r.read()
            with lock:
                stats["reads"] += 1
                if d.available:
                    stats["avail"] += 1
                    if d.gpu_voltage_mv and abs(d.gpu_voltage_mv - 1050) > 0.5:
                        stats["bad"] += 1
        except Exception:
            with lock:
                stats["errors"] += 1
def reopener():
    while not stop.is_set():
        r.reopen()
        with lock:
            stats["reopen"] += 1
        time.sleep(0.003)
r.RETRY_INTERVAL_S = 0.0     # reconnect as aggressively as possible
ts = [threading.Thread(target=reader) for _ in range(3)] + [threading.Thread(target=reopener)]
[t.start() for t in ts]
time.sleep(8.5)
stop.set(); [t.join() for t in ts]
cycles = int((hp.communicate()[0] or "0").strip() or 0)
print(f"  stats: {stats}, section create/destroy cycles: {cycles}")
check(stats["errors"] == 0 and stats["bad"] == 0, "no exceptions, no garbage values")
check(stats["avail"] > 100 and stats["reads"] > stats["avail"], "saw both live and dead phases")
check(cycles > 20, "section really was destroyed/recreated many times")
r.close()

# 3) frozen section (Afterburner force-killed, someone keeps the handle): the
#    stamp stops moving -> reader must give up on it, and must NOT re-attach to
#    the same frozen section — but must attach to a fresh one.
print("frozen section / suspend-resume")
hp = subprocess.Popen([sys.executable, "-c", STATIC, image().hex(), "4", NAME], stdout=subprocess.PIPE)
time.sleep(0.3)
r = MAHMReader()
r.STALE_S = 1.0
r.RETRY_INTERVAL_S = 0.0
check(r.read().available, "live at first")
time.sleep(1.4)
d = r.read()
check(not d.available and "eingefroren" in r.error, f"frozen stamp detected: {r.error}")
r.reopen()
check(not r.available, "does not re-attach to the same frozen section")
hp.wait()
time.sleep(1.1)                               # new stamp (whole seconds)
hp = subprocess.Popen([sys.executable, "-c", STATIC, image().hex(), "3", NAME], stdout=subprocess.PIPE)
time.sleep(0.3)
check(r.read().available, "re-attaches to a FRESH section (new stamp)")
r.suspend(30)
check(not r.available and not r.read().available, "suspend(): released and no reconnect while suspended")
r.resume()
check(r.available and r.read().available, "resume(): connected again")
r.close(); hp.wait()
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
