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


def _burn(parent_pid):
    """Pure-Python CPU burn for a single core. Beendet sich selbst, sobald der
    Eltern-Worker weg ist — sonst blieben nach dem Stoppen des Stresstests
    verwaiste Prozesse zurück, die alle Kerne weiter auslasten."""
    try:
        import psutil
    except Exception:
        psutil = None
    last = time.time()
    while True:
        _ = sum(i * i for i in range(50000))
        now = time.time()
        if now - last > 1.0:
            last = now
            if psutil is not None and not psutil.pid_exists(parent_pid):
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
