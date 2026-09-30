"""numpy-backed stand-in for cupy (tests only). Env knobs:
FAKE_CORRUPT_DOT=n   corrupt the n-th dot() result
FAKE_CORRUPT_COPY=n  corrupt the n-th copyto()
FAKE_RAISE_DOT=n     raise a CUDA-like error on the n-th dot()
FAKE_INIT_FAIL=1     fail while allocating (-> 'no usable CUDA' path)"""
import os as _os
import numpy as _np

float32 = _np.float32
_calls = {"dot": 0, "copy": 0}
_E = lambda k: int(_os.environ.get(k, "0"))


class _Random:
    @staticmethod
    def rand(*shape, dtype=_np.float64):
        if _E("FAKE_INIT_FAIL"):
            raise RuntimeError("cudaErrorNoDevice (fake)")
        return _np.random.RandomState(1).rand(*shape).astype(dtype)


random = _Random()


def dot(a, b, out=None):
    _calls["dot"] += 1
    if _E("FAKE_RAISE_DOT") and _calls["dot"] == _E("FAKE_RAISE_DOT"):
        raise RuntimeError("cudaErrorLaunchFailure (fake)")
    r = _np.dot(a, b, out=out)
    if _E("FAKE_CORRUPT_DOT") and _calls["dot"] == _E("FAKE_CORRUPT_DOT"):
        r[3, 5] += 1.0
    return r


def copyto(dst, src):
    _calls["copy"] += 1
    _np.copyto(dst, src)
    if _E("FAKE_CORRUPT_COPY") and _calls["copy"] == _E("FAKE_CORRUPT_COPY"):
        dst[7] += 1.0


empty_like = _np.empty_like
abs = _np.abs
count_nonzero = _np.count_nonzero
array_equal = _np.array_equal


class _Null:
    @staticmethod
    def synchronize():
        pass


class _Stream:
    null = _Null


class cuda:
    Stream = _Stream
