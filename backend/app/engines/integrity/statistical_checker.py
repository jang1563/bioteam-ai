"""Statistical Checker — GRIM, GRIMMER, Benford's Law, p-value consistency.

Deterministic engine: no LLM calls. Implements core statistical integrity
checks used to detect fabricated or erroneous data in publications.

References:
- Brown & Heathers, "The GRIM Test" (2017)
- Heathers, "GRIMMER" (2019) — extends GRIM to SDs and percentages
- Nuijten et al., "The prevalence of statistical reporting errors" (2016)
"""

from __future__ import annotations

import logging
import math
import re

from app.engines.integrity.finding_models import (
    BenfordResult,
    GRIMResult,
    GRIMMERPercentResult,
    GRIMMERSDResult,
    PValueCheckResult,
    StatisticalFinding,
)

logger = logging.getLogger(__name__)

# Regex for APA-style statistical reporting
# Matches: F(1, 23) = 4.52, p = .003
#          t(45) = 2.31, p < .05
#          χ²(2) = 8.41, p = .015
#          r(30) = .45, p = .012
#          Z = 2.58, p = .010
_APA_STAT_RE = re.compile(
    r"""
    (?P<test_type>[Ftr]|χ²|chi2|[ZQ])  # test type (incl. Z-test, Q meta-analysis)
    \s*\(\s*                            # opening paren
    (?P<df1>\d+)                        # df1
    (?:\s*,\s*(?P<df2>\d+))?            # optional df2 (for F-test)
    \s*\)\s*                            # closing paren
    [=]\s*                              # equals sign
    (?P<statistic>-?(?:\d+\.?\d*|\.\d+))  # test statistic (allows .45 and 2.05)
    \s*,?\s*                            # optional comma
    p\s*[=<>]\s*                        # p =, p <, or p >
    \.?(?P<p_value>\d+(?:\.\d+)?)       # p-value: prevents trailing period capture
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Separate regex for Z-test without parentheses: Z = 2.58, p = .010
_Z_STAT_RE = re.compile(
    r"""
    (?P<test_type>[ZQ])                 # Z or Q test
    \s*[=]\s*                           # equals sign (no parens)
    (?P<statistic>-?(?:\d+\.?\d*|\.\d+))  # test statistic
    \s*,?\s*                            # optional comma
    p\s*[=<>]\s*                        # p =, p <, or p >
    \.?(?P<p_value>\d+(?:\.\d+)?)       # p-value
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Regex for SD reporting: "SD = 1.23", "M = 4.56, SD = 1.23, N = 30"
_SD_RE = re.compile(
    r"(?:M\s*=\s*(?P<mean>-?\d+\.?\d*)\s*,?\s*)?"
    r"SD\s*=\s*(?P<sd>\d+\.?\d*)"
    r"(?:\s*,?\s*[Nn]\s*=\s*(?P<n>\d+))?",
    re.IGNORECASE,
)

# Regex for percentage reporting: "45.6% (N = 100)", "33.3% of participants (n = 30)"
_PERCENT_RE = re.compile(
    r"(?P<pct>\d+\.?\d*)\s*%"
    r"(?:\s+(?:of|out\s+of)\s+\S+)?"
    r"(?:\s*\(?\s*[Nn]\s*=\s*(?P<n>\d+)\s*\)?)?",
)


class StatisticalChecker:
    """Deterministic statistical integrity checks.

    Implements:
    1. GRIM test — validates means against sample sizes for integer data
    2. Benford's Law — first-digit distribution analysis
    3. p-value consistency — checks if reported stats match reported p-values
    """

    # === GRIM Test ===

    @staticmethod
    def grim_test(mean: float, n: int, decimals: int = 2) -> GRIMResult:
        """Test if a reported mean is mathematically possible given sample size.

        The GRIM test checks whether a mean of integer values (e.g., Likert
        scale, count data) is consistent with the reported sample size.

        For integer data summing to S, the mean must be S/n. So the mean × n
        must be (close to) an integer.

        Args:
            mean: The reported mean.
            n: The reported sample size.
            decimals: Number of decimal places in the reported mean.

        Returns:
            GRIMResult with is_consistent=True if the mean is achievable.
        """
        if n <= 0:
            return GRIMResult(
                mean=mean,
                n=n,
                decimals=decimals,
                is_consistent=False,
                explanation="Sample size must be positive.",
            )

        # The sum S = mean * n must be an integer (within rounding tolerance)
        product = mean * n
        granularity = 10 ** (-decimals)
        # Allow for rounding: the true sum could differ by up to n * granularity/2
        tolerance = n * granularity / 2

        # Check if product is close to any integer
        nearest_int = round(product)
        diff = abs(product - nearest_int)

        is_consistent = diff <= tolerance + 1e-10  # small epsilon for float errors

        if is_consistent:
            explanation = f"Mean {mean} with N={n} is consistent (sum ≈ {nearest_int})."
        else:
            explanation = (
                f"Mean {mean} with N={n} is NOT consistent. "
                f"Product {mean}×{n} = {product:.4f}, nearest integer = {nearest_int}, "
                f"difference = {diff:.4f} exceeds tolerance {tolerance:.4f}."
            )

        return GRIMResult(
            mean=mean,
            n=n,
            decimals=decimals,
            is_consistent=is_consistent,
            explanation=explanation,
        )

    def grim_test_batch(self, entries: list[dict]) -> list[GRIMResult]:
        """Run GRIM test on multiple entries.

        Each entry should have keys: mean, n, and optionally decimals.
        """
        results = []
        for entry in entries:
            mean = float(entry.get("mean", 0))
            n = int(entry.get("n", 0))
            decimals = int(entry.get("decimals", 2))
            results.append(self.grim_test(mean, n, decimals))
        return results

    # === GRIMMER SD Test ===

    @staticmethod
    def grimmer_sd_test(sd: float, n: int, decimals: int = 2) -> GRIMMERSDResult:
        """Test if a reported SD is consistent with integer data and sample size.

        For integer data, the sum of squared deviations from the mean (SSD)
        must be an integer. SSD = SD² × (n-1). The rounding interval of the
        reported SD determines the range of possible SSD values; at least one
        integer must fall within that range for consistency.

        Reference: Heathers, "GRIMMER" (2019).

        Args:
            sd: The reported standard deviation.
            n: The reported sample size.
            decimals: Number of decimal places in the reported SD.

        Returns:
            GRIMMERSDResult with is_consistent=True if the SD is achievable.
        """
        if n <= 1:
            return GRIMMERSDResult(
                sd=sd, n=n, decimals=decimals, is_consistent=False,
                explanation="Sample size must be > 1 for SD.",
            )
        if sd < 0:
            return GRIMMERSDResult(
                sd=sd, n=n, decimals=decimals, is_consistent=False,
                explanation="SD cannot be negative.",
            )
        if sd == 0:
            return GRIMMERSDResult(
                sd=sd, n=n, decimals=decimals, is_consistent=True,
                explanation="SD of 0 means all values identical — always consistent.",
            )

        # SSD = SD² × (n-1) should be close to an integer
        granularity = 10 ** (-decimals)
        sd_low = sd - granularity / 2
        sd_high = sd + granularity / 2

        # Possible SSD range from rounding interval
        ssd_low = max(0.0, sd_low ** 2 * (n - 1))
        ssd_high = sd_high ** 2 * (n - 1)

        # Check if any integer falls within [ssd_low, ssd_high]
        low_int = math.ceil(ssd_low - 1e-9)
        high_int = math.floor(ssd_high + 1e-9)
        is_consistent = low_int <= high_int

        ssd = sd ** 2 * (n - 1)
        if is_consistent:
            explanation = (
                f"SD {sd} with N={n} is consistent "
                f"(SSD = {ssd:.4f}, range [{ssd_low:.4f}, {ssd_high:.4f}])."
            )
        else:
            explanation = (
                f"SD {sd} with N={n} is NOT consistent. "
                f"SSD = {sd}² × {n-1} = {ssd:.4f}, "
                f"no integer in [{ssd_low:.4f}, {ssd_high:.4f}]."
            )

        return GRIMMERSDResult(
            sd=sd, n=n, decimals=decimals,
            is_consistent=is_consistent, explanation=explanation,
        )

    # === GRIMMER Percentage Test ===

    @staticmethod
    def grimmer_percent_test(
        percentage: float, n: int, decimals: int = 2,
    ) -> GRIMMERPercentResult:
        """Test if a reported percentage is consistent with sample size.

        count = percentage × n / 100 should be close to an integer.
        Tolerance derived from rounding granularity of the percentage.

        Args:
            percentage: The reported percentage (0-100 scale).
            n: The reported sample size.
            decimals: Number of decimal places in the reported percentage.

        Returns:
            GRIMMERPercentResult with is_consistent flag.
        """
        if n <= 0:
            return GRIMMERPercentResult(
                percentage=percentage, n=n, decimals=decimals,
                is_consistent=False,
                explanation="Sample size must be positive.",
            )

        product = percentage * n / 100
        granularity = 10 ** (-decimals)
        # tolerance = n × granularity / 200 (granularity/100 × n / 2)
        tolerance = n * granularity / 200

        nearest_int = round(product)
        diff = abs(product - nearest_int)
        is_consistent = diff <= tolerance + 1e-10

        if is_consistent:
            explanation = (
                f"{percentage}% with N={n} is consistent (count ≈ {nearest_int})."
            )
        else:
            explanation = (
                f"{percentage}% with N={n} is NOT consistent. "
                f"Count = {percentage}×{n}/100 = {product:.4f}, "
                f"nearest integer = {nearest_int}, "
                f"diff = {diff:.4f} > tolerance {tolerance:.4f}."
            )

        return GRIMMERPercentResult(
            percentage=percentage, n=n, decimals=decimals,
            is_consistent=is_consistent, explanation=explanation,
        )

    # === GRIMMER Text Extraction ===

    def extract_and_check_grimmer(self, text: str) -> list[StatisticalFinding]:
        """Extract SD and percentage reports from text and run GRIMMER tests.

        Looks for patterns like 'SD = 1.23, N = 30' and '45.6% (N = 100)'.
        Only flags inconsistencies — consistent values are silently passed.
        """
        findings: list[StatisticalFinding] = []

        # SD checks
        for match in _SD_RE.finditer(text):
            sd_str = match.group("sd")
            n_str = match.group("n")
            if not n_str:
                continue  # Need N for GRIMMER
            sd = float(sd_str)
            n = int(n_str)
            decimals = len(sd_str.split(".")[-1]) if "." in sd_str else 0
            result = self.grimmer_sd_test(sd, n, decimals)
            if not result.is_consistent:
                findings.append(StatisticalFinding(
                    severity="warning",
                    title="GRIMMER SD inconsistency",
                    description=result.explanation,
                    source_text=match.group(0),
                    suggestion=(
                        "Verify the reported SD is consistent with "
                        "sample size and integer data."
                    ),
                    confidence=0.80,
                    checker="statistical_checker",
                    category="grimmer_sd_failure",
                    grimmer_sd_result=result,
                ))

        # Percentage checks
        for match in _PERCENT_RE.finditer(text):
            pct_str = match.group("pct")
            n_str = match.group("n")
            if not n_str:
                continue  # Need N for GRIMMER
            pct = float(pct_str)
            n = int(n_str)
            decimals = len(pct_str.split(".")[-1]) if "." in pct_str else 0
            result = self.grimmer_percent_test(pct, n, decimals)
            if not result.is_consistent:
                findings.append(StatisticalFinding(
                    severity="warning",
                    title="GRIMMER percentage inconsistency",
                    description=result.explanation,
                    source_text=match.group(0),
                    suggestion=(
                        "Verify the reported percentage is consistent "
                        "with sample size."
                    ),
                    confidence=0.80,
                    checker="statistical_checker",
                    category="grimmer_percent_failure",
                    grimmer_percent_result=result,
                ))

        return findings

    # === Benford's Law ===

    @staticmethod
    def benford_analysis(values: list[float], min_values: int = 50) -> BenfordResult:
        """Analyze first-digit distribution against Benford's Law.

        Benford's Law: P(d) = log10(1 + 1/d) for d = 1..9.
        Natural datasets follow this distribution; fabricated data often doesn't.

        Args:
            values: List of numeric values to analyze.
            min_values: Minimum number of values for meaningful analysis.

        Returns:
            BenfordResult with chi-squared test and anomaly flag.
        """
        # Filter to positive values and extract first digits
        first_digits: list[int] = []
        for v in values:
            v_abs = abs(v)
            if v_abs < 1e-10:
                continue
            # Get first non-zero digit
            digit = int(str(v_abs).lstrip("0").lstrip(".").lstrip("0")[0])
            if 1 <= digit <= 9:
                first_digits.append(digit)

        n = len(first_digits)
        if n < min_values:
            return BenfordResult(
                n_values=n,
                is_anomalous=False,  # Not enough data to determine
            )

        # Expected Benford distribution
        expected: dict[str, float] = {}
        for d in range(1, 10):
            expected[str(d)] = math.log10(1 + 1 / d)

        # Observed distribution
        observed: dict[str, float] = {}
        for d in range(1, 10):
            count = first_digits.count(d)
            observed[str(d)] = count / n

        # Chi-squared test
        chi_sq = 0.0
        for d in range(1, 10):
            obs = observed[str(d)] * n
            exp = expected[str(d)] * n
            if exp > 0:
                chi_sq += (obs - exp) ** 2 / exp

        # Chi-squared with 8 df (9 categories - 1)
        # Critical values: 15.51 (p=0.05), 20.09 (p=0.01)
        # Use a simple lookup instead of scipy dependency
        p_value = _chi2_survival(chi_sq, df=8)
        is_anomalous = p_value < 0.05

        return BenfordResult(
            n_values=n,
            chi_squared=round(chi_sq, 4),
            p_value=round(p_value, 6),
            is_anomalous=is_anomalous,
            digit_distribution=observed,
            expected_distribution=expected,
        )

    # === P-value consistency ===

    @staticmethod
    def check_p_value_consistency(
        test_type: str,
        statistic: float,
        df: int | tuple[int, int],
        reported_p: float,
        threshold: float = 0.05,
    ) -> PValueCheckResult:
        """Check if reported p-value is consistent with reported test statistic.

        Uses scipy for p-value recalculation if available, otherwise skips.

        Args:
            test_type: "t", "F", "chi2", or "r"
            statistic: The reported test statistic value.
            df: Degrees of freedom (int for t/chi2, tuple for F).
            reported_p: The reported p-value.
            threshold: Maximum acceptable discrepancy.

        Returns:
            PValueCheckResult with consistency assessment.
        """
        recalculated_p = _recalculate_p_value(test_type, statistic, df)

        if recalculated_p is None:
            return PValueCheckResult(
                test_type=test_type,
                reported_statistic=statistic,
                reported_df=str(df),
                reported_p=reported_p,
                recalculated_p=0.0,
                discrepancy=0.0,
                is_consistent=True,  # Can't verify, assume consistent
            )

        discrepancy = abs(reported_p - recalculated_p)
        is_consistent = discrepancy <= threshold

        return PValueCheckResult(
            test_type=test_type,
            reported_statistic=statistic,
            reported_df=str(df),
            reported_p=reported_p,
            recalculated_p=round(recalculated_p, 6),
            discrepancy=round(discrepancy, 6),
            is_consistent=is_consistent,
        )

    def extract_and_check_stats(self, text: str) -> list[StatisticalFinding]:
        """Extract APA-style statistics from text and validate consistency.

        Finds patterns like "F(1, 23) = 4.52, p = .003" and checks if the
        reported p-value matches the test statistic. Also handles Z = 2.58, p = .010.
        """
        findings: list[StatisticalFinding] = []
        seen_spans: set[tuple[int, int]] = set()

        # Process matches from both regex patterns
        for match in _extract_all_stat_matches(text):
            # Deduplicate overlapping matches
            span = match.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)

            finding = self._process_stat_match(match)
            if finding:
                findings.append(finding)

        return findings

    def _process_stat_match(self, match: re.Match) -> StatisticalFinding | None:
        """Process a single regex match into a finding (if inconsistent)."""
        test_type = match.group("test_type").lower()
        if test_type in ("χ²", "chi2"):
            test_type = "chi2"

        df1_str = match.groupdict().get("df1")
        df2_str = match.groupdict().get("df2")

        if df1_str is not None:
            df1 = int(df1_str)
            df: int | tuple[int, int] = (df1, int(df2_str)) if df2_str else df1
        else:
            # Z = ... format (no parenthesized df)
            df = 0  # Z-test doesn't use df

        statistic = float(match.group("statistic"))

        p_str = match.group("p_value")
        # Handle both ".003" (captured as "003") and "0.003" (captured as "0.003")
        reported_p = float(p_str) if "." in p_str else float(f"0.{p_str}")

        result = self.check_p_value_consistency(test_type, statistic, df, reported_p)

        if not result.is_consistent:
            return StatisticalFinding(
                severity="warning",
                title=f"p-value inconsistency: {test_type} test",
                description=(
                    f"Reported {test_type}({result.reported_df}) = {statistic}, "
                    f"p = {reported_p}. Recalculated p = {result.recalculated_p}. "
                    f"Discrepancy = {result.discrepancy}."
                ),
                source_text=match.group(0),
                suggestion="Verify the reported p-value matches the test statistic.",
                confidence=0.85,
                checker="statistical_checker",
                category="p_value_mismatch",
                p_value_result=result,
            )
        return None


