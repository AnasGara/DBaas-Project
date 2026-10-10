"""Audit the exact runtime dependency closure against OSV's public advisory database."""

import http.client
import json
import re
from pathlib import Path


def main():
    manifest = Path(__file__).resolve().parents[1] / "src" / "requirements.txt"
    packages = []
    for line in manifest.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise ValueError("Runtime dependencies must be exactly pinned")
        packages.append(match.groups())
    body = json.dumps(
        {
            "queries": [
                {"package": {"ecosystem": "PyPI", "name": name}, "version": version}
                for name, version in packages
            ]
        }
    )
    connection = http.client.HTTPSConnection("api.osv.dev", timeout=30)
    try:
        connection.request(
            "POST", "/v1/querybatch", body=body, headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Advisory service unavailable; audit did not pass")
        results = json.loads(response.read(4 * 1024 * 1024))["results"]
    finally:
        connection.close()
    if len(results) != len(packages):
        raise RuntimeError("Incomplete advisory response; audit did not pass")
    findings = []
    for (name, version), result in zip(packages, results, strict=True):
        if result.get("vulns"):
            findings.append(
                {
                    "package": name,
                    "version": version,
                    "advisories": [v["id"] for v in result["vulns"]],
                }
            )
    print(
        json.dumps(
            {"database": "OSV", "runtime_packages_checked": len(packages), "findings": findings},
            indent=2,
        )
    )
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
