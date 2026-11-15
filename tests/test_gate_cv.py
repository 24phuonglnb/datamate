"""eval/gate_cv.py: shop-wise cross-validation of the LLM gate (synthetic rows, no data, no model)."""
from eval.gate_cv import cross_validate, measure, to_markdown


def _rows():
    rows = []
    for shop in ("s1", "s2", "s3", "s4"):
        # router answers: 10 correct per shop
        rows += [{"business_id": shop, "route": "template", "score": 1, "status": "correct", "gate_key": "r"} for _ in range(10)]
        # kind "good": LLM right 8/10; kind "bad": LLM right 2/10 (wrong 8)
        rows += [{"business_id": shop, "route": "llm", "gate_key": "good", "score": 1 if i < 8 else -1,
                  "status": "correct" if i < 8 else "wrong"} for i in range(10)]
        rows += [{"business_id": shop, "route": "llm", "gate_key": "bad", "score": 1 if i < 2 else -1,
                  "status": "correct" if i < 2 else "wrong"} for i in range(10)]
    return rows


def test_measure_reference_points():
    rows = _rows()
    allp = measure(rows, None)
    assert allp["n"] == 120 and allp["n_llm"] == 80
    assert allp["pa_total"] == (40 + 4 * (6 + (-6))) / 120                       # good: +6 net, bad: -6 net per shop
    only = measure(rows, set())
    assert only["pa_total"] == 40 / 120 and only["pa_llm_branch"] == 0.0 and only["llm_answered"] == 0
    gated = measure(rows, {"good"})
    assert gated["pa_llm_branch"] == 24 / 80 and gated["pa_total"] == (40 + 24) / 120


def test_cross_validation_fits_on_other_shops_only():
    res = cross_validate(_rows(), [0.6], [5])
    c = res["configs"]["min_acc=0.6,min_n=5"]
    for fold in c["split"]["folds"] + c["loo"]["folds"]:
        assert fold["enabled"] == ["good"]                                       # accuracy 0.8 passes, 0.2 does not
    assert c["split"]["pooled"]["pa_total"] == c["loo"]["pooled"]["pa_total"] == (40 + 24) / 120
    assert len(c["loo"]["folds"]) == 4 and len(c["split"]["folds"]) == 2


def test_gate_is_not_fitted_on_the_measured_shop():
    rows = _rows()
    for r in rows:                                                                # s4 is the only shop where "bad" is good
        if r["business_id"] == "s4" and r["gate_key"] == "bad":
            r["score"], r["status"] = 1, "correct"
    res = cross_validate(rows, [0.6], [5])
    s4 = [f for f in res["configs"]["min_acc=0.6,min_n=5"]["loo"]["folds"] if f["n"] == 30][-1]
    assert s4["enabled"] == ["good"]                                              # fitted on s1-s3 where "bad" fails


def test_markdown_has_reference_and_every_configuration():
    md = to_markdown(cross_validate(_rows(), [0.5, 0.7], [5]))
    assert "router-only" in md and "all (no gate" in md and md.count("loo") == 2 and md.count(" split ") == 2
