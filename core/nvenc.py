"""
GameOptimizerPro v2.0 — NVIDIA video encoder (NVENC) through the driver's own
nvEncodeAPI64.dll (round 33).

What recording / streaming puts on the card next to a game: OBS, NVIDIA's Instant
Replay or Discord encode every frame on the NVENC engine. The hardness test
(core/hardness_test.py) runs that next to a 3D and a compute load — the tuner's
single loads never had the encoder, the graphics and the compute engine busy at
the same time.

No extra package: the structs below follow NVIDIA's nvEncodeAPI.h. The layout is
the one of API 6; API 10 (the first with the P1–P7 presets) only gave
NV_ENC_INITIALIZE_PARAMS a `tuningInfo` in its first reserved word — same sizes,
same struct versions. The driver takes clients of older APIs (it says which API
it supports up to: NvEncodeAPIGetMaxSupportedVersion).

Input frames are CUDA device buffers (NV12) of the caller's CUDA context, as OBS
does it with "GPU scaling": the frame never leaves the card.
"""

from __future__ import annotations

import ctypes as C
from typing import Optional

u32, u64, vp = C.c_uint32, C.c_uint64, C.c_void_p

API_MAJOR, API_MINOR = 10, 0
API = API_MAJOR | (API_MINOR << 24)

SUCCESS = 0
ERR_NEED_MORE_INPUT = 17
DEVICE_CUDA = 1
RESOURCE_CUDADEVICEPTR = 1
FMT_NV12 = 1
PIC_STRUCT_FRAME = 1
PIC_FLAG_EOS = 0x8
TUNING_HIGH_QUALITY, TUNING_LOW_LATENCY = 1, 2

ERRORS = {1: "no encode device", 2: "unsupported device", 3: "invalid encoder device", 4: "invalid device",
          5: "device does not exist", 6: "invalid pointer", 7: "invalid event", 8: "invalid parameter",
          9: "invalid call", 10: "out of memory", 11: "encoder not initialized", 12: "unsupported parameter",
          13: "lock busy", 14: "not enough buffer", 15: "invalid version", 16: "map failed",
          17: "need more input", 18: "encoder busy", 19: "event not registered", 20: "generic error",
          21: "incompatible client key", 22: "unimplemented", 23: "resource register failed",
          24: "resource not registered", 25: "resource not mapped"}


def _sv(ver: int) -> int:
    """NVENCAPI_STRUCT_VERSION"""
    return API | (ver << 16) | (0x7 << 28)


class GUID(C.Structure):
    _fields_ = [("d1", u32), ("d2", C.c_uint16), ("d3", C.c_uint16), ("d4", C.c_uint8 * 8)]


def _guid(d1, d2, d3, *d4) -> GUID:
    return GUID(d1, d2, d3, (C.c_uint8 * 8)(*d4))


CODECS = {
    "h264": _guid(0x6bc82762, 0x4e63, 0x4ca4, 0xaa, 0x85, 0x1e, 0x50, 0xf3, 0x21, 0xf6, 0xbf),
    "hevc": _guid(0x790cdc88, 0x4522, 0x4d7b, 0x94, 0x25, 0xbd, 0xa9, 0x97, 0x5f, 0x76, 0x03),
}
PRESETS = {     # P1 (fastest) … P7 (slowest, best quality); OBS streams with P5 by default
    1: _guid(0xfc0a8d3e, 0x45f8, 0x4cf8, 0x80, 0xc7, 0x29, 0x88, 0x71, 0x59, 0x0e, 0xbf),
    2: _guid(0xf581cfb8, 0x88d6, 0x4381, 0x93, 0xf0, 0xdf, 0x13, 0xf9, 0xc2, 0x7d, 0xab),
    3: _guid(0x36850110, 0x3a07, 0x441f, 0x94, 0xd5, 0x36, 0x70, 0x63, 0x1f, 0x91, 0xf6),
    4: _guid(0x90a7b826, 0xdf06, 0x4862, 0xb9, 0xd2, 0xcd, 0x6d, 0x73, 0xa0, 0x86, 0x81),
    5: _guid(0x21c6e6b4, 0x297a, 0x4cba, 0x99, 0x8f, 0xb6, 0xcb, 0xde, 0x72, 0xad, 0xe3),
    6: _guid(0x8e75c279, 0x6299, 0x4ab6, 0x83, 0x02, 0x0b, 0x21, 0x5a, 0x33, 0x5c, 0xf5),
    7: _guid(0x84848c12, 0x6f71, 0x4c13, 0x93, 0x1b, 0x53, 0xe2, 0x83, 0xf5, 0x79, 0x74),
}

