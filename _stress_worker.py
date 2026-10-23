"""NVTuner Stress Worker — runs in a subprocess to load the GPU (and CPU as fallback).

The parent (GUI) PID is passed as argv[1] so every burn loop can stop itself the
moment the GUI is gone. Without that, a hard GUI crash (not the clean Stop button,
which calls .terminate()) would leave an orphaned process pegging the CPU/GPU at
100% forever. os.getppid() is unreliable here — Windows does not re-parent orphans
and keeps returning the dead parent's PID — so the PID is handed in explicitly.

argv[2] = mode:
  "gemm" (default)  the same matrix product over and over; every result is compared
                    with the first one. cuBLAS SGEMM is deterministic, so ANY
                    difference is a computation error — the first sign of an
                    unstable overclock, long before a crash or a driver reset (the
                    method of gpu-burn / OCCT). Prints "RATE <TFLOPS>" every second.
  "mixed"           alternates 10 s of the "gemm" load with 10 s of BOOST load:
                    a smaller product with a pause after each one. Measured on an
                    RTX 4080: the full load runs ~2510 MHz at the power limit
                    (mid-curve), the boost load 2790 MHz at 240 W / 64 % util —
                    the top of the V/F curve, exactly where games run and where an
                    overclock fails first. Every result is verified in both phases.
                    Prints "RATE" in the full phase, "BEAT" in the boost phase.
Every mode prints a line at least once a second, each after a VERIFIED result:
the tuner counts 8 s without one as a hung GPU (StressTester.HANG_S). "mixed"
printed nothing for its 10-s boost phase — every step "hung" (live, round 16).
  "boost"           only the boost phase of "mixed", without pause: the GPU stays
                    at the TOP point of its V/F curve (below the power limit) —
                    with the curve flattened at a voltage point, exactly that
                    point is tested. Prints "RATE <TFLOPS>" (duty-cycled work).
  "transient"       load CHANGES at the top of the curve: verified products in
                    bursts of random length (5–250 ms, light or full size) with
                    random idle gaps — the GPU jumps between idle and load at its
                    highest clock, as in games (scene changes, menus, uneven
                    frames). The load step at a high clock is where the supply
                    voltage dips; a steady load never shows that. (A game can end
                    with D3D12 "device hung" on a profile that passed every
                    steady test.) Prints "RATE <TFLOPS>".
  "boost_trans"     the point search's step (23.10.): "boost" for GOP_STRESS_SPLIT_S
                    seconds (the GPU sits on the point, its voltage is measured), then
                    "transient" at that point until the end — live, a point found with
                    the boost load alone failed ~100 MHz lower under 3D + encoder + load
                    changes. One process: no second start-up per step.
  "mem"             copies two large buffers back and forth and prints
                    "BW <GB/s>". GDDR6X corrects transfer errors by retrying, so a
                    memory overclock past its limit shows up as LOST bandwidth, not
                    as a crash; every 50th round trip is verified against a copy.
  "encode"          what recording / streaming adds to a game (round 33): every frame a
                    CUDA kernel draws a scene, scales it and converts it to NV12 (OBS's
                    "GPU scaling"), and the video engine (NVENC, core/nvenc.py) encodes it
                    — H.264, preset P5, 60 frames a second (GOP_ENC_FPS, 0 = as fast as
                    it goes). The scenes repeat every ENC_CYCLE frames: each converted
                    frame's checksum must match its first one. A frame that takes longer
                    than ENC_STALL_S is a hung video engine (a hang stalls the encoder for
                    seconds). Prints "ENC <frames per second>". No NVENC
                    here (driver, session limit): "NOENC <why>", exit code 4.
On an error the worker prints "ERR <n>" and exits with code 3.
"""
import sys, os, time

