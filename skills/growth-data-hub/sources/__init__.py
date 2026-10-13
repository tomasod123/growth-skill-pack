"""Source connectors for growth-data-hub.

Every module exposes the same three things:
  NAME                         short key used in config.yaml and report.json
  missing(cfg, env) -> list    env vars / config keys still missing (empty = ready to pull)
  fetch(cfg, env, start, end)  raw API responses (a dict of lists, exactly as the API returned them)
  parse(raw, cfg, start, end)  clean, flat rows the join can use

--demo feeds fixtures/<NAME>.json into parse(), so the demo and the tests exercise the same code as a real run.
"""
from . import meta, google_ads, ga4, clarity, ghl

ALL = [meta, google_ads, ga4, clarity, ghl]
