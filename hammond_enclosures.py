"""Hammond 1551 Series Enclosure Database — instant PCB-to-enclosure matching.

Mimics the CircuitShell approach: when a PCB is dropped, match it against
standard Hammond enclosures and suggest the best fit. Zero AI needed.

1551 Series: General Purpose ABS (UL94-HB), IP54, 22 models across F–R series.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Enclosure1551:
    series: str                       # e.g. "1551F"
    variant: str                      # "standard" | "flanged"
    part_suffix: str                  # base part code e.g. "1551F"
    ext_length: float                 # mm
    ext_width: float                  # mm
    ext_height: float                 # mm
    int_length: float                 # mm
    int_width: float                  # mm
    int_height: float                 # mm
    pcb_max_length: float             # mm
    pcb_max_width: float              # mm
    colors: List[str] = field(default_factory=lambda: ["BK", "GY", "TBU"])

    @property
    def ext_volume_cm3(self) -> float:
        return (self.ext_length * self.ext_width * self.ext_height) / 1000.0

    @property
    def part_numbers(self) -> List[str]:
        return [f"{self.part_suffix}{c}" for c in self.colors]

    @property
    def display_name(self) -> str:
        suffix = " (Flanged)" if self.variant == "flanged" else ""
        return f"{self.part_suffix}{suffix}"

    def fits_pcb(self, pcb_l: float, pcb_w: float, margin: float = 0.0) -> bool:
        need_l = pcb_l + margin
        need_w = pcb_w + margin
        return (self.pcb_max_length >= need_l and self.pcb_max_width >= need_w) or \
               (self.pcb_max_length >= need_w and self.pcb_max_width >= need_l)

    def fit_score(self, pcb_l: float, pcb_w: float) -> float:
        enc_area = self.pcb_max_length * self.pcb_max_width
        pcb_area = pcb_l * pcb_w
        return enc_area - pcb_area


HAMMOND_1551: List[Enclosure1551] = [
    Enclosure1551("1551F",  "standard", "1551F",   50.00, 35.00, 15.00, 45.17, 30.17, 11.00, 44.50, 29.50),
    Enclosure1551("1551F",  "flanged",  "1551FFL", 67.30, 35.00, 15.00, 45.17, 30.17, 11.00, 44.50, 29.50),
    Enclosure1551("1551G",  "standard", "1551G",   50.00, 35.00, 20.00, 44.73, 29.73, 16.00, 44.00, 29.00),
    Enclosure1551("1551G",  "flanged",  "1551GFL", 67.30, 35.00, 20.00, 44.73, 29.73, 16.00, 44.00, 29.00),
    Enclosure1551("1551H",  "standard", "1551H",   60.00, 35.00, 20.00, 54.73, 29.73, 16.00, 54.00, 29.00),
    Enclosure1551("1551H",  "flanged",  "1551HFL", 76.30, 35.00, 20.00, 54.73, 29.73, 16.00, 54.00, 29.00),
    Enclosure1551("1551J",  "flanged",  "1551JFL", 76.30, 35.00, 15.00, 55.17, 30.17, 11.00, 54.50, 29.50),
    Enclosure1551("1551K",  "standard", "1551K",   80.00, 40.00, 20.00, 74.73, 34.73, 16.00, 74.00, 34.00),
    Enclosure1551("1551K",  "flanged",  "1551KFL", 96.30, 40.00, 20.00, 74.73, 34.73, 16.00, 74.00, 34.00),
    Enclosure1551("1551L",  "standard", "1551L",   80.00, 40.00, 15.00, 75.17, 35.17, 11.00, 74.50, 34.50),
    Enclosure1551("1551L",  "flanged",  "1551LFL", 96.30, 40.00, 15.00, 75.17, 35.17, 11.00, 74.50, 34.50),
    Enclosure1551("1551M",  "standard", "1551M",   35.00, 35.00, 20.00, 29.73, 29.73, 16.00, 29.00, 29.00),
    Enclosure1551("1551N",  "standard", "1551N",   35.00, 35.00, 15.00, 30.17, 30.17, 11.00, 29.00, 29.00),
    Enclosure1551("1551N",  "flanged",  "1551NFL", 51.30, 35.00, 15.00, 30.17, 30.17, 11.00, 29.00, 29.00),
    Enclosure1551("1551P",  "standard", "1551P",   40.00, 40.00, 20.00, 34.72, 34.72, 16.00, 34.00, 34.00),
    Enclosure1551("1551Q",  "standard", "1551Q",   40.00, 40.00, 15.00, 35.12, 35.12, 11.00, 34.50, 34.50),
    Enclosure1551("1551Q",  "flanged",  "1551QFL", 56.30, 40.00, 15.00, 35.12, 35.12, 11.00, 34.50, 34.50),
    Enclosure1551("1551R",  "standard", "1551R",   50.00, 50.00, 20.00, 44.72, 44.72, 16.00, 44.00, 44.00),
    Enclosure1551("1551R",  "flanged",  "1551RFL", 66.30, 50.00, 20.00, 44.72, 44.72, 16.00, 44.00, 44.00),
]


@dataclass
class MatchResult:
    enclosure: Enclosure1551
    fit_score: float          # lower = tighter fit
    orientation: str          # "normal" | "rotated"
    unused_area_mm2: float
    headroom_mm: float


def match_enclosure(pcb_length: float, pcb_width: float,
                    component_height: float = 0.0, margin: float = 0.5,
                    top_n: int = 3) -> List[MatchResult]:
    """Find the best-fitting Hammond 1551 enclosure for a given PCB.

    Returns top_n matches sorted by fit score (lower = better).
    """
    pcb_thickness = 1.6
    min_height = component_height + pcb_thickness + margin if component_height > 0 else 0.0
    results: List[MatchResult] = []

    for enc in HAMMOND_1551:
        if min_height > 0 and enc.int_height < min_height:
            continue

        fits_n = enc.pcb_max_length >= pcb_length + margin and enc.pcb_max_width >= pcb_width + margin
        fits_r = enc.pcb_max_length >= pcb_width + margin and enc.pcb_max_width >= pcb_length + margin

        if not (fits_n or fits_r):
            continue

        orient = "normal" if fits_n else "rotated"
        unused = enc.fit_score(pcb_length, pcb_width)
        headroom = enc.int_height - (component_height + pcb_thickness) if component_height > 0 else enc.int_height

        results.append(MatchResult(enc, unused, orient, unused, headroom))

    results.sort(key=lambda r: (r.fit_score, r.enclosure.ext_height))
    return results[:top_n]


def enclosure_to_dict(enc: Enclosure1551) -> dict:
    return {
        "series": enc.series,
        "display_name": enc.display_name,
        "part_numbers": enc.part_numbers,
        "external": {"length": enc.ext_length, "width": enc.ext_width, "height": enc.ext_height},
        "internal": {"length": enc.int_length, "width": enc.int_width, "height": enc.int_height},
        "pcb_max": {"length": enc.pcb_max_length, "width": enc.pcb_max_width},
        "volume_cm3": round(enc.ext_volume_cm3, 2),
        "colors": enc.colors,
        "material": "ABS (UL94-HB)",
    }


def match_to_dict(result: MatchResult) -> dict:
    d = enclosure_to_dict(result.enclosure)
    d["fit"] = {
        "score": round(result.fit_score, 2),
        "orientation": result.orientation,
        "unused_area_mm2": round(result.unused_area_mm2, 2),
        "headroom_mm": round(result.headroom_mm, 2),
    }
    return d
