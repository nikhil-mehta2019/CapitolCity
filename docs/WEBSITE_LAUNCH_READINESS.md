# Website Launch Readiness Standard

This repository follows the shared [Website Launch Readiness Standard](https://github.com/nikhil-mehta2019/CodeAtlas/blob/feat/website-launch-standard/docs/WEBSITE_LAUNCH_READINESS_STANDARD.md) while the canonical change is under review. Before merging the standard PR, update this link to the default branch.

## Run the audit

From the repository root:

```bash
python scripts/website-audit.py
python scripts/website-audit.py --url https://YOUR-STAGING-URL --json website-audit.json
```

The script uses only Python's standard library. Static matches are marked PARTIAL, not PASS. The live crawl is read-only and limited to the same host and 30 pages by default. Analytics delivery, Search Console permissions, legal review, redirects, and actual contact-form delivery require separate verification.
