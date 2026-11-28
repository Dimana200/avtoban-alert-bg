#!/usr/bin/env python3
"""Delete driver reports whose time is over (field `exp`) from Firestore.

Expired reports are never read again (every query asks for exp > now), but they stay in the
database forever and take space. This removes them, only them, in small portions.

Safety:
- By default it only COUNTS (dry run). It deletes only when DELETE=true.
- Only collection `reports`, only documents with exp older than now minus GRACE_HOURS (24 h).
  Each document is checked again before it is deleted.
- At most MAX_DELETES (5000) per run, so a day stays far inside the free quota
  (20 000 deletes and 50 000 reads a day; each deleted report costs 1 read + 1 delete).
- The service account key comes from the environment (GitHub secret FIRESTORE_SA_KEY).
  It is never printed or written to disk.
"""
import json, os, sys, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
import common  # noqa: F401 - IPv4-only patch

PROJECT = "avtoban-alert-bg"
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
PAGE = 500  # Firestore allows up to 500 writes in one batchWrite


def env_int(name, default):
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


def token():
    raw = os.environ.get("FIRESTORE_SA_KEY", "").strip()
    if not raw:
        return None
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    info = json.loads(raw)
    if info.get("project_id") != PROJECT:
        raise SystemExit(f"the key is for project {info.get('project_id')!r}, not {PROJECT!r}: nothing done")
    cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/datastore"])
    cred.refresh(Request())
    return cred.token


def post(url, body, tok):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}", "User-Agent": common.UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # the body is Firestore's error text (no key in it)
        raise SystemExit(f"Firestore {e.code}: {e.read().decode(errors='replace')[:500]}")


def expired_query(cutoff, limit=None):
    q = {"from": [{"collectionId": "reports"}],
         "where": {"fieldFilter": {"field": {"fieldPath": "exp"}, "op": "LESS_THAN", "value": {"timestampValue": cutoff}}},
         "orderBy": [{"field": {"fieldPath": "exp"}, "direction": "ASCENDING"}]}
    if limit:
        q["select"] = {"fields": [{"fieldPath": "exp"}]}
        q["limit"] = limit
    return q


def count(cutoff, tok):
    # one aggregation costs 1 read per up to 1000 matching documents, much cheaper than reading them
    q = expired_query(cutoff)
    del q["orderBy"]
    res = post(f"{BASE}:runAggregationQuery",
               {"structuredAggregationQuery": {"structuredQuery": q, "aggregations": [{"alias": "n", "count": {}}]}}, tok)
    return int(res[0]["result"]["aggregateFields"]["n"]["integerValue"])


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    delete = os.environ.get("DELETE", "").lower() == "true"
    grace = env_int("GRACE_HOURS", 24)
    cap = env_int("MAX_DELETES", 5000)
    tok = token()
    if not tok:
        print("::warning::secret FIRESTORE_SA_KEY is not set: nothing done")
        return
    now = datetime.now(timezone.utc)
    cutoff_dt = now - timedelta(hours=grace)
    cutoff = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    total = count(cutoff, tok)
    print(f"reports expired before {cutoff} ({grace} h ago): {total}")
    if not delete:
        print(f"DRY RUN: nothing deleted. A real run would delete {min(total, cap)} now (at most {cap} per run).")
        return

    deleted = 0
    while deleted < cap:
        rows = post(f"{BASE}:runQuery", {"structuredQuery": expired_query(cutoff, min(PAGE, cap - deleted))}, tok)
        names = []
        for row in rows:
            d = row.get("document")
            if not d:
                continue
            exp = d.get("fields", {}).get("exp", {}).get("timestampValue")
            # check again: delete only a report whose exp is really older than the cutoff
            if exp and ts(exp) < cutoff_dt and "/documents/reports/" in d["name"]:
                names.append(d["name"])
        if not names:
            break
        res = post(f"{BASE}:batchWrite", {"writes": [{"delete": n} for n in names]}, tok)
        bad = [s for s in res.get("status", []) if s.get("code", 0) != 0]
        deleted += len(names) - len(bad)
        print(f"   deleted {len(names) - len(bad)} of {len(names)}" + (f", errors: {bad[:3]}" if bad else ""), flush=True)
        if bad:
            raise SystemExit("some deletes failed: stopped")
    print(f"deleted this run: {deleted}; still expired: {max(total - deleted, 0)}")


if __name__ == "__main__":
    sys.exit(main())
