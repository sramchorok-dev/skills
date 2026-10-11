import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import copy_policy  # noqa: E402
import pkg_matrix  # noqa: E402
from pkg_matrix import Response  # noqa: E402

BASE = "https://api-dev.example.test"
HEADER = ",".join(pkg_matrix.COMBO_HEADER)


def artifact(status="READY", trees=None, clusters=None, plants=None, shortage=False, reason=None,
             diagnostics=None, width=6.0, depth=2.0):
    return {
        "status": status, "reason": reason, "configVersion": "cfg-1",
        "selection": {"seed": 20260825, "catalogVersion": "cat-1", "enabledFlowerChips": ["빨강"],
                      "shortageRepeat": shortage, "warnings": [],
                      "selectedPlants": plants or [{"productCode": "A1", "itemId": "a", "representativeRank": 1,
                                                    "stage": "MAIN"}]},
        "snapshot": {"widthM": width, "depthM": depth,
                     "clusters": clusters or [{"productCode": "A1", "label": "가", "heightCm": 40, "quantity": 9}],
                     "trees": trees or [],
                     "bom": [{"productCode": "A1", "name": "가", "quantity": 9}],
                     "diagnostics": diagnostics or []},
    }


QUOTE_OK = {"items": [{"type": "SET_PLAN", "ref": "C1", "amount": 642160},
                      {"type": "SERVICE", "ref": "GARDEN_GUIDE_V1", "amount": 100000}],
            "subtotal": 742160, "totalAmount": 742160, "shippingAmount": 0, "packageAmount": 742160,
            "guideAmount": 100000, "optionAmount": 0,
            "packageDelivery": {"separatePayment": True, "label": "용달 기준 50,000원~ · 상담 후 별도 결제"}}


class FakeHttp:
    """Scripted responses per (method, path prefix); records every call."""

    def __init__(self, script):
        self.script = {key: list(value) for key, value in script.items()}
        self.calls = []

    def __call__(self, method, url, payload):
        path = url[len(BASE):]
        self.calls.append((method, path, payload))
        for (want_method, prefix), queue in self.script.items():
            if want_method == method and path.startswith(prefix) and queue:
                return queue.pop(0)
        raise AssertionError(f"unexpected call {method} {path}")


def run_matrix(rows, script, extra=None, files=None):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    combos = root / "combos.csv"
    combos.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    for name, text in (files or {}).items():
        (root / name).write_text(text, encoding="utf-8")
    out = root / "out.tsv"
    http, sleeps = FakeHttp(script), []
    argv = ["--base-url", BASE, "--combos", str(combos), "--out", str(out), "--sleep", "0"]
    argv += [part.replace("{root}", str(root)) for part in (extra or [])]
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = pkg_matrix.main(argv, http=http, sleep=sleeps.append, clock=lambda: 0.0)
    result = list(csv.DictReader(out.open(encoding="utf-8"), delimiter="\t")) if out.exists() else []
    tmp.cleanup()
    return code, result, http, sleeps, stdout.getvalue(), stderr.getvalue()


def job(art):
    return Response(200, {"jobId": "j1", "status": "SUCCEEDED", "retryAfterMs": 0, "artifact": art, "error": None},
                    {})


