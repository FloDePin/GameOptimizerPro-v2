"""NVTuner Stress Worker — runs in a subprocess to load the GPU (and CPU as fallback)."""
import sys, os, time


def cuda_stress():
    import cupy as cp
    a = cp.random.rand(8192, 8192, dtype=cp.float32)
    b = cp.random.rand(8192, 8192, dtype=cp.float32)
    while True:
        c = cp.dot(a, b)
        cp.cuda.Stream.null.synchronize()
        a = c % 1.0 + 0.001


def _parent_alive(pid):
    """True solange der Eltern-Prozess lebt.
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


def _burn(parent_pid):
    """Pure-Python CPU burn for a single core. Beendet sich selbst, sobald der
    Eltern-Worker weg ist — sonst blieben nach dem Stoppen des Stresstests
    verwaiste Prozesse zurück, die alle Kerne weiter auslasten."""
    last = time.time()
    while True:
        _ = sum(i * i for i in range(50000))
        now = time.time()
        if now - last > 1.0:
            last = now
            if not _parent_alive(parent_pid):
                break


def cpu_stress():
    try:
        import numpy as np      # numpy's BLAS lastet bereits alle Kerne aus
        s = 4096
        a = np.random.rand(s, s).astype(np.float32)
        b = np.random.rand(s, s).astype(np.float32)
        while True:
            c = np.dot(a, b)
            a = c % 1.0 + 0.001
    except KeyboardInterrupt:
        pass
    except ImportError:
        # Kein numpy: einen Prozess pro CPU-Kern starten, damit ALLE Kerne
        # geladen werden (umgeht den GIL, der sonst nur 1 Kern auslasten würde).
        import multiprocessing as mp
        n = max(1, mp.cpu_count())
        ppid = os.getpid()
        procs = [mp.Process(target=_burn, args=(ppid,), daemon=True) for _ in range(n)]
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
    try:
        cuda_stress()
    except (ImportError, Exception):
        cpu_stress()
