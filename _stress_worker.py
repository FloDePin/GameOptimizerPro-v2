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
  "mem"             copies two large buffers back and forth and prints
                    "BW <GB/s>". GDDR6X corrects transfer errors by retrying, so a
                    memory overclock past its limit shows up as LOST bandwidth, not
                    as a crash; every 50th round trip is verified against a copy.
On an error the worker prints "ERR <n>" and exits with code 3.
"""
import sys, os, time

EXIT_COMPUTE_ERROR = 3
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
        alive_at = time.time()
        while True:
            end, last, iters = time.time() + HEAVY_S, time.time(), 0
            while time.time() < end:                      # heavy: power-limited
                _gemm_checked(cp, heavy)
                iters += 1
                now = time.time()
                if now - last >= 1.0:
                    _emit(f"RATE {flop * iters / (now - last) / 1e12:.3f}")
                    last, iters = now, 0
            end = time.time() + BOOST_S
            while time.time() < end:                      # boost: top of the curve
                t = time.perf_counter()
                _gemm_checked(cp, light)
                time.sleep((time.perf_counter() - t) * BOOST_PAUSE)
                if time.time() - alive_at >= 1.0:
                    alive_at = time.time()
                    if not _parent_alive(parent_pid):
                        return
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
        while True:
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
        while True:
            t = time.time()
            cp.copyto(b, a)
            cp.copyto(a, b)
            cp.cuda.Stream.null.synchronize()
            busy += time.time() - t
            moved += 4 * a.nbytes               # 2 copies x (read + write)
            k += 1
            if k % 50 == 0 and not bool(cp.array_equal(a, ref)):
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
    try:
        {"mem": mem_stress, "mixed": mixed_stress}.get(mode, cuda_stress)(parent_pid)
    except ImportError:
        cpu_stress(parent_pid)            # kein cupy → CPU-Last
    except _GpuStarted as e:
        # The GPU load was already running and CUDA failed (e.g. after a driver
        # reset) — that is an instability signal, not a reason to fall back.
        _emit("ERR cuda")
        print(f"CUDA error under load: {e}", file=sys.stderr)
        sys.exit(EXIT_COMPUTE_ERROR)
    except Exception as e:
        # Echter CUDA-/Laufzeitfehler beim Start: sichtbar machen statt still als "kein CUDA"
        print(f"CUDA stress failed: {e}", file=sys.stderr)
        cpu_stress(parent_pid)