_FUNCS = ["OpenEncodeSession", "GetEncodeGUIDCount", "GetEncodeProfileGUIDCount", "GetEncodeProfileGUIDs",
          "GetEncodeGUIDs", "GetInputFormatCount", "GetInputFormats", "GetEncodeCaps", "GetEncodePresetCount",
          "GetEncodePresetGUIDs", "GetEncodePresetConfig", "InitializeEncoder", "CreateInputBuffer",
          "DestroyInputBuffer", "CreateBitstreamBuffer", "DestroyBitstreamBuffer", "EncodePicture",
          "LockBitstream", "UnlockBitstream", "LockInputBuffer", "UnlockInputBuffer", "GetEncodeStats",
          "GetSequenceParams", "RegisterAsyncEvent", "UnregisterAsyncEvent", "MapInputResource",
          "UnmapInputResource", "DestroyEncoder", "InvalidateRefFrames", "OpenEncodeSessionEx",
          "RegisterResource", "UnregisterResource", "ReconfigureEncoder", "reserved1", "CreateMVBuffer",
          "DestroyMVBuffer", "RunMotionEstimationOnly"]


class _FunctionList(C.Structure):
    _fields_ = [("version", u32), ("reserved", u32)] + [(n, vp) for n in _FUNCS] + [("reserved2", vp * 281)]


class _MeHintCounts(C.Structure):
    _fields_ = [("bits", u32), ("reserved1", u32 * 3)]


class _OpenParams(C.Structure):
    _fields_ = [("version", u32), ("deviceType", u32), ("device", vp), ("reserved", vp),
                ("apiVersion", u32), ("reserved1", u32 * 253), ("reserved2", vp * 64)]


class _InitParams(C.Structure):
    _fields_ = [("version", u32), ("encodeGUID", GUID), ("presetGUID", GUID), ("encodeWidth", u32),
                ("encodeHeight", u32), ("darWidth", u32), ("darHeight", u32), ("frameRateNum", u32),
                ("frameRateDen", u32), ("enableEncodeAsync", u32), ("enablePTD", u32), ("bitFields", u32),
                ("privDataSize", u32), ("privData", vp), ("encodeConfig", vp), ("maxEncodeWidth", u32),
                ("maxEncodeHeight", u32), ("maxMEHintCountsPerBlock", _MeHintCounts * 2),
                ("tuningInfo", u32), ("reserved", u32 * 288), ("reserved2", vp * 64)]


class _BitstreamBuffer(C.Structure):
    _fields_ = [("version", u32), ("size", u32), ("memoryHeap", u32), ("reserved", u32),
                ("bitstreamBuffer", vp), ("bitstreamBufferPtr", vp), ("reserved1", u32 * 58),
                ("reserved2", vp * 64)]


class _RegisterResource(C.Structure):
    _fields_ = [("version", u32), ("resourceType", u32), ("width", u32), ("height", u32), ("pitch", u32),
                ("subResourceIndex", u32), ("resourceToRegister", vp), ("registeredResource", vp),
                ("bufferFormat", u32), ("reserved1", u32 * 248), ("reserved2", vp * 62)]


class _MapInput(C.Structure):
    _fields_ = [("version", u32), ("subResourceIndex", u32), ("inputResource", vp),
                ("registeredResource", vp), ("mappedResource", vp), ("mappedBufferFmt", u32),
                ("reserved1", u32 * 251), ("reserved2", vp * 63)]


class _PicParams(C.Structure):
    _fields_ = [("version", u32), ("inputWidth", u32), ("inputHeight", u32), ("inputPitch", u32),
                ("encodePicFlags", u32), ("frameIdx", u32), ("inputTimeStamp", u64), ("inputDuration", u64),
                ("inputBuffer", vp), ("outputBitstream", vp), ("completionEvent", vp), ("bufferFmt", u32),
                ("pictureStruct", u32), ("pictureType", u32), ("codecPicParams", u32 * 256),
                ("meHintCountsPerBlock", _MeHintCounts * 2), ("meExternalHints", vp), ("reserved1", u32 * 6),
                ("reserved2", vp * 2), ("qpDeltaMap", vp), ("qpDeltaMapSize", u32), ("reservedBitFields", u32),
                ("reserved3", u32 * 287), ("reserved4", vp * 60)]


class _LockBitstream(C.Structure):
    _fields_ = [("version", u32), ("bitFields", u32), ("outputBitstream", vp), ("sliceOffsets", vp),
                ("frameIdx", u32), ("hwEncodeStatus", u32), ("numSlices", u32), ("bitstreamSizeInBytes", u32),
                ("outputTimeStamp", u64), ("outputDuration", u64), ("bitstreamBufferPtr", vp),
                ("pictureType", u32), ("pictureStruct", u32), ("frameAvgQP", u32), ("frameSatd", u32),
                ("ltrFrameIdx", u32), ("ltrFrameBitmap", u32), ("reserved", u32 * 236), ("reserved2", vp * 64)]


