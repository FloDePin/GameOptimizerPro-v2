"""
GameOptimizerPro v2.0 — audio endpoint settings through the Windows audio API

Windows 11 locks the endpoint property stores in the registry
(HKLM\\...\\MMDevices\\Audio\\Render\\{id}\\Properties / FxProperties): even an
administrator gets "access denied" (verified on 26H2 with a probe value), only
the audio endpoint builder service may write there. The Sound control panel
(and tools like EarTrumpet / SoundVolumeView) therefore go through the
policy-config COM interface, which asks that service to write for them. This
module builds the PowerShell for it (C# compiled with Add-Type):

  * PKEY_AudioEndpoint_Disable_SysFx {1da5d803-...},5 in the FX store:
    ENDPOINT_SYSFX_ENABLED = 0, ENDPOINT_SYSFX_DISABLED = 1 ("audio enhancements")
  * {b3f8fa53-...},3 / ,4 in the endpoint store: "allow applications to take
    exclusive control" / "give exclusive mode applications priority"
"""

from __future__ import annotations

SYSFX = ("{1da5d803-d492-4edd-8c23-e0c0ffee7f0e}", 5)
EXCL_ALLOW = ("{b3f8fa53-0004-438e-9003-51a46e139bfc}", 3)
EXCL_PRIORITY = ("{b3f8fa53-0004-438e-9003-51a46e139bfc}", 4)

CSHARP = r"""
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace GOPAudio {
  [StructLayout(LayoutKind.Sequential)]
  public struct PROPERTYKEY { public Guid fmtid; public int pid; }

  [StructLayout(LayoutKind.Explicit, Size = 24)]
  public struct PROPVARIANT {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public uint uintVal;
    [FieldOffset(8)] public IntPtr ptr;
  }

  [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    [PreserveSig] int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
  }

  [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceCollection {
    [PreserveSig] int GetCount(out uint count);
    [PreserveSig] int Item(uint index, out IMMDevice device);
  }

  [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    [PreserveSig] int Activate(ref Guid iid, int clsCtx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
    [PreserveSig] int OpenPropertyStore(int access, out IntPtr props);
    [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
    [PreserveSig] int GetState(out int state);
  }

  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator { }

  [ComImport, Guid("F8679F50-850A-41CF-9C72-430F290290C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPolicyConfig {
    [PreserveSig] int GetMixFormat([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr fmt);
    [PreserveSig] int GetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string dev, int bDefault, IntPtr fmt);
    [PreserveSig] int ResetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string dev);
    [PreserveSig] int SetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr ep, IntPtr mix);
    [PreserveSig] int GetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string dev, int bDefault, IntPtr d, IntPtr m);
    [PreserveSig] int SetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr p);
    [PreserveSig] int GetShareMode([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr m);
    [PreserveSig] int SetShareMode([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr m);
    [PreserveSig] int GetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string dev, int bFxStore, ref PROPERTYKEY key, out PROPVARIANT pv);
    [PreserveSig] int SetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string dev, int bFxStore, ref PROPERTYKEY key, ref PROPVARIANT pv);
  }

  [ComImport, Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")] class PolicyConfigClient { }

  public static class Fx {
    [DllImport("ole32.dll")] static extern int PropVariantClear(ref PROPVARIANT pv);

    // eRender = 0; DEVICE_STATE_ACTIVE = 1, DEVICE_STATE_UNPLUGGED = 8
    public static string[] RenderIds(int stateMask) {
      var list = new List<string>();
      var en = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
      IMMDeviceCollection col;
      if (en.EnumAudioEndpoints(0, stateMask, out col) != 0) return list.ToArray();
      uint n; col.GetCount(out n);
      for (uint i = 0; i < n; i++) {
        IMMDevice d; if (col.Item(i, out d) != 0) continue;
        string id; if (d.GetId(out id) == 0) list.Add(id);
      }
      return list.ToArray();
    }

    static PROPERTYKEY Key(string fmtid, int pid) {
      var k = new PROPERTYKEY(); k.fmtid = new Guid(fmtid); k.pid = pid; return k;
    }

    // "vt=19 value=1", "vt=0" (not set) or "hr=0x...."
    public static string Get(string id, bool fx, string fmtid, int pid) {
      var pc = (IPolicyConfig)(new PolicyConfigClient());
      var k = Key(fmtid, pid);
      PROPVARIANT pv;
      int hr = pc.GetPropertyValue(id, fx ? 1 : 0, ref k, out pv);
      if (hr != 0) return "hr=0x" + hr.ToString("X8");
      string s = "vt=" + pv.vt + (pv.vt == 19 || pv.vt == 18 || pv.vt == 11 ? " value=" + pv.uintVal : "");
      PropVariantClear(ref pv);
      return s;
    }

    public static int SetUInt(string id, bool fx, string fmtid, int pid, uint value) {
      var pc = (IPolicyConfig)(new PolicyConfigClient());
      var k = Key(fmtid, pid);
      var pv = new PROPVARIANT(); pv.vt = 19; pv.uintVal = value;   // VT_UI4
      return pc.SetPropertyValue(id, fx ? 1 : 0, ref k, ref pv);
    }
  }
}
"""


