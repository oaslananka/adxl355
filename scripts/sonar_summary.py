#!/usr/bin/env python3
"""Create a bounded, security-safe GitHub summary for one SonarQube Cloud analysis."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ALLOWED_HOSTS = {"sonarcloud.io"}
MAX_PUBLIC_ISSUES = 20
METRIC_LABELS = {
    "new_reliability_rating": "New-code reliability rating",
    "new_security_rating": "New-code security rating",
    "new_maintainability_rating": "New-code maintainability rating",
    "new_duplicated_lines_density": "New-code duplicated lines",
    "new_security_hotspots_reviewed": "New security hotspots reviewed",
}
MEASURE_KEYS = (
    "bugs",
    "vulnerabilities",
    "code_smells",
    "security_hotspots",
    "security_rating",
    "reliability_rating",
    "sqale_rating",
    "coverage",
    "duplicated_lines_density",
)


def _validated_url(value: str, field: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"{field} must use an approved SonarQube Cloud host")
    return value


def parse_report_task(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Sonar report task not found: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    for required in ("ceTaskUrl", "dashboardUrl"):
        if required not in values:
            raise ValueError(f"Sonar report task is missing {required}")
        values[required] = _validated_url(values[required], required)
    return values


class SonarClient:
    def __init__(self, token: str, base_url: str = "https://sonarcloud.io") -> None:
        if not token:
            raise ValueError("SONAR_TOKEN is required")
        self.token = token
        self.base_url = _validated_url(base_url.rstrip("/"), "base URL")

    def get(
        self, endpoint_or_url: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        if endpoint_or_url.startswith("https://"):
            url = _validated_url(endpoint_or_url, "API URL")
        else:
            url = f"{self.base_url}/{endpoint_or_url.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "adxl355-sonar-summary/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"Sonar API request failed with HTTP {error.code}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError("Sonar API request failed") from error
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Sonar API returned an unexpected payload")
        return data


def wait_for_analysis(
    client: SonarClient,
    ce_task_url: str,
    *,
    attempts: int,
    interval_seconds: float,
) -> str:
    for _ in range(attempts):
        payload = client.get(ce_task_url)
        task = payload.get("task", {})
        if not isinstance(task, dict):
            raise ValueError("Sonar compute task response is invalid")
        status = str(task.get("status", ""))
        if status == "SUCCESS":
            analysis_id = str(task.get("analysisId", ""))
            if not analysis_id:
                raise ValueError("Successful Sonar task did not return an analysis id")
            return analysis_id
        if status in {"FAILED", "CANCELED"}:
            raise RuntimeError(f"Sonar compute task finished with status {status}")
        time.sleep(interval_seconds)
    raise TimeoutError("Sonar compute task did not complete within the polling budget")


def _scope_params(branch: str | None, pull_request: str | None) -> dict[str, str]:
    if pull_request:
        return {"pullRequest": pull_request}
    if branch:
        return {"branch": branch}
    return {}


def fetch_analysis_data(
    client: SonarClient,
    *,
    project_key: str,
    analysis_id: str,
    branch: str | None,
    pull_request: str | None,
) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]], int]:
    gate_payload = client.get(
        "api/qualitygates/project_status",
        {"analysisId": analysis_id},
    )
    gate = gate_payload.get("projectStatus", {})
    if not isinstance(gate, dict):
        raise ValueError("Sonar quality gate response is invalid")

    scope = _scope_params(branch, pull_request)
    measures_payload = client.get(
        "api/measures/component",
        {
            "component": project_key,
            "metricKeys": ",".join(MEASURE_KEYS),
            **scope,
        },
    )
    component = measures_payload.get("component", {})
    measures_list = component.get("measures", []) if isinstance(component, dict) else []
    measures: dict[str, str] = {}
    if isinstance(measures_list, list):
        for item in measures_list:
            if isinstance(item, dict) and item.get("metric") is not None:
                measures[str(item["metric"])] = str(item.get("value", "—"))

    issues_payload = client.get(
        "api/issues/search",
        {
            "componentKeys": project_key,
            "resolved": "false",
            "ps": "100",
            "p": "1",
            **scope,
        },
    )
    raw_issues = issues_payload.get("issues", [])
    issues = (
        [item for item in raw_issues if isinstance(item, dict)]
        if isinstance(raw_issues, list)
        else []
    )
    paging = issues_payload.get("paging", {})
    total = (
        int(paging.get("total", len(issues)))
        if isinstance(paging, dict)
        else len(issues)
    )
    return gate, measures, issues, total


def _is_security_issue(issue: dict[str, Any]) -> bool:
    if str(issue.get("type", "")).upper() in {"VULNERABILITY", "SECURITY_HOTSPOT"}:
        return True
    impacts = issue.get("impacts", [])
    if isinstance(impacts, list):
        for impact in impacts:
            if (
                isinstance(impact, dict)
                and str(impact.get("softwareQuality", "")).upper() == "SECURITY"
            ):
                return True
    return False


def _escape_markdown(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _component_path(component: object) -> str:
    value = str(component)
    if ":" in value:
        value = value.split(":", 1)[1]
    return value


def render_markdown(
    *,
    gate: dict[str, Any],
    measures: dict[str, str],
    issues: list[dict[str, Any]],
    dashboard_url: str,
    scope: str,
    total_issues: int,
) -> str:
    dashboard_url = _validated_url(dashboard_url, "dashboard URL")
    gate_status = str(gate.get("status", "UNKNOWN"))
    lines = [
        "## SonarQube Cloud analysis",
        "",
        f"- Scope: `{_escape_markdown(scope)}`",
        f"- Quality Gate: **{_escape_markdown(gate_status)}**",
        f"- Open issues: **{total_issues}**",
        f"- Dashboard: [Open detailed analysis]({dashboard_url})",
        "",
        "### Quality Gate conditions",
        "",
        "| Condition | Status | Actual | Threshold |",
        "|---|---:|---:|---:|",
    ]
    conditions = gate.get("conditions", [])
    if isinstance(conditions, list) and conditions:
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            metric = str(condition.get("metricKey", "unknown"))
            label = METRIC_LABELS.get(metric, metric)
            lines.append(
                "| "
                f"{_escape_markdown(label)} | "
                f"{_escape_markdown(condition.get('status', '—'))} | "
                f"{_escape_markdown(condition.get('actualValue', '—'))} | "
                f"{_escape_markdown(condition.get('errorThreshold', '—'))} |"
            )
    else:
        lines.append("| No conditions returned | — | — | — |")

    lines.extend(
        [
            "",
            "### Measures",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )
    for key in MEASURE_KEYS:
        if key in measures:
            lines.append(f"| `{key}` | {_escape_markdown(measures[key])} |")
    if not measures:
        lines.append("| No measures returned | — |")

    security_count = sum(1 for issue in issues if _is_security_issue(issue))
    public_issues = [issue for issue in issues if not _is_security_issue(issue)][
        :MAX_PUBLIC_ISSUES
    ]
    lines.extend(
        [
            "",
            "### Bounded issue summary",
            "",
            f"Security-related issues in the fetched page: **{security_count}**. "
            "Security issue details are intentionally omitted from public logs and summaries.",
            "",
        ]
    )
    if public_issues:
        lines.extend(["| Location | Rule | Message |", "|---|---|---|"])
        for issue in public_issues:
            path = _component_path(issue.get("component", "unknown"))
            line = issue.get("line")
            location = f"{path}:{line}" if line is not None else path
            lines.append(
                f"| `{_escape_markdown(location)}` | "
                f"`{_escape_markdown(issue.get('rule', 'unknown'))}` | "
                f"{_escape_markdown(issue.get('message', ''))} |"
            )
    else:
        lines.append(
            "No non-security issue details were returned in the bounded result page."
        )

    if total_issues > len(issues):
        lines.extend(
            [
                "",
                f"Only the first {len(issues)} of {total_issues} issues were fetched for this summary.",
            ]
        )
    return "\n".join(lines) + "\n"


def write_warning(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "## SonarQube Cloud analysis\n\n"
        f"> Summary generation warning: {_escape_markdown(message)}\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-task", type=Path, required=True)
    parser.add_argument("--project-key", required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--branch")
    scope.add_argument("--pull-request")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=60)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--soft-fail", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = parse_report_task(args.report_task)
        client = SonarClient(os.environ.get("SONAR_TOKEN", ""))
        analysis_id = wait_for_analysis(
            client,
            report["ceTaskUrl"],
            attempts=args.attempts,
            interval_seconds=args.interval_seconds,
        )
        gate, measures, issues, total = fetch_analysis_data(
            client,
            project_key=args.project_key,
            analysis_id=analysis_id,
            branch=args.branch,
            pull_request=args.pull_request,
        )
        scope = (
            f"pull request #{args.pull_request}"
            if args.pull_request
            else f"branch {args.branch}"
        )
        markdown = render_markdown(
            gate=gate,
            measures=measures,
            issues=issues,
            dashboard_url=report["dashboardUrl"],
            scope=scope,
            total_issues=total,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(
            f"Sonar summary written for {scope}: gate={gate.get('status', 'UNKNOWN')}, issues={total}"
        )
        return 0
    except Exception as error:
        if args.soft_fail:
            write_warning(args.output, str(error))
            print(
                "Sonar summary could not be generated; a bounded warning was written."
            )
            return 0
        raise


if __name__ == "__main__":
    raise SystemExit(main())