EXIT_COMPUTE_ERROR = 3
EXIT_NO_ENCODER = 4
N = int(os.environ.get("GOP_STRESS_N", "8192"))          # matrix size (tests use less)
BOOST_N = int(os.environ.get("GOP_STRESS_BOOST_N", "4096"))  # boost-phase matrix size
MEM_MB = int(os.environ.get("GOP_STRESS_MEM_MB", "512"))  # per buffer in "mem" mode
HEAVY_S = float(os.environ.get("GOP_STRESS_HEAVY_S", "10"))
BOOST_S = float(os.environ.get("GOP_STRESS_BOOST_S", "10"))
BOOST_PAUSE = 0.5          # pause = 50 % of the kernel time -> ~64 % util, no power cap


def _parent_alive(pid):
    """True solange der angegebene Prozess lebt.
    ctypes (immer in Python eingebaut) zuerst — os.getppid() taugt auf Windows
    NICHT, weil Windows Waisen nicht umhängt und getppid() die tote Eltern-PID
    unverändert zurückgibt. psutil als Fallback. Wenn gar nichts prüfbar ist:
    als 'tot' behandeln, damit der Burner nie ewig weiterläuft (kein Zombie)."""
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k = ctypes.windll.kernel32          # nur Windows — sonst AttributeError
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False                    # Prozess existiert nicht mehr
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return (code.value == STILL_ACTIVE) if ok else True
    except Exception:
        pass
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False                        # nicht prüfbar -> lieber beenden


# Round 33: a stop on request. A hard kill in the middle of GPU work, while another program
# encodes video, makes the driver log nvlddmkm 153 ("aborted GPU work") — live 6 of 6 when
# two loads ended together, 0 of 6 for one alone. The hardness test asks its loads to end
# instead: it creates the file named in GOP_STRESS_STOP_FILE, the running product finishes,
# the loop returns, the encoder closes its session, the process exits. (Not stdin: a thread
# waiting on a stdin pipe kept the CUDA start-up from ever finishing.)
class _StopFlag:
    def __init__(self, path):
        self.path, self._next, self._set = path, 0.0, False

    def is_set(self) -> bool:
        if self._set or not self.path:
            return self._set
        now = time.monotonic()
        if now >= self._next:                 # a look every 0.1 s is plenty
            self._next = now + 0.1
            self._set = os.path.exists(self.path)
        return self._set


_STOP = _StopFlag(os.environ.get("GOP_STRESS_STOP_FILE", ""))


def _emit(line):
    try:
        print(line, flush=True)
    except Exception:
        pass                                # stdout closed / DEVNULL — keep burning


class _GpuStarted(Exception):
    """A CUDA error AFTER the GPU load was running — instability, not 'no CUDA'."""


def _gemm_set(cp, n):
    """Fixed inputs, the first product as reference, tolerance of a few ULPs."""
    a = cp.random.rand(n, n, dtype=cp.float32)
    b = cp.random.rand(n, n, dtype=cp.float32)
    ref = cp.dot(a, b)
    return a, b, ref, cp.empty_like(ref), cp.abs(ref) * 1e-6 + 1e-6


def _gemm_checked(cp, s):
    """One product, compared with the reference (gpu-burn check)."""
    a, b, ref, c, tol = s
    cp.dot(a, b, out=c)
    bad = int(cp.count_nonzero(cp.abs(c - ref) > tol))   # also synchronizes
    if bad:
        _emit(f"ERR {bad}")
        sys.exit(EXIT_COMPUTE_ERROR)


