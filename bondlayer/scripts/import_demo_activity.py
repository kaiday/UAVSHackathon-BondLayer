"""Import remote benchmark outcomes as clearly identified local demo activity."""
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone

import httpx


def main():
    now = datetime.now(timezone.utc)
    targets = {"citycircuit", "northgear"}
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        for index in range(30):
            scenario = f"R{index + 1:02d}"
            raw = subprocess.check_output([
                "git", "show", f"origin/main:bondlayer/data/eval/reports/{scenario}.json"
            ])
            original = json.loads(raw)
            for enabled, group in ((True, "merchants"), (False, "control")):
                rows = original.get(group, [])
                selected = [row for row in rows if row["merchant"] in targets]
                if not selected:
                    continue
                report = {
                    "request_id": "live-" + hashlib.md5(f"imported-demo-{scenario}-{group}".encode()).hexdigest(),
                    "source": "demo", "scenario_id": scenario,
                    "created_at": (now - timedelta(days=(index * 7) % 14, hours=index % 5 + 1)).isoformat(),
                    "utterance": original["utterance"], "constraints": original["constraints"],
                    "extension_enabled": enabled, "merchants": selected,
                    "comparison_winner_known": any(row.get("won") is True for row in rows),
                    "demo_note": "Remote benchmark outcomes; dates simulated over 14 days; no checkout data.",
                }
                # Re-running preserves the original import instead of conflicting with its date.
                existing = client.get(f"/onboard/requests/{report['request_id']}")
                if existing.status_code == 200:
                    continue
                response = client.post("/internal/requests", json=report)
                response.raise_for_status()
        for merchant in sorted(targets):
            response = client.get(f"/onboard/insights/{merchant}")
            response.raise_for_status()
            print(json.dumps({"merchant": merchant, "metrics": response.json()["metrics"]}))


if __name__ == "__main__":
    main()