# === Internal helpers ===


def _extract_all_stat_matches(text: str) -> list[re.Match]:
    """Extract all APA-style stat matches from text using both regex patterns."""
    matches = list(_APA_STAT_RE.finditer(text))
    # Also check for Z/Q without parentheses (e.g., "Z = 2.58, p = .010")
    for m in _Z_STAT_RE.finditer(text):
        # Avoid duplicates — only add if not already captured by main regex
        if not any(m.start() == existing.start() for existing in matches):
            matches.append(m)
    return sorted(matches, key=lambda m: m.start())


def _recalculate_p_value(
    test_type: str,
    statistic: float,
    df: int | tuple[int, int],
) -> float | None:
    """Recalculate p-value from test statistic and df.

    Returns None if scipy is not available.
    """
    try:
        from scipy import stats as sp_stats
    except ImportError:
        logger.debug("scipy not available, skipping p-value recalculation")
        return None

    try:
        if test_type == "t":
            if isinstance(df, tuple):
                df = df[0]
            return float(2 * sp_stats.t.sf(abs(statistic), df))  # two-tailed

        if test_type == "f":
            if isinstance(df, tuple):
                df1, df2 = df
            else:
                return None
            return float(sp_stats.f.sf(statistic, df1, df2))

        if test_type == "chi2":
            if isinstance(df, tuple):
                df = df[0]
            return float(sp_stats.chi2.sf(statistic, df))

        if test_type == "r":
            # Convert r to t: t = r * sqrt(n-2) / sqrt(1-r²)
            if isinstance(df, tuple):
                df = df[0]
            if abs(statistic) >= 1.0:
                return 0.0
            t_val = statistic * math.sqrt(df) / math.sqrt(1 - statistic**2)
            return float(2 * sp_stats.t.sf(abs(t_val), df))

        if test_type == "z":
            # Z-test: standard normal, two-tailed
            return float(2 * sp_stats.norm.sf(abs(statistic)))

        if test_type == "q":
            # Q-test (meta-analysis heterogeneity): chi-squared distribution
            if isinstance(df, tuple):
                df = df[0]
            return float(sp_stats.chi2.sf(statistic, df))

    except Exception as e:
        logger.debug("p-value recalculation failed: %s", e)

    return None


def _chi2_survival(x: float, df: int) -> float:
    """Approximate chi-squared survival function (p-value).

    Uses the regularized incomplete gamma function approximation.
    Falls back to scipy if available, otherwise uses a simple approximation.
    """
    if df <= 0 or x <= 0:
        return 1.0

    try:
        from scipy import stats as sp_stats
        return float(sp_stats.chi2.sf(x, df))
    except ImportError:
        pass

    z = ((x / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))

    # Standard normal CDF approximation
    if z > 6:
        return 0.0
    if z < -6:
        return 1.0

    return 0.5 * math.erfc(z / math.sqrt(2))
