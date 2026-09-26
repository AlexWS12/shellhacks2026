"""Scaffold fixture from the sponsor sample (Projects_Overlaps.xlsx).

Stub stages return these values with `fixture=True` until the real parsers,
locator, and overlap engine replace them in M1.
"""

from datetime import date

from tandem_core.models import Overlap, Project, Provenance, ReferenceResult

DESC_3 = Project(
    id="DESC_3",
    utility="DESC",
    sponsor="DESC",
    name="Jasper - Okatie 230 kV #2: Construct",
    description="",
    status=None,
    in_service=date(2025, 12, 31),
    build_start=None,
    cost_total=None,
    cost_by_year=None,
    length_mi=None,
    endpoints=(),
    center=(32.346439, -81.0785475),
    confidence="verified",
    partial_location=False,
    provenance=Provenance(
        file="Projects_Overlaps.xlsx", page=None, locator="sponsor sample DESC_3", stage="fixture"
    ),
)

GPC_2 = Project(
    id="GPC_2",
    utility="GPC",
    sponsor="SAV",
    name="SAV: MCINTOSH - PURRYSBURG 230KV REACTORS",
    description="",
    status=None,
    in_service=date(2026, 6, 1),
    build_start=None,
    cost_total=None,
    cost_by_year=None,
    length_mi=None,
    endpoints=(),
    center=(32.352116, -81.175112),
    confidence="verified",
    partial_location=False,
    provenance=Provenance(
        file="Projects_Overlaps.xlsx", page=None, locator="sponsor sample GPC_2", stage="fixture"
    ),
)

OVERLAP = Overlap(
    id="DESC_3~GPC_2",
    a="DESC_3",
    b="GPC_2",
    distance_mi=5.65,
    closest_mi=None,
    gap_days=152,
    windows_overlap=False,
    confidence="verified",
    in_reference=True,
)

REFERENCE_RESULT = ReferenceResult(
    pair=("DESC_3", "GPC_2"),
    expected_mi=5.65,
    actual_mi=5.65,
    expected_days=152,
    actual_days=152,
    passed=True,
)
