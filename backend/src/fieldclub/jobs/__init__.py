"""Scheduled work, run by `fieldclub-jobs` (see `fieldclub.jobs.cli`).

- `channels`: read each watched channel's public feed and add a mention
  for every link back to a finding.
- `sources`: run each bulk source's connector when its data is older than
  the connector says it should be.
"""
