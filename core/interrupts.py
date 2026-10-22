"""
GameOptimizerPro — Interrupt view (read-only)

Per PCI device: does it really run with MSI (Message Signaled Interrupts) or with
the old line interrupt, how many messages it got, and the interrupt priority and
core assignment from the registry. "Really" = the resources Windows allocated
(Win32_PNPAllocatedResource): MSI vectors show up as IRQ numbers >= 2^31, line
interrupts as small numbers. The registry value MSISupported only says what is
requested. Nothing is changed.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from core.i18n import tr as _tr

_PS = r"""
$ErrorActionPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$map=@{}
foreach($r in @(Get-CimInstance Win32_PNPAllocatedResource)){
  $a=$r.Antecedent
  if($a.CimClass.CimClassName -ne 'Win32_IRQResource' -and "$a" -notmatch 'Win32_IRQResource'){ continue }
  $id=[string]$r.Dependent.DeviceID
  if(-not $id -or $id -notmatch '^PCI\\'){ continue }
  if(-not $map.ContainsKey($id)){ $map[$id]=New-Object System.Collections.Generic.List[int64] }
  $map[$id].Add([int64]$a.IRQNumber)
}
$ents=@{}
foreach($e in @(Get-CimInstance Win32_PnPEntity -Property DeviceID,Name,PNPClass,CompatibleID)){
  if("$($e.DeviceID)" -match '^PCI\\'){ $ents[[string]$e.DeviceID]=$e } }
