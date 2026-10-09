import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import qa_record  # noqa: E402
import tc_cards  # noqa: E402
from qa_sheet import load_tab  # noqa: E402

TC_HEADER = ["ID", "우선순위", "영역", "테스트 의도", "화면", "준비 데이터", "선행조건", "절차", "합격 기준",
             "현재 사전판정", "연결 이슈", "TC 버전"]
TC_ROWS = [
    ["A-01", "P0", "탐색", "데스크톱 메뉴", "/", "BASE", "1280px", "1. 접속 2. 상단 GNB 읽기 3. 우측 CTA 확인",
     "GNB 4개 + 우측 AI 정원 설계. 정원 가이드 없음", "실행 가능", "", "1.0"],
    ["P-22", "P0", "운영", "검수 확정", "/orders", "PG-LIVE", "P-05", "1. 저장 2. 확정",
     '3: 미리보기만. 4: "검수를 확정했습니다. 다시 확인하세요." 6: 다운로드', "", "R52 R10", "1.2"],
    ["G-05", "P1", "견적", "카카오 저장", "/estimate", "BASE", "", "저장 누르기",
     "완료를 안내한다.\n실패하면 입력을 유지한다.", "", "R06", "1.1"],
]
ISSUE_HEADER = ["이슈 ID", "우선순위", "유형", "현상", "영향 TC", "근거", "완료 조건", "담당 제안", "상태"]
ISSUE_ROWS = [["R52", "P0", "기능 결함", "검수 저장 400\n상세 줄", "P-22", "", "저장 성공", "", "FIXED_DEV"]]


