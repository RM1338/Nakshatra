"""The generated spec must cover docs/openapi.yaml (API Contract §7), except endpoints not built yet."""
import yaml
from fastapi.testclient import TestClient

from nakshatra.api.main import create_app

# Should/Could endpoints still to build (MVP S3, S5, C1). Remove an entry when the endpoint lands.
PENDING = {("get", "/runs/{run_id}/dossier"), ("get", "/places/search")}


def test_generated_spec_covers_contract(tmp_path):
    from nakshatra.settings import Env, load_config
    from nakshatra.store.db import Store
    doc = yaml.safe_load(open("docs/openapi.yaml"))
    app = create_app(Store(tmp_path / "o.db"), load_config(), Env(_env_file=None))
    with TestClient(app) as c:
        gen = c.get("/api/v1/openapi.json").json()
    have = {(m, p.removeprefix("/api/v1")) for p, ops in gen["paths"].items() for m in ops}
    want = {(m, p) for p, ops in doc["paths"].items() for m in ops if m in ("get", "post")}
    assert want - PENDING <= have, sorted(want - PENDING - have)
    assert not (PENDING & have), "an endpoint landed: remove it from PENDING"
    for (m, p) in want - PENDING:  # documented query parameters exist in the code
        doc_q = {x["name"] for x in doc["paths"][p][m].get("parameters", []) + doc["paths"][p].get("parameters", [])
                 if isinstance(x, dict) and x.get("in") == "query"}
        gen_q = {x["name"] for x in gen["paths"]["/api/v1" + p][m].get("parameters", []) if x["in"] == "query"}
        assert doc_q <= gen_q, (m, p, doc_q - gen_q)