$out=@(foreach($id in $map.Keys){
  $e=$ents[$id]
  $cc=''; foreach($c in @($e.CompatibleID)){ if("$c" -match 'CC_([0-9A-Fa-f]{4})'){ $cc=$matches[1].ToUpper(); break } }
  if($cc -eq '0600' -or $cc -eq '0604'){ continue }
  $b="HKLM:\SYSTEM\CurrentControlSet\Enum\$id\Device Parameters\Interrupt Management"
  $m=Get-ItemProperty -LiteralPath "$b\MessageSignaledInterruptProperties"
  $f=Get-ItemProperty -LiteralPath "$b\Affinity Policy"
  [pscustomobject]@{ id=$id; name=[string]$e.Name; cls=[string]$e.PNPClass; cc=$cc
    irqs=@($map[$id]); msi=$m.MSISupported; limit=$m.MessageNumberLimit
    prio=$f.DevicePriority; policy=$f.DevicePolicy
    mask=$(if($f.AssignmentSetOverride){ [BitConverter]::ToString([byte[]]$f.AssignmentSetOverride) }else{ $null }) }
})
ConvertTo-Json -InputObject $out -Compress -Depth 4
"""

MSI_BASE = 2 ** 31

KIND_ORDER = ("gpu", "network", "storage", "usb", "audio", "other")


def kind_label(kind: str) -> str:
    return {"gpu": _tr("Grafik", "Graphics"), "network": _tr("Netzwerk", "Network"),
            "storage": _tr("Speicher", "Storage"), "usb": "USB", "audio": "Audio",
            "other": _tr("Sonstige", "Other")}[kind]


@dataclass
class IrqDevice:
    name: str
    kind: str                 # see KIND_ORDER
    mode: str                 # "msi" | "line"
    messages: int             # allocated interrupts (MSI vectors or line IRQs)
    line_irqs: list = field(default_factory=list)
    msi_reg: int | None = None        # MSISupported (None = not set)
    limit: int | None = None          # MessageNumberLimit
    priority: int | None = None       # DevicePriority 1 low, 2 normal, 3 high
    policy: int | None = None         # DevicePolicy (IRQ_DEVICE_POLICY)
    cores: list = field(default_factory=list)   # from AssignmentSetOverride
    shared_with: list = field(default_factory=list)
    device_id: str = ""


@dataclass
class InterruptScan:
    ok: bool = False
    devices: list = field(default_factory=list)
    error: str = ""


def _kind(cls: str, cc: str) -> str:
    cc = (cc or "").upper()
    if cc.startswith("03") or cls == "Display":
        return "gpu"
    if cc.startswith("02") or cls == "Net":
        return "network"
    if cc.startswith("01") or cls in ("SCSIAdapter", "HDC"):
        return "storage"
    if cc.startswith("0C03") or cls == "USB":
        return "usb"
    if cc.startswith("04") or cls == "MEDIA":
        return "audio"
    return "other"


def mask_cores(mask: str | None) -> list[int]:
    """'01-00-00-00-00-00-00-00' (little-endian bytes) -> [0]."""
    if not mask:
        return []
    try:
        val = int.from_bytes(bytes(int(b, 16) for b in mask.split("-")), "little")
    except ValueError:
        return []
    return [i for i in range(val.bit_length()) if val >> i & 1]


def parse(rows) -> list[IrqDevice]:
    if isinstance(rows, dict):          # ConvertTo-Json of a single item
        rows = [rows]
    devs: list[IrqDevice] = []
    for r in rows or []:
        irqs = [int(x) for x in (r.get("irqs") or []) if x is not None]
        irqs = [x & 0xFFFFFFFF for x in irqs]
        msi = any(x >= MSI_BASE for x in irqs)

        def _int(k):
            v = r.get(k)
            try:
                return None if v is None else int(v)
            except (TypeError, ValueError):
                return None
        devs.append(IrqDevice(
            name=str(r.get("name") or r.get("id") or "?"), kind=_kind(str(r.get("cls") or ""), str(r.get("cc") or "")),
            mode="msi" if msi else "line", messages=len(irqs),
            line_irqs=sorted(x for x in irqs if x < MSI_BASE), msi_reg=_int("msi"), limit=_int("limit"),
            priority=_int("prio"), policy=_int("policy"), cores=mask_cores(r.get("mask")),
            device_id=str(r.get("id") or "")))
    # line interrupts used by more than one device
    for d in devs:
        if d.mode == "line":
            d.shared_with = [o.name for o in devs if o is not d and o.mode == "line"
                             and set(o.line_irqs) & set(d.line_irqs)]
    devs.sort(key=lambda d: (KIND_ORDER.index(d.kind), d.mode != "line", d.name.lower()))
    return devs


def scan() -> InterruptScan:
    res = InterruptScan()
    if os.name != "nt":
        res.error = _tr("Nur unter Windows verfügbar.", "Only available on Windows.")
        return res
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", _PS], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (r.stdout or "").strip()
        res.devices = parse(json.loads(out) if out else [])
    except Exception as e:
        res.error = _tr(f"Abfrage fehlgeschlagen: {e}", f"Query failed: {e}")
        return res
    if not res.devices:
        res.error = _tr("Keine PCI-Geräte mit Interrupts gefunden (Rechte?).",
                        "No PCI devices with interrupts found (rights?).")
        return res
    res.ok = True
    return res


# ── texts ─────────────────────────────────────────────────────────────────────

def mode_text(d: IrqDevice) -> str:
    if d.mode == "msi":
        return "MSI"
    irq = ", ".join(str(x) for x in d.line_irqs[:2]) or "?"
    return _tr(f"Leitung (IRQ {irq})", f"Line (IRQ {irq})")


def priority_text(p: int | None) -> str:
    return {1: _tr("niedrig", "low"), 2: "normal", 3: _tr("hoch", "high")}.get(p or 0, _tr("Standard", "default"))


def cores_text(d: IrqDevice) -> str:
    pol = d.policy or 0
    if pol == 4:
        return (_tr("fest: Kern ", "fixed: core ") + ", ".join(str(c) for c in d.cores)) if d.cores \
            else _tr("fest (ohne Maske)", "fixed (no mask)")
    return {0: _tr("Windows-Standard", "Windows default"), 1: _tr("nahe Kerne", "close cores"),
            2: _tr("ein naher Kern", "one close core"), 3: _tr("alle Kerne", "all cores"),
            5: _tr("verteilt auf alle Kerne", "spread over all cores")}.get(pol, f"Policy {pol}")


def notes(d: IrqDevice) -> list[tuple[str, str]]:
    """(level, text) worth saying about one device: 'warning' | 'info' | 'success'."""
    out = []
    if d.mode == "line":
        if d.msi_reg == 0:
            out.append(("info", _tr(
                "Der Treiber schaltet MSI ausdrücklich ab (MSISupported = 0). So lassen — erzwungenes MSI "
                "kann das Gerät am Start hindern.",
                "The driver turns MSI off on purpose (MSISupported = 0). Leave it — forcing MSI can stop "
                "the device from starting.")))
        elif d.kind == "gpu":
            out.append(("warning", _tr(
                "Läuft über den alten Leitungs-Interrupt. Der Tweak 'Enable MSI Mode' (Optimizer → Gaming → "
                "GPU & Driver) schaltet MSI ein — wirkt nach einem Neustart.",
                "Runs on the old line interrupt. The tweak 'Enable MSI Mode' (Optimizer → Gaming → GPU & "
                "Driver) turns MSI on — takes effect after a restart.")))
        elif d.msi_reg == 1:
            out.append(("warning", _tr(
                "MSI ist angefordert, Windows hat aber einen Leitungs-Interrupt vergeben — meist fehlt ein "
                "Neustart, sonst unterstützt das Gerät MSI nicht.",
                "MSI is requested, but Windows gave it a line interrupt — usually a restart is missing, "
                "otherwise the device does not support MSI.")))
        if d.shared_with:
            out.append(("warning", _tr("Teilt sich den Interrupt mit: ", "Shares the interrupt with: ")
                        + ", ".join(d.shared_with[:3])))
    if (d.policy or 0) == 4 or (d.priority or 0) in (1, 3) and d.kind in ("gpu", "network", "usb"):
        out.append(("info", _tr(
            "Eigene Interrupt-Einstellung gesetzt (Priorität/Kerne) — von Hand, vom Treiber oder einem Tool.",
            "A custom interrupt setting is set (priority / cores) — by hand, by the driver or by a tool.")))
    return out


def summary(devs: list[IrqDevice]) -> str:
    msi = sum(1 for d in devs if d.mode == "msi")
    line = len(devs) - msi
    return _tr(f"{len(devs)} Geräte: {msi} mit MSI, {line} mit Leitungs-Interrupt",
               f"{len(devs)} devices: {msi} with MSI, {line} with a line interrupt")
