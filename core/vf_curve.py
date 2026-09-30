"""
GameOptimizerPro v2.1 — V/F curve undervolt helpers (voltage stepping).

The curve itself is written by core/ab_profile.py (VFCurve.with_flatline) into
Afterburner's real profile file. That writer works on the card's actual curve
points (voltage + base frequency per point, read from the profile) instead of
the invented 512-point offset list this module used to produce — Afterburner
never read that one.

Method (how undervolting is done by hand):
1. Target frequency = Stage-1 result (e.g. 2700 MHz).
2. Step the lock voltage down until the stress test fails.
3. Flat curve: from the lock voltage upwards every point runs the target
   frequency, so the GPU never boosts past that voltage.

  Freq ▲
  2700 │           ████████████  ← flat at the target frequency
       │      █████
       │  ████
       └──────────────────────▶ Volt
          750  850  950  1050
"""


class VFCurveBuilder:
    """Voltage steps for the Stage-3 search."""

    UV_STEP_MV = 25   # 25 mV steps — precise without being slow

    def __init__(self, gpu_generation: str = "Ada"):
        self.gen = gpu_generation

    def get_uv_test_voltages(
        self,
        start_voltage_mv: int,
        min_voltage_mv:   int = 750,
    ) -> list[int]:
        """
        Voltages to test (high → low). Starts one step below start_voltage_mv.
        min_voltage_mv: lower bound (below ~750 mV an RTX 4080 is unstable).
        """
        voltages = []
        v = start_voltage_mv - self.UV_STEP_MV
        while v >= min_voltage_mv:
            voltages.append(v)
            v -= self.UV_STEP_MV
        return voltages

    def recommend_start_voltage(self, avg_voltage_mv: float) -> int:
        """
        Start voltage for the UV search from the measured load voltage:
        rounded down to 25 mV, then two steps lower (conservative).
        """
        rounded = int(avg_voltage_mv / self.UV_STEP_MV) * self.UV_STEP_MV
        return max(750, rounded - self.UV_STEP_MV * 2)


def get_builder_for_gpu(gpu_name: str) -> VFCurveBuilder:
    """Builder for the detected GPU generation."""
    gpu_upper = gpu_name.upper()
    if "RTX 40" in gpu_upper:
        return VFCurveBuilder("Ada Lovelace")
    elif "RTX 30" in gpu_upper:
        return VFCurveBuilder("Ampere")
    elif "RTX 20" in gpu_upper or "GTX 16" in gpu_upper:
        return VFCurveBuilder("Turing")
    else:
        return VFCurveBuilder("Ada")  # conservative default
