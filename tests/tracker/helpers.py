import json

TEAM = "team.example.test"
AUD = "aud-tag-1"
OWNER_EMAIL = "me@example.test"
GHOST_EMAIL = "ghost@example.test"  # in access.json, but its user key has no row in the ledger


def write_config(data_dir, mode="enforce", **overrides):
    cfg = {"team_domain": TEAM, "aud": AUD, "mode": mode,
           "users": {OWNER_EMAIL: "owner", GHOST_EMAIL: "ghost"}}
    cfg.update(overrides)
    (data_dir / "access.json").write_text(json.dumps(cfg))