def _col(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_xml(rows):
    out = ['<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r, row in enumerate(rows, 1):
        out.append(f'<row r="{r}">')
        for c, value in enumerate(row):
            text = (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            out.append(f'<c r="{_col(c)}{r}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def make_xlsx(path: Path, tabs: dict[str, list[list[str]]]) -> None:
    sheets = "".join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(tabs, 1))
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
        f' Target="worksheets/sheet{i}.xml"/>' for i, _ in enumerate(tabs, 1))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml",
                         '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                         f"<sheets>{sheets}</sheets></workbook>")
        archive.writestr("xl/_rels/workbook.xml.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         f"{rels}</Relationships>")
        for i, rows in enumerate(tabs.values(), 1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))


def run_main(module, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = module.main(argv)
    return code, out.getvalue(), err.getvalue()


class SplitTests(unittest.TestCase):
    def test_numbered_procedure_becomes_steps(self):
        self.assertEqual(tc_cards.split_steps("1. 접속 2. 상단 GNB 읽기 3. 우측 CTA 확인"),
                         ["접속", "상단 GNB 읽기", "우측 CTA 확인"])

    def test_unnumbered_procedure_stays_one_step(self):
        self.assertEqual(tc_cards.split_steps("저장 누르기"), ["저장 누르기"])

    def test_sentences_split_but_quoted_copy_stays_whole(self):
        checks = tc_cards.split_checks('안내 “저장했습니다. 다시 보세요.”를 띄운다. 목록에 1건')
        self.assertEqual(checks, ["안내 “저장했습니다. 다시 보세요.”를 띄운다.", "목록에 1건"])

    def test_step_keyed_criteria_become_one_check_per_step(self):
        checks = tc_cards.split_checks('3: 미리보기만. 4: "검수를 확정했습니다. 다시 확인하세요." 6: 다운로드')
        self.assertEqual(checks, ["절차 3: 미리보기만.", '절차 4: "검수를 확정했습니다. 다시 확인하세요."',
                                  "절차 6: 다운로드"])

    def test_line_breaks_split_checks(self):
        self.assertEqual(tc_cards.split_checks("완료를 안내한다.\n실패하면 입력을 유지한다."),
                         ["완료를 안내한다.", "실패하면 입력을 유지한다."])


class CardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.xlsx = Path(self.tmp.name) / "qa.xlsx"
        make_xlsx(self.xlsx, {"00 먼저읽기": [["안내"], ["PASS", "모든 기대 결과 확인. 증거 필수."],
                                                ["자동실행 표기", "실행자 칸은 책임자(사람)만 기재."], ["PASS", "20"]],
                              "01 TC정의": [TC_HEADER] + TC_ROWS,
                              "04 결함과결정": [ISSUE_HEADER] + ISSUE_ROWS})

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_tab_by_name(self):
        rows = load_tab(self.xlsx, "01 TC정의")
        self.assertEqual([row["ID"] for row in rows], ["A-01", "P-22", "G-05"])

    def test_card_lists_numbered_checks_and_linked_issue_first_line(self):
        code, out, _ = run_main(tc_cards, [str(self.xlsx), "--ids", "P-22"])
        self.assertEqual(code, 0)
        self.assertIn("## P-22 · P0 · v1.2", out)
        self.assertIn('[C2] 절차 4: "검수를 확정했습니다. 다시 확인하세요."', out)
        self.assertIn("연결 이슈 R52 [FIXED_DEV]: 검수 저장 400 (상세는 04 탭)", out)
        self.assertNotIn("상세 줄", out)

    def test_filters_by_issue_and_reports_missing_ids(self):
        code, out, _ = run_main(tc_cards, [str(self.xlsx), "--issue", "R52", "--list"])
        self.assertEqual((code, out.split("\t")[0]), (0, "P-22"))
        code, _, err = run_main(tc_cards, [str(self.xlsx), "--ids", "A-01,Z-99"])
        self.assertEqual(code, 0)
        self.assertIn("시트에 없는 TC ID: Z-99", err)

    def test_rules_come_from_sheet_tab_and_skip_counters(self):
        code, out, _ = run_main(tc_cards, [str(self.xlsx), "--rules"])
        self.assertEqual(code, 0)
        self.assertIn("- PASS: 모든 기대 결과 확인. 증거 필수.", out)
        self.assertIn("- 자동실행 표기: 실행자 칸은 책임자(사람)만 기재.", out)
        self.assertNotIn("- PASS: 20", out)
        self.assertNotIn("안내", out.split("\n", 2)[2])

    def test_rules_need_xlsx(self):
        csv_path = Path(self.tmp.name) / "tc.csv"
        csv_path.write_text(",".join(TC_HEADER) + "\n", encoding="utf-8")
        code, _, err = run_main(tc_cards, [str(csv_path), "--rules"])
        self.assertEqual(code, 2)
        self.assertIn("xlsx", err)

    def test_csv_of_tc_tab_works(self):
        csv_path = Path(self.tmp.name) / "tc.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows([TC_HEADER] + TC_ROWS)
        code, out, _ = run_main(tc_cards, [str(csv_path), "--area", "A"])
        self.assertEqual(code, 0)
        self.assertIn("[C2] 정원 가이드 없음", out)

    def test_unknown_tab_is_a_clear_error(self):
        broken = Path(self.tmp.name) / "broken.xlsx"
        make_xlsx(broken, {"다른 탭": [["x"]]})
        code, _, err = run_main(tc_cards, [str(broken), "--ids", "A-01"])
        self.assertEqual(code, 2)
        self.assertIn("01 TC정의", err)


def check(status, evidence=True, **extra):
    item = {"id": "C1", "criterion": "기준", "status": status, "observed": "본 것"}
    if evidence:
        item["evidence"] = ["shots/a.png"]
    item.update(extra)
    return item


def result(checks, **extra):
    data = {"tc_id": "A-01", "tc_version": "1.0", "viewport": "PC 1280×720", "preconditions_met": True,
            "checks": checks}
    data.update(extra)
    return data


class VerdictTests(unittest.TestCase):
    def test_all_match_with_evidence_is_pass(self):
        self.assertEqual(qa_record.decide(result([check("일치")]))[0], "PASS")

    def test_any_mismatch_is_fail_even_with_matches(self):
        verdict, line = qa_record.decide(result([check("일치"), check("불일치")], issue_id="R13"))
        self.assertEqual(verdict, "FAIL")
        self.assertIn("이슈 R13", line)

    def test_unverified_check_blocks_pass(self):
        self.assertEqual(qa_record.decide(result([check("일치"), check("확인불가", evidence=False)]))[0],
                         "BLOCKED")

    def test_match_without_evidence_is_rejected(self):
        with self.assertRaisesRegex(qa_record.RecordError, "evidence"):
            qa_record.decide(result([check("일치", evidence=False)]))

    def test_vague_or_missing_observation_is_rejected(self):
        with self.assertRaisesRegex(qa_record.RecordError, "observed"):
            qa_record.decide(result([check("일치", observed="  ")]))

    def test_unknown_status_is_rejected(self):
        with self.assertRaisesRegex(qa_record.RecordError, "status"):
            qa_record.decide(result([check("PASS")]))

    def test_unmet_precondition_needs_reason(self):
        with self.assertRaisesRegex(qa_record.RecordError, "blocked_reason"):
            qa_record.decide(result([], preconditions_met=False))
        verdict, line = qa_record.decide(result([], preconditions_met=False, blocked_reason="P-05 FAIL"))
        self.assertEqual(verdict, "BLOCKED")
        self.assertIn("P-05 FAIL", line)

    def test_na_requires_human_decider(self):
        with self.assertRaisesRegex(qa_record.RecordError, "na_decided_by"):
            qa_record.decide(result([], na_reason="이번 회차 제외"))
        self.assertEqual(qa_record.decide(result([], na_reason="제외", na_decided_by="JD"))[0], "N/A")

    def test_empty_checks_are_rejected(self):
        with self.assertRaisesRegex(qa_record.RecordError, "checks"):
            qa_record.decide(result([]))


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "QA-20261010-01.tsv"
        self.meta = {"run_id": "QA-20261010-01", "env": "DEV FE 6a3cdca2", "runner": "QA"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_row_matches_execution_log_columns_and_format(self):
        row = qa_record.build_row(self.meta, result([check("일치")]), now=datetime(2026, 10, 10, 11, 30))
        self.assertEqual(len(row), len(qa_record.HEADER))
        self.assertEqual(row[6:8], ["11:30:00", "PASS"])
        self.assertTrue(row[8].startswith("[결론] 기준과 일치 → PASS\n• C1 기준(일치): 본 것"))
        self.assertEqual(row[9], "shots/a.png")

    def test_model_run_rows_get_auto_execution_marker_once(self):
        meta = dict(self.meta, tool="Claude+Playwright")
        row = qa_record.build_row(meta, result([check("일치")]))
        self.assertEqual(row[3], "[자동실행 · Claude+Playwright] PC 1280×720")
        again = qa_record.build_row(meta, result([check("일치")], viewport=row[3]))
        self.assertEqual(again[3], row[3])

    def test_human_run_rows_have_no_marker(self):
        self.assertEqual(qa_record.build_row(self.meta, result([check("일치")]))[3], "PC 1280×720")

    def test_sensitive_values_are_refused(self):
        for leaked in ("010-1234-5678", "qa@example.com", "token=abc123"):
            with self.subTest(leaked=leaked), self.assertRaisesRegex(qa_record.RecordError, "가리고"):
                qa_record.build_row(self.meta, result([check("일치", observed=f"화면에 {leaked}")]))

    def test_bad_tc_id_is_refused(self):
        with self.assertRaisesRegex(qa_record.RecordError, "tc_id"):
            qa_record.build_row(self.meta, result([check("일치")], tc_id="A1"))

    def test_init_add_summary_round_trip(self):
        code, _, err = run_main(qa_record, ["init", "--out", str(self.run), "--run-id", "QA-20261010-01",
                                            "--env", "DEV FE 6a3cdca2, BE 297e3873", "--runner", "QA",
                                            "--tool", "Claude+Playwright"])
        self.assertEqual(code, 0, err)
        result_path = Path(self.tmp.name) / "r.json"
        result_path.write_text(json.dumps(result([check("불일치")], issue_id="R13"), ensure_ascii=False),
                               encoding="utf-8")
        code, out, err = run_main(qa_record, ["add", "--run", str(self.run), str(result_path)])
        self.assertEqual(code, 0, err)
        self.assertIn("A-01 → FAIL", out)
        with self.run.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        self.assertEqual(rows[0], qa_record.HEADER)
        self.assertEqual(rows[1][7], "FAIL")
        self.assertTrue(rows[1][3].startswith("[자동실행 · Claude+Playwright]"))
        code, out, _ = run_main(qa_record, ["summary", "--run", str(self.run)])
        self.assertIn("FAIL 1", out)
        self.assertIn("- A-01", out)

    def test_init_refuses_guessed_or_missing_env_and_bad_run_id(self):
        code, _, err = run_main(qa_record, ["init", "--out", str(self.run), "--run-id", "QA-1",
                                            "--env", "DEV FE 6a3cdca2", "--runner", "QA"])
        self.assertEqual(code, 1)
        self.assertIn("QA-YYYYMMDD-NN", err)
        code, _, err = run_main(qa_record, ["init", "--out", str(self.run), "--run-id", "QA-20261010-01",
                                            "--env", "DEV 최신", "--runner", "QA"])
        self.assertEqual(code, 1)
        self.assertIn("SHA", err)

    def test_rejected_result_is_not_appended(self):
        run_main(qa_record, ["init", "--out", str(self.run), "--run-id", "QA-20261010-01",
                             "--env", "DEV 확인 불가(gh 권한 없음)", "--runner", "QA"])
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text(json.dumps(result([check("일치", evidence=False)]), ensure_ascii=False), encoding="utf-8")
        code, _, _ = run_main(qa_record, ["add", "--run", str(self.run), str(bad)])
        self.assertEqual(code, 1)
        self.assertEqual(len(self.run.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
