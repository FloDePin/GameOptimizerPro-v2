"""NVTuner Stress Worker — runs in a subprocess to load the GPU (and CPU as fallback).

The parent (GUI) PID is passed as argv[1] so every burn loop can stop itself the
moment the GUI is gone. Without that, a hard GUI crash (not the clean Stop button,
which calls .terminate()) would leave an orphaned process pegging the CPU/GPU at
100% forever. os.getppid() is unreliable here — Windows does not re-parent orphans
and keeps returning the dead parent's PID — so the PID is handed in explicitly.
"""
import sys, os, time


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


def cuda_stress(parent_pid):
    """GPU burn via cupy. Stops when the GUI (parent_pid) is gone — otherwise a
    hard GUI crash would leave the GPU pinned at 100% indefinitely."""
    import cupy as cp
    a = cp.random.rand(8192, 8192, dtype=cp.float32)
    b = cp.random.rand(8192, 8192, dtype=cp.float32)
    last = time.time()
    while True:
        c = cp.dot(a, b)
        cp.cuda.Stream.null.synchronize()
        a = c % 1.0 + 0.001
        now = time.time()
        if now - last > 1.0:
            last = now
            if not _parent_alive(parent_pid):
                break


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
    try:
        cuda_stress(parent_pid)
    except ImportError:
        cpu_stress(parent_pid)            # kein cupy → CPU-Last
    except Exception as e:
        # Echter CUDA-/Laufzeitfehler: sichtbar machen statt still als "kein CUDA"
        print(f"CUDA stress failed: {e}", file=sys.stderr)
        cpu_stress(parent_pid)