def mixed_stress(parent_pid):
    """Heavy + boost phases (see module docstring)."""
    import cupy as cp
    heavy, light = _gemm_set(cp, N), _gemm_set(cp, BOOST_N)
    cp.cuda.Stream.null.synchronize()
    flop = 2.0 * N ** 3
    try:
        alive_at = time.time()                            # the last line printed
        while not _STOP.is_set():
            end, last, iters = time.time() + HEAVY_S, time.time(), 0
            while time.time() < end and not _STOP.is_set():   # heavy: power-limited
                _gemm_checked(cp, heavy)
                iters += 1
                now = time.time()
                if now - last >= 1.0:
                    _emit(f"RATE {flop * iters / (now - last) / 1e12:.3f}")
                    last, iters, alive_at = now, 0, now
                    if not _parent_alive(parent_pid):     # GUI gone: not the rest of the phase
                        return
                elif now - alive_at >= 1.0:               # phase change: no 2-s gap
                    _emit("BEAT 1")
                    alive_at = now
            end = time.time() + BOOST_S
            while time.time() < end and not _STOP.is_set():   # boost: top of the curve
                t = time.perf_counter()
                _gemm_checked(cp, light)
                time.sleep((time.perf_counter() - t) * BOOST_PAUSE)
                if time.time() - alive_at >= 1.0:
                    alive_at = time.time()
                    _emit("BEAT 1")                       # alive (not a rate: no TFLOPS mix-up)
                    if not _parent_alive(parent_pid):
                        return
            if not _parent_alive(parent_pid):
                return
    except SystemExit:
        raise
    except Exception as e:
        raise _GpuStarted(str(e)) from e


def boost_stress(parent_pid, seconds: float = 0.0):
    """Boost load only (see module docstring): small verified products with a
    pause after each one — ~64 % utilisation, the top of the V/F curve.
    seconds: end after this long (0 = until stopped)."""
    import cupy as cp
    light = _gemm_set(cp, BOOST_N)
    cp.cuda.Stream.null.synchronize()
    flop = 2.0 * BOOST_N ** 3
    until = time.time() + seconds if seconds > 0 else 0.0
    try:
        last, iters = time.time(), 0
        while not _STOP.is_set() and not (until and time.time() >= until):
            t = time.perf_counter()
            _gemm_checked(cp, light)
            iters += 1
            time.sleep((time.perf_counter() - t) * BOOST_PAUSE)
            now = time.time()
            if now - last >= 1.0:
                _emit(f"RATE {flop * iters / (now - last) / 1e12:.3f}")
                last, iters = now, 0
                if not _parent_alive(parent_pid):
                    return
    except SystemExit:
        raise
    except Exception as e:
        raise _GpuStarted(str(e)) from e


TRANS_MAX_S = float(os.environ.get("GOP_STRESS_TRANS_MAX_S", "0.25"))


def boost_trans_stress(parent_pid):
    """The point search's step: the boost load, then load changes (see module docstring)."""
    try:
        split = max(1.0, float(os.environ.get("GOP_STRESS_SPLIT_S", "30")))
    except ValueError:
        split = 30.0
    boost_stress(parent_pid, seconds=split)
    if not _STOP.is_set() and _parent_alive(parent_pid):
        transient_stress(parent_pid)


def transient_stress(parent_pid):
    """Load changes at the top of the curve (see module docstring)."""
    import random
    import cupy as cp
    heavy, light = _gemm_set(cp, N), _gemm_set(cp, BOOST_N)
    cp.cuda.Stream.null.synchronize()
    rnd = random.Random(1)
    try:
        last, flops = time.time(), 0.0
        while not _STOP.is_set():
            s, n = (heavy, N) if rnd.random() < 0.3 else (light, BOOST_N)
            burst_end = time.perf_counter() + rnd.uniform(0.005, TRANS_MAX_S)
            while True:                                   # at least one product per burst
                _gemm_checked(cp, s)
                flops += 2.0 * n ** 3
                if time.perf_counter() >= burst_end:
                    break
            time.sleep(rnd.uniform(0.005, TRANS_MAX_S))   # idle: the clock stays up
            now = time.time()
            if now - last >= 1.0:
                _emit(f"RATE {flops / (now - last) / 1e12:.3f}")
                last, flops = now, 0.0
                if not _parent_alive(parent_pid):
                    return
    except SystemExit:
        raise
    except Exception as e:
        raise _GpuStarted(str(e)) from e