def _add_type() -> str:
    # A single-quoted here-string: its closing '@ must start a line.
    return "Add-Type -TypeDefinition @'\n" + CSHARP.strip("\n") + "\n'@ -Language CSharp\n"


def ps_report() -> str:
    """Read-only: every render endpoint with the three values (diagnostics)."""
    return _add_type() + (
        "foreach($id in [GOPAudio.Fx]::RenderIds(1 -bor 8)){\n"
        f"  $s=[GOPAudio.Fx]::Get($id,$true,'{SYSFX[0]}',{SYSFX[1]})\n"
        f"  $a=[GOPAudio.Fx]::Get($id,$false,'{EXCL_ALLOW[0]}',{EXCL_ALLOW[1]})\n"
        f"  $p=[GOPAudio.Fx]::Get($id,$false,'{EXCL_PRIORITY[0]}',{EXCL_PRIORITY[1]})\n"
        "  Write-Output \"$id | sysfx $s | excl $a | prio $p\"\n"
        "}\n"
    )


def _ps_set(pairs, ok_text: str, fail_text: str, verify: bool) -> str:
    """pairs: [(fx_store, (fmtid, pid), value)] set on every active/unplugged
    render endpoint; with verify, read back through the same API."""
    body = ""
    for fx, (fmtid, pid), value in pairs:
        f = "$true" if fx else "$false"
        body += (f"  $hr=[GOPAudio.Fx]::SetUInt($id,{f},'{fmtid}',{pid},{value})\n"
                 f"  if($hr -ne 0){{ $bad=\"0x{{0:X8}}\" -f $hr }}\n")
        if verify:
            body += (f"  if([GOPAudio.Fx]::Get($id,{f},'{fmtid}',{pid}) -notmatch 'value={value}$'){{ $bad='readback' }}\n")
    return _add_type() + (
        "$n=0; $ok=0; $errs=@()\n"
        "foreach($id in [GOPAudio.Fx]::RenderIds(1 -bor 8)){\n"
        "  $n++; $bad=$null\n" + body +
        "  if($bad){ $errs+=$bad } else { $ok++ }\n"
        "}\n"
        f"if($ok -gt 0){{ Write-Output \"{ok_text}: $ok von $n Wiedergabegeraet(en)\"; exit 0 }}\n"
        f"Write-Output \"{fail_text} (0 von $n; $($errs | Select-Object -First 1))\"; exit 1\n"
    )


def ps_sysfx(disable: bool) -> str:
    return _ps_set([(True, SYSFX, 1 if disable else 0)],
                   "Audioverbesserungen " + ("aus" if disable else "an"),
                   "Audio-Dienst hat die Einstellung abgelehnt", verify=True)


def ps_exclusive(allow: bool) -> str:
    v = 1 if allow else 0
    return _ps_set([(False, EXCL_ALLOW, v), (False, EXCL_PRIORITY, v)],
                   "Exklusiver Modus " + ("erlaubt" if allow else "aus"),
                   "Audio-Dienst hat die Einstellung abgelehnt", verify=True)
