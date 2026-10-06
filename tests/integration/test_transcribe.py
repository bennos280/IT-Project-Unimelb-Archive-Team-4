"""Every committed model result under results/transcribe scores against its truth file."""
import json

from pipeline.transcribe.score import ANSWERS, TRUTH, score_page


def test_results_score():
    truth = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in TRUTH.glob("*/*.json")}
    assert truth, f"no truth files under {TRUTH}"
    for answer in ANSWERS.glob("*/*.json"):
        if answer.name in truth:
            r = score_page(truth[answer.name], json.loads(answer.read_text(encoding="utf-8")))
            assert 0 <= r["hits"] <= r["total"], answer