def cuda_stress(parent_pid):
    """GPU burn via cupy with result verification. Stops when the GUI
    (parent_pid) is gone — otherwise a hard GUI crash would leave the GPU
    pinned at 100% indefinitely."""
    import cupy as cp
    a = cp.random.rand(N, N, dtype=cp.float32)
    b = cp.random.rand(N, N, dtype=cp.float32)
    ref = cp.dot(a, b)                      # reference result of THIS run
    cp.cuda.Stream.null.synchronize()
    c = cp.empty_like(ref)
    tol = cp.abs(ref) * 1e-6 + 1e-6         # a few ULPs — real errors are far bigger
    flop = 2.0 * N ** 3
    try:
        last, iters = time.time(), 0
        while not _STOP.is_set():
            cp.dot(a, b, out=c)
            bad = int(cp.count_nonzero(cp.abs(c - ref) > tol))   # also synchronizes
            if bad:
                _emit(f"ERR {bad}")
                sys.exit(EXIT_COMPUTE_ERROR)
            iters += 1
            now = time.time()
            if now - last >= 1.0:
                _emit(f"RATE {flop * iters / (now - last) / 1e12:.3f}")
                last, iters = now, 0
                if not _parent_alive(parent_pid):
                    break
    except SystemExit:
        raise
    except Exception as e:
        raise _GpuStarted(str(e)) from e


def mem_stress(parent_pid):
    """Memory-bandwidth load for the memory-OC stage (see module docstring)."""
    import cupy as cp
    n = MEM_MB * 1024 * 1024 // 4
    a = cp.random.rand(n, dtype=cp.float32)
    b = cp.empty_like(a)
    ref = a.copy()          # independent copy: a corrupted b would otherwise be
    cp.cuda.Stream.null.synchronize()   # copied back into a and go unnoticed
    try:
        last, moved, busy, k = time.time(), 0, 0.0, 0
        checked = time.time()
        while not _STOP.is_set():
            t = time.time()
            cp.copyto(b, a)
            cp.copyto(a, b)
            cp.cuda.Stream.null.synchronize()
            busy += time.time() - t
            moved += 4 * a.nbytes               # 2 copies x (read + write)
            k += 1
            # Every 50th round trip — and at least twice a second: next to a
            # foreground FurMark the copies got little GPU time (live: 13 GB/s
            # instead of 231), and "every 50th" was then one compare every ~8 s.
            if k % 50 == 0 or time.time() - checked >= 0.5:
                checked = time.time()
                if not bool(cp.array_equal(a, ref)):
                    _emit("ERR 1")
                    sys.exit(EXIT_COMPUTE_ERROR)
            now = time.time()
            if now - last >= 1.0 and busy > 0:
                _emit(f"BW {moved / busy / 1e9:.1f}")
                last, moved, busy = now, 0, 0.0
                if not _parent_alive(parent_pid):
                    break
    except SystemExit:
        raise
    except Exception as e:
        raise _GpuStarted(str(e)) from e


ENC_FPS = float(os.environ.get("GOP_ENC_FPS", "60"))
ENC_SRC = os.environ.get("GOP_ENC_SRC", "2560x1440")     # the "game" frame
ENC_OUT = os.environ.get("GOP_ENC_OUT", "1920x1080")     # what is encoded
ENC_CODEC = os.environ.get("GOP_ENC_CODEC", "h264")
ENC_CYCLE = 30
ENC_STALL_S = float(os.environ.get("GOP_ENC_STALL_S", "5"))
ENC_SLOTS = 8