# sizes of the header's structs on x64 — a wrong field list would shift what the driver reads
STRUCT_SIZES = {_OpenParams: 1552, _InitParams: 1808, _BitstreamBuffer: 776, _RegisterResource: 1536,
                _MapInput: 1544, _PicParams: 2832, _LockBitstream: 1544, _FunctionList: 2552}


class NvencError(Exception):
    def __init__(self, where: str, code: int):
        self.where, self.code = where, code
        super().__init__(f"{where}: {ERRORS.get(code, code)} ({code})")


class Unavailable(Exception):
    """No NVENC here (no NVIDIA driver, too old, no session free) — not a fault of the card."""


def _load():
    try:
        return C.WinDLL("nvEncodeAPI64.dll")
    except (OSError, AttributeError) as e:
        raise Unavailable(f"nvEncodeAPI64.dll: {e}") from e


def max_api() -> tuple[int, int]:
    """The newest NVENC API the driver supports, (0, 0) = none."""
    try:
        lib = _load()
        v = u32()
        if lib.NvEncodeAPIGetMaxSupportedVersion(C.byref(v)) != SUCCESS:
            return 0, 0
        return v.value >> 4, v.value & 0xF
    except Unavailable:
        return 0, 0


class Encoder:
    """One encode session on the caller's CUDA context. `slots` input surfaces
    (NV12, CUDA device memory, `pitch` bytes a row) and as many bitstream buffers:
    with B-frames the encoder answers "need more input" and the frames come out
    later, in the order they went in — a slot stays busy until its frame is out.

        enc = Encoder(cuda_ctx, 2560, 1440)
        enc.register(i, device_ptr)            # for every slot
        sizes = enc.encode(i)                  # frame in slot i -> sizes of the frames done
        enc.close()
    """

    def __init__(self, cuda_ctx: int, width: int, height: int, codec: str = "h264", fps: int = 60,
                 preset: int = 5, tuning: int = TUNING_HIGH_QUALITY, slots: int = 8, pitch: int = 0):
        for cls, size in STRUCT_SIZES.items():
            if C.sizeof(cls) != size:
                raise Unavailable(f"struct {cls.__name__}: {C.sizeof(cls)} bytes, expected {size}")
        if max_api() < (API_MAJOR, API_MINOR):
            raise Unavailable(f"driver NVENC API {max_api()} < {API_MAJOR}.{API_MINOR}")
        lib = _load()
        self._fl = _FunctionList(version=_sv(2))
        st = lib.NvEncodeAPICreateInstance(C.byref(self._fl))
        if st != SUCCESS:
            raise Unavailable(f"NvEncodeAPICreateInstance: {ERRORS.get(st, st)}")
        P = vp
        f = self._fn
        self._open = f("OpenEncodeSessionEx", C.POINTER(_OpenParams), C.POINTER(vp))
        self._init = f("InitializeEncoder", P, C.POINTER(_InitParams))
        self._mkbits = f("CreateBitstreamBuffer", P, C.POINTER(_BitstreamBuffer))
        self._delbits = f("DestroyBitstreamBuffer", P, vp)
        self._reg = f("RegisterResource", P, C.POINTER(_RegisterResource))
        self._unreg = f("UnregisterResource", P, vp)
        self._map = f("MapInputResource", P, C.POINTER(_MapInput))
        self._unmap = f("UnmapInputResource", P, vp)
        self._enc = f("EncodePicture", P, C.POINTER(_PicParams))
        self._lock = f("LockBitstream", P, C.POINTER(_LockBitstream))
        self._unlock = f("UnlockBitstream", P, vp)
        self._destroy = f("DestroyEncoder", P)
        self.width, self.height, self.pitch = int(width), int(height), int(pitch or width)
        self.slots = int(slots)
        self._e = vp()
        st = self._open(C.byref(_OpenParams(version=_sv(1), deviceType=DEVICE_CUDA, device=cuda_ctx,
                                            apiVersion=API)), C.byref(self._e))
        if st != SUCCESS or not self._e.value:
            # e.g. the GeForce limit of parallel sessions reached (other programs encoding)
            raise Unavailable(f"open session: {ERRORS.get(st, st)}")
        self._bits: list = []
        self._regs: list = [None] * self.slots
        self._pending: list = []          # [(slot, mapped input)] submitted, not out yet
        self._n = 0
        try:
            ip = _InitParams(version=_sv(5) | (1 << 31), encodeGUID=CODECS.get(codec, CODECS["h264"]),
                             presetGUID=PRESETS.get(preset, PRESETS[5]), encodeWidth=self.width,
                             encodeHeight=self.height, darWidth=self.width, darHeight=self.height,
                             frameRateNum=int(fps or 60), frameRateDen=1, enablePTD=1, tuningInfo=tuning)
            self._check("initialize", self._init(self._e, C.byref(ip)), unavailable=True)
            for _ in range(self.slots):
                bb = _BitstreamBuffer(version=_sv(1), size=max(1 << 20, self.width * self.height * 2))
                self._check("bitstream buffer", self._mkbits(self._e, C.byref(bb)))
                self._bits.append(bb.bitstreamBuffer)
        except Exception:
            self.close()
            raise

    def _fn(self, name, *args):
        return C.WINFUNCTYPE(C.c_int, *args)(getattr(self._fl, name))

    def _check(self, where: str, st: int, unavailable: bool = False):
        if st != SUCCESS:
            if unavailable:
                raise Unavailable(f"{where}: {ERRORS.get(st, st)}")
            raise NvencError(where, st)

    def register(self, slot: int, device_ptr: int):
        rr = _RegisterResource(version=_sv(3), resourceType=RESOURCE_CUDADEVICEPTR, width=self.width,
                               height=self.height, pitch=self.pitch, resourceToRegister=device_ptr,
                               bufferFormat=FMT_NV12)
        self._check("register", self._reg(self._e, C.byref(rr)))
        self._regs[slot] = rr.registeredResource

    def busy(self, slot: int) -> bool:
        """The slot's frame is still in the encoder (B-frame order): don't overwrite it."""
        return any(s == slot for s, _m in self._pending)

    def encode(self, slot: int) -> list:
        """Encode the frame in `slot` -> the byte sizes of the frames that came out."""
        if self.busy(slot) or len(self._pending) >= self.slots:
            raise NvencError("pipeline full", ERR_NEED_MORE_INPUT)
        mp = _MapInput(version=_sv(4), registeredResource=self._regs[slot])
        self._check("map", self._map(self._e, C.byref(mp)))
        pp = _PicParams(version=_sv(4) | (1 << 31), inputWidth=self.width, inputHeight=self.height,
                        inputPitch=self.pitch, inputBuffer=mp.mappedResource, outputBitstream=self._bits[slot],
                        bufferFmt=mp.mappedBufferFmt or FMT_NV12, pictureStruct=PIC_STRUCT_FRAME,
                        frameIdx=self._n, inputTimeStamp=self._n)
        self._n += 1
        self._pending.append((slot, mp.mappedResource))
        st = self._enc(self._e, C.byref(pp))
        if st == ERR_NEED_MORE_INPUT:
            return []
        self._check("encode", st)
        return self._drain()

    def _drain(self) -> list:
        out = []
        while self._pending:
            slot, mapped = self._pending.pop(0)
            lb = _LockBitstream(version=_sv(1), outputBitstream=self._bits[slot])
            st = self._lock(self._e, C.byref(lb))
            if st == SUCCESS:
                out.append(int(lb.bitstreamSizeInBytes))
                self._unlock(self._e, self._bits[slot])
            self._unmap(self._e, mapped)
            self._check("lock bitstream", st)
        return out

    def flush(self) -> list:
        """End of stream: the frames still held back come out."""
        if not self._e.value:
            return []
        pp = _PicParams(version=_sv(4) | (1 << 31), encodePicFlags=PIC_FLAG_EOS)
        st = self._enc(self._e, C.byref(pp))
        if st not in (SUCCESS, ERR_NEED_MORE_INPUT):
            raise NvencError("flush", st)
        return self._drain()

    def close(self):
        if not self._e.value:
            return
        try:
            self.flush()
        except Exception:
            pass
        for _slot, mapped in self._pending:
            try:
                self._unmap(self._e, mapped)
            except Exception:
                pass
        self._pending = []
        for r in self._regs:
            if r:
                try:
                    self._unreg(self._e, r)
                except Exception:
                    pass
        for b in self._bits:
            try:
                self._delbits(self._e, b)
            except Exception:
                pass
        try:
            self._destroy(self._e)
        except Exception:
            pass
        self._e = vp()


def available() -> Optional[str]:
    """None when an encode session can be opened here, else why not (no GPU load)."""
    a = max_api()
    if a == (0, 0):
        return "no NVENC driver"
    if a < (API_MAJOR, API_MINOR):
        return f"NVENC API {a[0]}.{a[1]} too old"
    return None
