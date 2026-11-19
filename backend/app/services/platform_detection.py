from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformDetection:
    code: str
    confidence: float
    reasons: tuple[str, ...]


def detect_platform(url: str, title: str, text: str) -> PlatformDetection:
    target = url.lower()
    page = f"{title} {text[:5000]}".lower()
    rules = (
        ("EDITORIAL_MANAGER", ("editorialmanager.com",), "Editorial Manager URL", 0.99),
        ("SCHOLARONE", ("manuscriptcentral.com",), "ScholarOne URL", 0.99),
        ("WILEY_RESEARCH_EXCHANGE", ("wiley.atyponrex.com",), "Wiley Research Exchange URL", 0.98),
        ("SNAPP", ("submission.nature.com",), "SNAPP URL", 0.97),
        ("MDPI_SYSTEM", ("mdpi.com",), "MDPI domain", 0.9),
        ("FRONTIERS_SYSTEM", ("frontiersin.org",), "Frontiers domain", 0.85),
        ("IEEE_AUTHOR_PORTAL", ("ieee.org",), "IEEE domain", 0.85),
        ("ACS_PARAGON_PLUS", ("acs.org",), "ACS domain", 0.85),
    )
    for code, domains, reason, confidence in rules:
        if any(domain in target for domain in domains):
            return PlatformDetection(code=code, confidence=confidence, reasons=(reason,))
    if "open journal systems" in page or (
        "index.php" in target and "/about/submissions" in target
    ):
        return PlatformDetection(
            code="OJS",
            confidence=0.95,
            reasons=("Open Journal Systems 页面或路径特征",),
        )
    return PlatformDetection(code="UNKNOWN", confidence=0, reasons=())