_ENC_KERNELS = r'''
extern "C" __global__ void scene(unsigned int* rgba, int w, int h, int n) {
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h) return;
    float t = n * 0.21f, fx = x * (1.0f / w), fy = y * (1.0f / h);
    unsigned int s = (unsigned int)x * 73856093u ^ (unsigned int)y * 19349663u ^ (unsigned int)n * 83492791u;
    s ^= s >> 13; s *= 0x5bd1e995u; s ^= s >> 15;
    float r = 0.5f + 0.5f * __sinf(fx * 17.0f + t);
    float g = 0.5f + 0.5f * __sinf(fy * 11.0f - t * 1.3f + fx * 3.0f);
    float b = 0.5f + 0.5f * __cosf((fx + fy) * 9.0f + t * 0.7f);
    unsigned int R = (unsigned int)(r * 215.0f) + (s & 31u);
    unsigned int G = (unsigned int)(g * 215.0f) + ((s >> 5) & 31u);
    unsigned int B = (unsigned int)(b * 215.0f) + ((s >> 10) & 31u);
    rgba[y * w + x] = R | (G << 8) | (B << 16) | 0xff000000u;
}
extern "C" __global__ void to_nv12(const unsigned int* src, int sw, int sh,
                                   unsigned char* dst, int dw, int dh, int pitch) {
    int bx = blockIdx.x * blockDim.x + threadIdx.x;
    int by = blockIdx.y * blockDim.y + threadIdx.y;
    if (bx * 2 >= dw || by * 2 >= dh) return;
    float sx = (float)sw / dw, sy = (float)sh / dh, ur = 0.f, ug = 0.f, ub = 0.f;
    for (int k = 0; k < 4; k++) {
        int x = bx * 2 + (k & 1), y = by * 2 + (k >> 1);
        float fx = (x + 0.5f) * sx - 0.5f, fy = (y + 0.5f) * sy - 0.5f;
        int x0 = max(0, min(sw - 2, (int)fx)), y0 = max(0, min(sh - 2, (int)fy));
        float ax = fminf(fmaxf(fx - x0, 0.f), 1.f), ay = fminf(fmaxf(fy - y0, 0.f), 1.f);
        float c0 = 0.f, c1 = 0.f, c2 = 0.f;
        for (int j = 0; j < 4; j++) {
            unsigned int p = src[(y0 + (j >> 1)) * sw + x0 + (j & 1)];
            float wt = ((j & 1) ? ax : 1.f - ax) * ((j >> 1) ? ay : 1.f - ay);
            c0 += wt * (p & 255u); c1 += wt * ((p >> 8) & 255u); c2 += wt * ((p >> 16) & 255u);
        }
        float Y = 16.f + 0.1826f * c0 + 0.6142f * c1 + 0.0620f * c2;
        dst[y * pitch + x] = (unsigned char)fminf(fmaxf(Y, 0.f), 255.f);
        ur += c0; ug += c1; ub += c2;
    }
    ur *= 0.25f; ug *= 0.25f; ub *= 0.25f;
    unsigned char* uv = dst + (size_t)dh * pitch + (size_t)by * pitch + bx * 2;
    uv[0] = (unsigned char)fminf(fmaxf(128.f - 0.1006f * ur - 0.3386f * ug + 0.4392f * ub, 0.f), 255.f);
    uv[1] = (unsigned char)fminf(fmaxf(128.f + 0.4392f * ur - 0.3989f * ug - 0.0403f * ub, 0.f), 255.f);
}
'''


def _res(text, default):
    try:
        w, h = (int(v) for v in text.lower().split("x"))
        return (w, h) if w >= 64 and h >= 64 else default
    except ValueError:
        return default


