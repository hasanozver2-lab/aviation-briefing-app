"""Read-only source diagnostics; candidates and policy exclusions are not fetch errors."""

from collections import Counter

try:
    from . import source_catalog
except ImportError:
    import source_catalog

EXPECTED_REGIONS = ("Europe", "North America", "Latin America", "Middle East", "Asia-Pacific", "Turkey", "Africa")
STATUS_ACTIONS = {
    "error": ("Kaynak erişimi kontrol edilmeli; erişim engelleri aşılmaz.", "Check publisher access; access restrictions are respected."),
    "not_configured": ("Gerekli besleme veya ortam değişkeni yapılandırılmalı.", "Configure the required feed or environment variable."),
    "no_extractable_feed": ("Onaylı kaynak için geçerli bir besleme gerekiyor.", "A valid feed is required for this approved source."),
}


def present_source_health(pipeline_status, rows=None):
    catalog = source_catalog.read_rows() if rows is None else rows
    approved = [row for row in catalog if str(row.get("active")) == "1"]
    observed = (pipeline_status or {}).get("sources") or {}
    coverage = Counter(row.get("region", "Unknown") for row in approved)
    issues = []
    reading_ok = 0
    reading_coverage = Counter()
    for row in approved:
        entry = observed.get(row["name"], {})
        status = entry.get("status", "not_reported")
        if status == "active" and not entry.get("error"):
            reading_ok += 1
            reading_coverage[row.get("region", "Unknown")] += 1
            continue
        if not observed:
            continue
        status = "error" if status == "active" else status
        action_tr, action_en = STATUS_ACTIONS.get(status, ("Son toplama durumu kontrol edilmeli.", "Check the latest collection status."))
        issues.append({"name": row["name"], "status": status, "action_tr": action_tr, "action_en": action_en})
    return {
        "status": "reported" if observed else "unavailable",
        "checked_at": (pipeline_status or {}).get("last_attempt_at"),
        "configured_active": len(approved),
        "reading_ok": reading_ok,
        "issues": issues,
        "status_counts": dict(Counter(entry.get("status", "unknown") for entry in observed.values())),
        "coverage": dict(coverage),
        "reading_coverage": dict(reading_coverage),
        "coverage_gaps": [region for region in EXPECTED_REGIONS if not coverage[region]],
        "reading_coverage_gaps": [region for region in EXPECTED_REGIONS if not reading_coverage[region]] if observed else [],
    }