class PkgMatrixTests(unittest.TestCase):
    def test_ready_layout_and_quote_with_guide_line(self):
        code, rows, http, _, out, _ = run_matrix(
            ["G1,C1,6,2,BACK,,,,,,,READY,예시"],
            {("POST", "/tier2/layout/preview-jobs"): [job(artifact())],
             ("POST", "/tier2/pricing/quote"): [Response(200, QUOTE_OK, {})]})
        self.assertEqual(code, 0)
        row = rows[0]
        self.assertEqual((row["layout_status"], row["quote"]), ("READY", "OK"))
        self.assertEqual((row["set_plan_amount"], row["guide_amount"], row["package_amount"], row["shipping_amount"]),
                         ("642160", "100000", "742160", "0"))
        self.assertEqual(row["delivery_label"], "용달 기준 50,000원~ · 상담 후 별도 결제")
        layout_body = http.calls[0][2]
        self.assertEqual((layout_body["light"], layout_body["floorType"], layout_body["seed"]), ("SUN", "SOIL", 20260825))
        quote_body = http.calls[1][2]
        self.assertEqual((quote_body["layoutConfigVersion"], quote_body["layoutCatalogVersion"], quote_body["lengthM"],
                          quote_body["optionCodes"], quote_body["zipcode"]), ("cfg-1", "cat-1", None, [], None))
        self.assertIn("견적 OK 1", out)
        self.assertFalse(any(path.startswith("/tier2/orders") or "cart" in path for _, path, _ in http.calls))

    def test_review_required_records_409_and_internal_text(self):
        art = artifact(status="REVIEW_REQUIRED", reason="같은 품종 군락의 시드 간격을 확인해주세요",
                       diagnostics=[{"code": "SEED_GAP", "message": "배치 검토 항목 2건", "clusterId": None}])
        _, rows, _, _, _, _ = run_matrix(
            ["B1,C1,1.5,1,BACK,,,,,,,상담,예시"],
            {("POST", "/tier2/layout/preview-jobs"): [job(art)],
             ("POST", "/tier2/pricing/quote"): [Response(409, {"code": "TIER2-409-11",
                                                               "message": "구성과 가격 확인 중"}, {})]})
        row = rows[0]
        self.assertEqual(row["layout_status"], "REVIEW_REQUIRED")
        self.assertEqual(row["quote"], "HTTP_409:TIER2-409-11")
        self.assertEqual(row["internal_text"], "시드 간격; 배치 검토 항목; 구성과 가격 확인 중")

    def test_running_job_is_polled_with_clamped_wait(self):
        running = Response(202, {"jobId": "j9", "status": "RUNNING", "retryAfterMs": 50, "artifact": None,
                                 "error": None}, {})
        _, rows, http, sleeps, _, _ = run_matrix(
            ["P1,C3,3,2,BACK,,,,,,,,"],
            {("POST", "/tier2/layout/preview-jobs"): [running],
             ("GET", "/tier2/layout/preview-jobs/j9"): [job(artifact())],
             ("POST", "/tier2/pricing/quote"): [Response(200, QUOTE_OK, {})]})
        self.assertEqual(rows[0]["layout_job"], "SUCCEEDED")
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(http.calls[0][2]["light"], "PARTIAL_SHADE")

    def test_429_waits_retry_after_then_succeeds(self):
        _, rows, http, sleeps, out, _ = run_matrix(
            ["R1,C1,6,2,BACK,,,,,,,,"],
            {("POST", "/tier2/layout/preview-jobs"): [Response(429, None, {"Retry-After": "7"}), job(artifact())],
             ("POST", "/tier2/pricing/quote"): [Response(429, None, {}), Response(200, QUOTE_OK, {})]})
        self.assertEqual((rows[0]["layout_job"], rows[0]["quote"]), ("SUCCEEDED", "OK"))
        self.assertEqual(sleeps, [7.0, 2.0])
        self.assertIn("429 재시도 2회", out)

    def test_429_exhausted_is_recorded(self):
        _, rows, _, sleeps, _, _ = run_matrix(
            ["R2,C1,6,2,BACK,,,,,,,,"],
            {("POST", "/tier2/layout/preview-jobs"): [Response(429, None, {})] * 3,
             ("POST", "/tier2/pricing/quote"): [Response(200, QUOTE_OK, {})]},
            extra=["--max-retries", "2"])
        self.assertEqual(rows[0]["layout_job"], "HTTP_429")
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_height_band_violation_needs_catalog(self):
        plants = [{"productCode": "REP", "itemId": "r", "representativeRank": 1, "stage": "MAIN"},
                  {"productCode": "TALL", "itemId": "t", "representativeRank": 2, "stage": "P"},
                  {"productCode": "NEAR", "itemId": "n", "representativeRank": 3, "stage": "T1"}]
        files = {"bands.csv": "productCode,band,heightCm\nREP,중하,45\nTALL,뒤,105\nREP2,중하,45\nNEAR,중상,55\nREP3,중하,45\n",
                 "reps.csv": "package,rank,productCode\nC2,1,REP\nC2,2,REP2\nC2,3,REP3\n"}
        script = lambda: {("POST", "/tier2/layout/preview-jobs"): [job(artifact(plants=plants))],
                          ("POST", "/tier2/pricing/quote"): [Response(200, QUOTE_OK, {})]}
        _, rows, _, _, _, _ = run_matrix(["H1,C2,6,2,BACK,,,,,,,,"], script(), files=files,
                                         extra=["--catalog", "{root}/bands.csv", "--reps", "{root}/reps.csv"])
        self.assertEqual(rows[0]["height_band_violations"], "TALL(뒤 105)P→REP2(중하 45)")
        _, rows, _, _, _, _ = run_matrix(["H2,C2,6,2,BACK,,,,,,,,"], script())
        self.assertEqual(rows[0]["height_band_violations"], "unchecked")

    def test_wide_notice_rule_and_tree_overlap(self):
        clusters = [{"productCode": "A1", "label": "가", "heightCm": 40, "quantity": 5}] * 2
        trees = [{"productCode": "T1", "label": "나무수국", "xM": 1.0, "yM": 1.0, "crownRadiusM": 0.6},
                 {"productCode": "T1", "label": "나무수국", "xM": 1.5, "yM": 1.0, "crownRadiusM": 0.6}]
        _, rows, _, _, out, _ = run_matrix(
            ["W1,C3,3,2,BACK,,,,,,,,"],
            {("POST", "/tier2/layout/preview-jobs"): [job(artifact(shortage=True, clusters=clusters, trees=trees,
                                                                   width=3.0, depth=2.0))],
             ("POST", "/tier2/pricing/quote"): [Response(200, QUOTE_OK, {})]})
        row = rows[0]
        self.assertEqual((row["wide_notice"], row["max_same_species_clusters"], row["wide_rule_ok"]), ("yes", "2", "no"))
        self.assertEqual(row["tree_issue"], "overlap:T1/T1")
        self.assertTrue(row["trees"].startswith("2 (나무수국)"))
        self.assertIn("넓은 공간 안내 기준 불일치 1", out)

    def test_c6_sends_screening_length_on_wall_axis(self):
        script = {("POST", "/tier2/layout/preview-jobs"): [job(artifact())] * 3,
                  ("POST", "/tier2/pricing/quote"): [Response(200, QUOTE_OK, {})] * 3}
        _, _, http, _, _, _ = run_matrix(["S1,C6,6,1,BACK,,,,,,,,", "S2,C6,1.5,6,LEFT,,,,,,,,",
                                          "S3,C6,4,5,CORNER,,,,,,,,"], script)
        lengths = [payload["lengthM"] for method, path, payload in http.calls if path == "/tier2/pricing/quote"]
        self.assertEqual(lengths, [6.0, 6.0, 5.0])

    def test_production_host_is_refused(self):
        tmp = tempfile.TemporaryDirectory()
        combos = Path(tmp.name) / "c.csv"
        combos.write_text(HEADER + "\nX,C1,6,2,BACK,,,,,,,,\n", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = pkg_matrix.main(["--base-url", "https://api.example.com", "--combos", str(combos),
                                    "--out", str(Path(tmp.name) / "o.tsv")], http=FakeHttp({}), sleep=lambda s: None)
        self.assertEqual(code, 2)
        self.assertIn("--allow-host api.example.com", stderr.getvalue())
        self.assertEqual(pkg_matrix.guard_host("https://api.example.com/", "api.example.com"),
                         "https://api.example.com")
        tmp.cleanup()

    def test_bad_wall_is_usage_error(self):
        code, *_ = run_matrix(["X,C1,6,2,SOUTH,,,,,,,,"], {})
        self.assertEqual(code, 2)


def run_policy(argv, pages=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    fetch = (lambda url: pages[url.split("example.test", 1)[1] or "/"]) if pages else None
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = copy_policy.main(argv, fetch=fetch) if fetch else copy_policy.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


FILLER = "가든스텝 정원 패키지는 내 공간 크기와 조건에 맞춰 식물과 바크를 골라 보내드려요. " * 6


class CopyPolicyTests(unittest.TestCase):
    def test_banned_copy_fails_with_context(self):
        pages = {"/": f"<html><body><p>{FILLER}</p><p>받은 뒤 48시간 안에 사진으로 알려 주세요</p>"
                      "<script>var x='마당';</script></body></html>"}
        code, out, err = run_policy(["--base-url", "https://dev.example.test", "--paths", "/"], pages)
        self.assertEqual(code, 1)
        rows = list(csv.DictReader(io.StringIO(out), delimiter="\t"))
        self.assertEqual([(r["pattern"], r["allowed"]) for r in rows], [("48시간", "no")])
        self.assertIn("받은 뒤 48시간 안에", rows[0]["snippet"])
        self.assertIn("위반 1건", err)

    def test_company_info_and_terms_are_allowed(self):
        footer = "상호 ㈜사람과초록 · 사업자등록번호 000-00-00000"
        pages = {"/": f"<p>{FILLER}</p><footer>{footer}</footer>",
                 "/terms": f"<p>{FILLER} 회사(사람과초록)는 다음과 같이 정합니다.</p>",
                 "/design": f"<p>{FILLER}</p><p>사람과초록 시공 사진</p>"}
        code, out, _ = run_policy(["--base-url", "https://dev.example.test", "--paths", "/", "/terms", "/design",
                                   "--report-only"], pages)
        self.assertEqual(code, 0)
        rows = {(r["path"], r["pattern"]): r for r in csv.DictReader(io.StringIO(out), delimiter="\t")}
        self.assertEqual(rows[("/", "사람과초록")]["allowed"], "yes")
        self.assertEqual(rows[("/terms", "사람과초록")]["allowed"], "yes")
        self.assertEqual(rows[("/design", "사람과초록 시공")]["allowed"], "no")

    def test_offline_html_dir_and_low_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "_policy_returns.html").write_text(f"<p>{FILLER}</p><p>이한결 정원 전문가</p>", encoding="utf-8")
            Path(tmp, "_cart.html").write_text("<div id='root'></div>", encoding="utf-8")
            code, out, err = run_policy(["--html-dir", tmp])
        rows = list(csv.DictReader(io.StringIO(out), delimiter="\t"))
        self.assertEqual(code, 1)
        self.assertIn(("/policy/returns", "이한결", "no"), [(r["path"], r["pattern"], r["allowed"]) for r in rows])
        self.assertIn(("/cart", "LOW_TEXT"), [(r["path"], r["pattern"]) for r in rows])
        self.assertIn("PASS로 적지 않는다", err)

    def test_production_host_is_refused(self):
        code, _, err = run_policy(["--base-url", "https://www.example.com"])
        self.assertEqual(code, 2)
        self.assertIn("DEV 주소로 보이지 않아", err)

    def test_default_policy_is_valid(self):
        policy = copy_policy.load_policy(copy_policy.DEFAULT_POLICY)
        self.assertIn("48시간", [rule["pattern"] for rule in policy["rules"]])


if __name__ == "__main__":
    unittest.main()