def encode_stress(parent_pid):
    """Scene + scaling (CUDA) + NVENC, like a game being streamed (see module docstring)."""
    import threading
    try:
        import cupy as cp
        from core import nvenc
    except ImportError as e:
        _emit(f"NOENC {e}")
        sys.exit(EXIT_NO_ENCODER)
    sw, sh = _res(ENC_SRC, (2560, 1440))
    dw, dh = _res(ENC_OUT, (1920, 1080))
    dw, dh = dw // 2 * 2, dh // 2 * 2
    pitch = (dw + 255) // 256 * 256
    try:
        mod = cp.RawModule(code=_ENC_KERNELS)
        scene, to_nv12 = mod.get_function("scene"), mod.get_function("to_nv12")
    except Exception as e:
        # Loading the kernels onto the card is GPU work: a driver error there stays one (with
        # GOP_STRESS_GPU_OK a failure of the step). Compiling them is the CPU's NVRTC — missing or
        # failing, that is "no encoder load here", not an unstable card.
        if isinstance(e, getattr(getattr(cp.cuda, "driver", None), "CUDADriverError", ())):
            raise
        _emit(f"NOENC kernels: {e}")
        sys.exit(EXIT_NO_ENCODER)
    src = cp.empty(sw * sh, dtype=cp.uint32)
    frames = [cp.zeros((dh * 3 // 2, pitch), dtype=cp.uint8) for _ in range(ENC_SLOTS)]
    cp.cuda.Stream.null.synchronize()
    try:
        enc = nvenc.Encoder(cp.cuda.driver.ctxGetCurrent(), dw, dh, codec=ENC_CODEC,
                            fps=int(ENC_FPS) or 60, slots=ENC_SLOTS, pitch=pitch)
        for i, f in enumerate(frames):
            enc.register(i, f.data.ptr)
    except nvenc.Unavailable as e:
        _emit(f"NOENC {e}")
        sys.exit(EXIT_NO_ENCODER)
    state = {"done": time.time()}

    def stall_guard():
        # also while the encoder closes: closing takes milliseconds — seconds there are a hung
        # video engine as well (the close gets a full window of its own, see finally below)
        while True:
            time.sleep(0.5)
            quiet = time.time() - state["done"]
            if quiet > ENC_STALL_S:
                _emit(f"ERR stall {quiet:.0f}s")
                os._exit(EXIT_COMPUTE_ERROR)
    threading.Thread(target=stall_guard, daemon=True).start()
    ref: dict = {}
    b1, b2 = (16, 16, 1), (16, 16, 1)
    g1 = ((sw + 15) // 16, (sh + 15) // 16, 1)
    g2 = ((dw // 2 + 15) // 16, (dh // 2 + 15) // 16, 1)
    step = 1.0 / ENC_FPS if ENC_FPS > 0 else 0.0
    n, out, last, nxt = 0, 0, time.time(), time.perf_counter()
    try:
        while not _STOP.is_set():
            k, slot = n % ENC_CYCLE, n % ENC_SLOTS
            f = frames[slot]
            scene(g1, b1, (src, cp.int32(sw), cp.int32(sh), cp.int32(k)))
            to_nv12(g2, b2, (src, cp.int32(sw), cp.int32(sh), f, cp.int32(dw), cp.int32(dh), cp.int32(pitch)))
            chk = int(f.sum(dtype=cp.uint64))                  # also synchronizes
            if ref.setdefault(k, chk) != chk:
                _emit("ERR frame")
                sys.exit(EXIT_COMPUTE_ERROR)
            sizes = enc.encode(slot)
            if any(s <= 0 for s in sizes):
                _emit("ERR empty")
                sys.exit(EXIT_COMPUTE_ERROR)
            out += len(sizes)
            state["done"] = time.time()
            n += 1
            now = time.time()
            if now - last >= 1.0:
                _emit(f"ENC {out / (now - last):.0f}")
                last, out = now, 0
                if not _parent_alive(parent_pid):
                    break
            if step:
                nxt += step
                wait = nxt - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
                elif wait < -0.25:                              # far behind: no catch-up burst
                    nxt = time.perf_counter()
    except SystemExit:
        raise
    except Exception as e:
        raise _GpuStarted(str(e)) from e
    finally:
        state["done"] = time.time()
        try:
            enc.close()
        except Exception:
            pass


def _burn(worker_pid, gui_pid):
    """Pure-Python CPU burn for a single core. Beendet sich selbst, sobald ENTWEDER
    der Worker (sauberer Stop → .terminate()) ODER die GUI (harter Absturz) weg ist —
    sonst blieben nach dem Stoppen verwaiste Prozesse zurück, die alle Kerne weiter
    auslasten."""
    last = time.time()
    while True:
        _ = sum(i * i for i in range(50000))
        now = time.time()
        if now - last > 1.0:
            last = now
            if not _parent_alive(worker_pid) or not _parent_alive(gui_pid):
                break


def cpu_stress(parent_pid):
    try:
        import numpy as np      # numpy's BLAS lastet bereits alle Kerne aus
        s = 4096
        a = np.random.rand(s, s).astype(np.float32)
        b = np.random.rand(s, s).astype(np.float32)
        last = time.time()
        while True:
            c = np.dot(a, b)
            a = c % 1.0 + 0.001
            now = time.time()
            if now - last > 1.0:
                last = now
                if not _parent_alive(parent_pid):   # GUI weg → nicht ewig weiterlaufen
                    break
    except KeyboardInterrupt:
        pass
    except ImportError:
        # Kein numpy: einen Prozess pro CPU-Kern starten, damit ALLE Kerne
        # geladen werden (umgeht den GIL, der sonst nur 1 Kern auslasten würde).
        # Die Kinder prüfen sowohl den Worker (dieser Prozess) als auch die GUI.
        import multiprocessing as mp
        n = max(1, mp.cpu_count())
        worker_pid = os.getpid()
        procs = [mp.Process(target=_burn, args=(worker_pid, parent_pid), daemon=True)
                 for _ in range(n)]
        for p in procs:
            p.start()
        try:
            for p in procs:
                p.join()
        except KeyboardInterrupt:
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()   # harmlos als Skript, nötig falls jemals eingefroren
    # Parent (GUI) PID from argv[1]; fall back to getppid() if not supplied.
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        parent_pid = int(sys.argv[1])
    else:
        parent_pid = os.getppid()
    mode = sys.argv[2] if len(sys.argv) > 2 else "gemm"
    if mode == "encode":
        # never the CPU fallback: no cupy / NVENC here means "no encoder", not a GPU load
        try:
            encode_stress(parent_pid)
        except _GpuStarted as e:
            _emit("ERR cuda")
            print(f"CUDA/NVENC error under load: {e}", file=sys.stderr)
            sys.exit(EXIT_COMPUTE_ERROR)
        except Exception as e:
            if os.environ.get("GOP_STRESS_GPU_OK") == "1":
                _emit("ERR cuda")
                sys.exit(EXIT_COMPUTE_ERROR)
            _emit(f"NOENC {e}")
            sys.exit(EXIT_NO_ENCODER)
        sys.exit(0)
    try:
        {"mem": mem_stress, "mixed": mixed_stress, "boost": boost_stress, "transient": transient_stress,
         "boost_trans": boost_trans_stress}.get(mode, cuda_stress)(parent_pid)
    except ImportError:
        cpu_stress(parent_pid)            # kein cupy → CPU-Last
    except _GpuStarted as e:
        # The GPU load was already running and CUDA failed (e.g. after a driver
        # reset) — that is an instability signal, not a reason to fall back.
        _emit("ERR cuda")
        print(f"CUDA error under load: {e}", file=sys.stderr)
        sys.exit(EXIT_COMPUTE_ERROR)
    except Exception as e:
        # A CUDA error while setting up (the inputs, the reference product). When the
        # tester's earlier runs got results (GOP_STRESS_GPU_OK), CUDA works on this card:
        # the error comes from the clock just applied — instability, at once, instead of
        # a CPU load that the tester only calls a hang after START_HANG_S.
        if os.environ.get("GOP_STRESS_GPU_OK") == "1":
            _emit("ERR cuda")
            print(f"CUDA error at start-up under a working GPU: {e}", file=sys.stderr)
            sys.exit(EXIT_COMPUTE_ERROR)
        # Echter CUDA-/Laufzeitfehler beim ersten Start: sichtbar machen statt still als "kein CUDA"
        print(f"CUDA stress failed: {e}", file=sys.stderr)
        cpu_stress(parent_pid)
