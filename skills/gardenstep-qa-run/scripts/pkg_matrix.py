#!/usr/bin/env python3
"""Run the PKG-MATRIX combos against DEV's public layout and quote APIs, one combo at a time.

Read-only: it calls only the design preview (POST /tier2/layout/preview-jobs, GET …/{jobId}) and the price
preview (POST /tier2/pricing/quote) that the design screen calls before an order. It never creates carts,
orders or payments and never sends auth headers.

  python3 pkg_matrix.py --base-url <DEV API 주소> --combos combos.csv --out runs/pkg-matrix.tsv \
      [--catalog bands.csv --reps reps.csv] [--save-json runs/pkg-matrix-json]
  python3 pkg_matrix.py --rescore-json runs/pkg-matrix-json --out runs/pkg-matrix-rescored.tsv \
      [--catalog bands.csv --reps reps.csv]      # 저장한 응답만 다시 채점(네트워크 호출 없음)

combos.csv header: combo_id,sku,width_m,depth_m,wall,light,floor,climate_zone,conditions,flower_chips,seed,expect,source
  conditions·flower_chips are '|'-separated. Blank light/floor/seed take the design screen defaults.
bands.csv header:  productCode,band,heightCm[,itemId]   (시트 상품등록 탭에서 뽑은 높이 밴드·다 자란 키)
reps.csv header:   package,rank,productCode[,itemId]   (시트 대표수종 탭의 패키지별 순위)
  API의 productCode는 시트 sku와 다를 수 있다(옛 코드가 남은 품목). itemId 열이 있으면 itemId로 먼저 맞춘다.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

COMBO_HEADER = ["combo_id", "sku", "width_m", "depth_m", "wall", "light", "floor", "climate_zone",
                "conditions", "flower_chips", "seed", "expect", "source"]
OUT_HEADER = ["combo_id", "sku", "width", "depth", "wall", "light", "layout_job", "layout_status", "quote",
              "set_plan_amount", "guide_amount", "option_amount", "package_amount", "total_amount",
              "shipping_amount", "delivery_label", "species", "plants", "trees", "height_band_violations",
              "fill_count", "engine_diagnostics", "api_internal_text", "wide_notice", "max_same_species_clusters",
              "wide_rule_ok", "tree_issue", "expect", "source", "note"]
WALLS = ("BACK", "LEFT", "RIGHT", "CORNER", "NONE")
LIGHTS = ("SUN", "PARTIAL_SHADE", "SHADE")
FLOORS = ("SOIL", "LAWN", "PAVED")
DEFAULT_SEED = 20260825  # 설계 화면(DesignScenesClient)의 기본 seed와 같다
GUIDE_REF = "GARDEN_GUIDE_V1"
# 넓은 공간 안내(selection.shortageRepeat)의 서버 규칙: 면적 때문에 반복(areaRepeat)하고 같은 품종이 3덩이 이상.
# areaRepeat는 응답에 없어, 응답으로 확인할 수 있는 필요조건(안내 ⇒ 3덩이 이상)만 본다. 작은 화단에서 앞줄을
# 채우려고 3덩이가 되는 것은 서버 기준상 안내 대상이 아니다.
WIDE_CLUSTER_RULE = 3
BAND_HEIGHT_TOLERANCE_CM = 15  # 대표와 밴드가 달라도 다 자란 키 차이 15cm 이내면 허용
# 엔진 내부 문구(QA에서 고객 화면에 보였던 것). API 응답에 있는지만 본다 — 화면이 숨기는지는 브라우저로
# 판정한다(api_internal_text는 정보 열). --internal-strings로 바꿀 수 있다.
INTERNAL_STRINGS = ["시드 간격", "배치 검토 항목", "필수 높이대", "확정 구성과 단가를 준비", "허용 높이대 품종으로",
                    "단식목의 성숙 크기", "구성과 가격 확인 중"]
# 나무 겹침·이탈을 서버가 직접 알려 주는 진단 코드. tree_issue에 server:로 합친다.
SERVER_TREE_CODES = ("TREE_CROWN_OVERLAP", "TREE_CROWN_OUTSIDE_BED")
SAFE_HOST_MARKERS = ("dev", "localhost", "127.0.0.1")
JOB_DEADLINE_S = 90.0


class MatrixError(ValueError):
    pass


@dataclass
class Response:
    status: int
    body: object
    headers: dict


HttpFn = Callable[[str, str, object], Response]


def urllib_http(method: str, url: str, payload: object) -> Response:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:
            raw, status, headers = reply.read(), reply.status, dict(reply.headers)
    except urllib.error.HTTPError as error:
        raw, status, headers = error.read(), error.code, dict(error.headers or {})
    try:
        body = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = None
    return Response(status, body, headers)


def guard_host(base_url: str, allow_host: str | None) -> str:
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise MatrixError(f"--base-url이 주소 형식이 아닙니다: {base_url}")
    if allow_host and host == allow_host.lower():
        return base_url.rstrip("/")
    if not any(marker in host for marker in SAFE_HOST_MARKERS):
        raise MatrixError(f"{host}는 DEV 주소로 보이지 않아 멈춥니다. DEV가 맞으면 --allow-host {host}로 다시 실행하세요.")
    return base_url.rstrip("/")


def split_list(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def default_light(sku: str, conditions: list[str]) -> str:
    if "SHADE" in conditions:
        return "SHADE"
    return "PARTIAL_SHADE" if sku == "C3" else "SUN"


def read_combos(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in COMBO_HEADER if name not in (reader.fieldnames or [])]
        if missing:
            raise MatrixError(f"{path}: 열이 없습니다 {missing}. 머리줄: {','.join(COMBO_HEADER)}")
        combos = []
        for line, row in enumerate(reader, 2):
            combos.append(parse_combo(row, f"{path.name}:{line}"))
    if not combos:
        raise MatrixError(f"{path}: 조합이 없습니다.")
    return combos


def parse_combo(row: dict, where: str) -> dict:
    sku = (row.get("sku") or "").strip().upper()
    wall = (row.get("wall") or "").strip().upper()
    if not sku or not (row.get("combo_id") or "").strip():
        raise MatrixError(f"{where}: combo_id와 sku가 필요합니다.")
    if wall not in WALLS:
        raise MatrixError(f"{where}: wall은 {'|'.join(WALLS)} 중 하나입니다.")
    try:
        width, depth = float(row["width_m"]), float(row["depth_m"])
        seed = int(row["seed"]) if (row.get("seed") or "").strip() else DEFAULT_SEED
    except (TypeError, ValueError) as error:
        raise MatrixError(f"{where}: width_m·depth_m·seed는 숫자여야 합니다.") from error
    conditions = split_list(row.get("conditions", ""))
    light = (row.get("light") or "").strip().upper() or default_light(sku, conditions)
    floor = (row.get("floor") or "").strip().upper() or "SOIL"
    if light not in LIGHTS or floor not in FLOORS:
        raise MatrixError(f"{where}: light는 {'|'.join(LIGHTS)}, floor는 {'|'.join(FLOORS)} 중 하나입니다.")
    chips = split_list(row.get("flower_chips", ""))
    return {"combo_id": row["combo_id"].strip(), "sku": sku, "width": width, "depth": depth, "wall": wall,
            "light": light, "floor": floor, "climate_zone": (row.get("climate_zone") or "").strip() or None,
            "conditions": conditions, "flower_chips": chips or None, "seed": seed,
            "expect": (row.get("expect") or "").strip(), "source": (row.get("source") or "").strip()}


def screening_length(combo: dict) -> float | None:
    """C6 가림 정원의 길이 축 — 설계 화면(designContract.screeningAxisLength)과 같은 규칙."""
    if combo["sku"] != "C6":
        return None
    uses_depth = combo["wall"] in ("LEFT", "RIGHT") or (combo["wall"] == "CORNER" and combo["depth"] > combo["width"])
    return combo["depth"] if uses_depth else combo["width"]


def layout_body(combo: dict) -> dict:
    return {"skuCode": combo["sku"], "widthM": combo["width"], "depthM": combo["depth"], "wallSide": combo["wall"],
            "floorType": combo["floor"], "climateZone": combo["climate_zone"], "conditions": combo["conditions"],
            "seed": combo["seed"], "enabledFlowerChips": combo["flower_chips"], "light": combo["light"],
            "exclusions": []}


def quote_body(combo: dict, artifact: dict | None) -> dict:
    body = {"skuCode": combo["sku"], "widthM": combo["width"], "depthM": combo["depth"],
            "lengthM": screening_length(combo), "conditions": combo["conditions"], "optionCodes": [],
            "zipcode": None, "wallSide": combo["wall"], "climateZone": combo["climate_zone"],
            "floorType": combo["floor"], "layoutConfigVersion": (artifact or {}).get("configVersion")}
    selection = (artifact or {}).get("selection")
    if selection:
        body.update({"layoutSeed": selection.get("seed"),
                     "layoutEnabledFlowerChips": selection.get("enabledFlowerChips"),
                     "layoutLight": combo["light"], "layoutCatalogVersion": selection.get("catalogVersion")})
    return body


class Client:
    """Strictly serial calls with 429 backoff. One instance per run."""

    def __init__(self, base: str, http: HttpFn, sleep: Callable[[float], None], max_retries: int,
                 clock: Callable[[], float] = time.monotonic):
        self.base, self.http, self.sleep, self.max_retries, self.clock = base, http, sleep, max_retries, clock
        self.throttled = 0

    def call(self, method: str, path: str, payload: object = None) -> Response:
        attempt = 0
        while True:
            response = self.http(method, self.base + path, payload)
            if response.status != 429 or attempt >= self.max_retries:
                return response
            self.throttled += 1
            self.sleep(retry_after(response.headers, attempt))
            attempt += 1


def retry_after(headers: dict, attempt: int) -> float:
    for key, value in (headers or {}).items():
        if key.lower() == "retry-after":
            try:
                return max(0.0, min(float(value), 300.0))
            except (TypeError, ValueError):
                break
    return float(min(2 ** (attempt + 1), 60))


def error_code(response: Response) -> str:
    body = response.body if isinstance(response.body, dict) else {}
    nested = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = body.get("code") or nested.get("code")
    return f"HTTP_{response.status}" + (f":{code}" if code else "")


def error_message(response: Response) -> str:
    body = response.body if isinstance(response.body, dict) else {}
    nested = body.get("error") if isinstance(body.get("error"), dict) else {}
    return str(body.get("message") or nested.get("message") or "")


def run_layout(client: Client, combo: dict) -> tuple[str, dict | None, str]:
    """Return (layout_job, artifact, message)."""
    response = client.call("POST", "/tier2/layout/preview-jobs", layout_body(combo))
    if response.status not in (200, 202) or not isinstance(response.body, dict):
        return error_code(response), None, error_message(response)
    job = response.body
    deadline = client.clock() + JOB_DEADLINE_S
    while True:
        status = job.get("status")
        if status == "SUCCEEDED" and isinstance(job.get("artifact"), dict):
            return "SUCCEEDED", job["artifact"], ""
        if status == "FAILED":
            error = job.get("error") or {}
            return f"FAILED:{error.get('code', '')}", None, str(error.get("message", ""))
        if status != "RUNNING" or not job.get("jobId"):
            return "BAD_JOB", None, f"알 수 없는 작업 상태 {status}"
        if client.clock() >= deadline:
            return "TIMEOUT", None, f"{int(JOB_DEADLINE_S)}초 안에 끝나지 않음"
        wait_ms = max(250, min(5000, int(job.get("retryAfterMs") or 1000)))
        client.sleep(wait_ms / 1000)
        response = client.call("GET", f"/tier2/layout/preview-jobs/{job['jobId']}")
        if response.status != 200 or not isinstance(response.body, dict):
            return error_code(response), None, error_message(response)
        job = response.body


def load_bands(catalog: Path | None, reps: Path | None) -> tuple[dict, dict]:
    """bands: productCode·itemId 둘 다로 찾는 {key: (band, heightCm)}. representatives: {(package, rank): [keys]}."""
    bands: dict[str, tuple[str, float | None]] = {}
    representatives: dict[tuple[str, int], list[str]] = {}
    if catalog:
        with catalog.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                height = (row.get("heightCm") or "").strip()
                value = (row.get("band", "").strip(), float(height) if height else None)
                for key in (row.get("itemId"), row.get("productCode")):
                    if key and key.strip():
                        bands[key.strip()] = value
    if reps:
        with reps.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                keys = [key.strip() for key in (row.get("itemId"), row.get("productCode")) if key and key.strip()]
                representatives[(row["package"].strip().upper(), int(row["rank"]))] = keys
    return bands, representatives


def band_of(bands: dict, *keys) -> tuple[str | None, tuple[str, float | None] | None]:
    for key in keys:
        if key and key in bands:
            return key, bands[key]
    return None, None


def band_violations(combo: dict, artifact: dict, bands: dict, representatives: dict) -> str:
    """Substitutes whose band differs from their representative's AND whose height differs by >15cm.

    `-` = 대체가 없거나 모두 확인해 위반 없음, `unchecked` = 대체가 있는데 밴드표로 확인하지 못함.
    서버 진단 HEIGHT_BAND_SUBSTITUTE_REJECTED는 서버가 위반 후보를 건너뛰었다는 정보라 위반이 아니다(engine_diagnostics).
    """
    found: list[str] = []
    unchecked = False
    selection = artifact.get("selection") or {}
    for plant in selection.get("selectedPlants") or []:
        if plant.get("bandViolation") is not None:  # 서버가 직접 알려 주면 그대로 쓴다
            if plant["bandViolation"]:
                found.append(f"{plant.get('productCode')}(서버 표시)")
            continue
        rank, stage = plant.get("representativeRank"), plant.get("stage")
        if rank is None or stage in (None, "MAIN", "FILL"):
            continue
        rep_keys = representatives.get((combo["sku"], int(rank))) or []
        code, value = band_of(bands, plant.get("itemId"), plant.get("productCode"))
        rep_code, rep_value = band_of(bands, *rep_keys)
        if not value or not rep_value:
            unchecked = True
            continue
        (band, height), (rep_band, rep_height) = value, rep_value
        if band == rep_band or height is None or rep_height is None:
            continue
        if abs(height - rep_height) > BAND_HEIGHT_TOLERANCE_CM:
            found.append(f"{code}({band} {height:g}){stage}→{rep_code}({rep_band} {rep_height:g})")
    if found:
        return "; ".join(found)
    return "unchecked" if unchecked else "-"


def diagnostic_codes(artifact: dict) -> str:
    """서버 진단 코드와 선정 경고를 '코드×개수'로. 정보 열이다(판정은 TC 기준으로)."""
    counts: dict[str, int] = {}
    for item in (artifact.get("snapshot") or {}).get("diagnostics") or []:
        code = str(item.get("code") or "")
        if code:
            counts[code] = counts.get(code, 0) + 1
    for warning in (artifact.get("selection") or {}).get("warnings") or []:
        code = f"warn:{warning}"
        counts[code] = counts.get(code, 0) + 1
    return "; ".join(f"{code}×{n}" if n > 1 else code for code, n in sorted(counts.items())) or "-"


def internal_hits(texts: list[str], patterns: list[str]) -> str:
    hits = [pattern for pattern in patterns if any(pattern in text for text in texts)]
    return "; ".join(hits)


def tree_issues(snapshot: dict) -> str:
    trees = snapshot.get("trees") or []
    width, depth = snapshot.get("widthM"), snapshot.get("depthM")
    issues: list[str] = []
    for i, tree in enumerate(trees):
        try:
            x, y, r = float(tree["xM"]), float(tree["yM"]), float(tree.get("crownRadiusM") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if width is not None and depth is not None and (x - r < -1e-6 or y - r < -1e-6
                                                        or x + r > width + 1e-6 or y + r > depth + 1e-6):
            issues.append(f"outside:{tree.get('productCode')}")
        for other in trees[i + 1:]:
            try:
                ox, oy, orad = float(other["xM"]), float(other["yM"]), float(other.get("crownRadiusM") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if math.hypot(x - ox, y - oy) < r + orad - 1e-6:
                issues.append(f"overlap:{tree.get('productCode')}/{other.get('productCode')}")
    for item in snapshot.get("diagnostics") or []:
        if item.get("code") in SERVER_TREE_CODES:
            issues.append(f"server:{item.get('code')}")
    return "; ".join(issues) or "-"


def amount(value) -> str:
    return "" if value is None else str(value)


def evaluate(combo: dict, layout_job: str, artifact: dict | None, layout_message: str, quote: Response | None,
             bands: dict, representatives: dict, patterns: list[str]) -> dict:
    row = {name: "" for name in OUT_HEADER}
    row.update({"combo_id": combo["combo_id"], "sku": combo["sku"], "width": f"{combo['width']:g}",
                "depth": f"{combo['depth']:g}", "wall": combo["wall"], "light": combo["light"],
                "layout_job": layout_job, "expect": combo["expect"], "source": combo["source"]})
    notes: list[str] = []
    texts = [layout_message] if layout_message else []
    if artifact:
        row["layout_status"] = artifact.get("status", "")
        if artifact.get("reason"):
            texts.append(str(artifact["reason"]))
        selection = artifact.get("selection") or {}
        snapshot = artifact.get("snapshot") or {}
        texts += [str(item) for item in selection.get("warnings") or []]
        texts += [str(item.get("message", "")) for item in snapshot.get("diagnostics") or []]
        plants = [line for line in snapshot.get("bom") or []]
        tree_list = snapshot.get("trees") or []
        tree_codes = {tree.get("productCode") for tree in tree_list}
        row["species"] = str(len({line.get("productCode") for line in plants}))
        row["plants"] = str(sum(int(line.get("quantity") or 0) for line in plants
                                if line.get("productCode") not in tree_codes))
        row["trees"] = str(len(tree_list)) + (
            f" ({', '.join(sorted({str(t.get('label') or t.get('productCode')) for t in tree_list}))})"
            if tree_list else "")
        row["fill_count"] = str(sum(1 for plant in selection.get("selectedPlants") or []
                                    if plant.get("stage") == "FILL"))
        row["height_band_violations"] = band_violations(combo, artifact, bands, representatives)
        row["engine_diagnostics"] = diagnostic_codes(artifact)
        clusters: dict[str, int] = {}
        for cluster in snapshot.get("clusters") or []:
            clusters[cluster.get("productCode")] = clusters.get(cluster.get("productCode"), 0) + 1
        most = max(clusters.values(), default=0)
        wide = bool(selection.get("shortageRepeat"))
        row["wide_notice"] = "yes" if wide else "no"
        row["max_same_species_clusters"] = str(most)
        row["wide_rule_ok"] = "no" if wide and most < WIDE_CLUSTER_RULE else "yes"
        if most >= WIDE_CLUSTER_RULE and not wide:
            notes.append(f"같은 품종 {most}덩이지만 넓은 공간 안내 없음(면적 반복 아님 — 서버 기준 정상)")
        row["tree_issue"] = tree_issues(snapshot) if snapshot else "-"
    else:
        row["height_band_violations"] = "n/a"  # 배치도가 없어(입력 거절·작업 실패) 볼 대체가 없다
        row["engine_diagnostics"] = "-"
    if layout_message:
        notes.append(f"layout: {layout_message}")
    if quote is None:
        row["quote"] = "NOT_CALLED"
    elif quote.status == 200 and isinstance(quote.body, dict):
        body = quote.body
        row["quote"] = "OK"
        items = body.get("items") or []
        set_plan = next((item for item in items if item.get("type") == "SET_PLAN"), None)
        guide = next((item for item in items if item.get("ref") == GUIDE_REF), None)
        row["set_plan_amount"] = amount((set_plan or {}).get("amount"))
        row["guide_amount"] = amount((guide or {}).get("amount", body.get("guideAmount")))
        row["option_amount"] = amount(body.get("optionAmount"))
        row["package_amount"] = amount(body.get("packageAmount"))
        row["total_amount"] = amount(body.get("totalAmount"))
        row["shipping_amount"] = amount(body.get("shippingAmount"))
        row["delivery_label"] = str((body.get("packageDelivery") or {}).get("label") or "")
        if body.get("reason"):
            texts.append(str(body["reason"]))
        if "packageAmount" not in body:
            notes.append("견적 응답에 packageAmount 없음(가이드 줄 계약 이전 서버?)")
    else:
        row["quote"] = error_code(quote)
        message = error_message(quote)
        if message:
            texts.append(message)
            notes.append(f"quote: {message}")
    row["api_internal_text"] = internal_hits(texts, patterns) or "-"
    row["note"] = " | ".join(notes)
    return row


def run(combos: list[dict], client: Client, bands: dict, representatives: dict, patterns: list[str],
        pause: float, save_json: Path | None) -> list[dict]:
    rows = []
    for index, combo in enumerate(combos):
        if index and pause:
            client.sleep(pause)
        layout_job, artifact, message = run_layout(client, combo)
        quote = client.call("POST", "/tier2/pricing/quote", quote_body(combo, artifact))
        rows.append(evaluate(combo, layout_job, artifact, message, quote, bands, representatives, patterns))
        if save_json:
            save_json.mkdir(parents=True, exist_ok=True)
            (save_json / f"{combo['combo_id']}.json").write_text(json.dumps(
                {"combo": combo, "layout_job": layout_job, "layout_message": message, "artifact": artifact,
                 "quote": {"status": quote.status, "body": quote.body}}, ensure_ascii=False, indent=1),
                encoding="utf-8")
        print(f"[{index + 1}/{len(combos)}] {combo['combo_id']} {rows[-1]['layout_status'] or layout_job} "
              f"quote={rows[-1]['quote']}", file=sys.stderr)
    return rows


def rescore(json_dir: Path, bands: dict, representatives: dict, patterns: list[str]) -> list[dict]:
    """--save-json으로 남긴 응답을 네트워크 없이 다시 채점한다. 조합 순서는 파일 안 combo_id 순서를 따른다."""
    rows = []
    files = sorted(json_dir.glob("*.json"))
    if not files:
        raise MatrixError(f"{json_dir}: 저장된 응답(*.json)이 없습니다.")
    for path in files:
        saved = json.loads(path.read_text(encoding="utf-8"))
        quote = saved.get("quote")
        response = None if quote is None else Response(int(quote.get("status") or 0), quote.get("body"), {})
        rows.append(evaluate(saved["combo"], saved.get("layout_job", ""), saved.get("artifact"),
                             saved.get("layout_message") or "", response, bands, representatives, patterns))
    return rows


def summary(rows: list[dict], throttled: int | None) -> str:
    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))

    statuses: dict[str, int] = {}
    for row in rows:
        key = row["layout_status"] or row["layout_job"]
        statuses[key] = statuses.get(key, 0) + 1
    lines = [f"조합 {len(rows)}개 · 배치도 " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())),
             f"견적 OK {count(lambda r: r['quote'] == 'OK')} · 409 {count(lambda r: r['quote'].startswith('HTTP_409'))}"
             f" · 그 밖 {count(lambda r: r['quote'] != 'OK' and not r['quote'].startswith('HTTP_409'))}",
             f"높이 밴드 위반 {count(lambda r: r['height_band_violations'] not in ('-', 'unchecked', 'n/a'))}"
             f" · 확인 못 함 {count(lambda r: r['height_band_violations'] == 'unchecked')}"
             f" · 배치도 없음 {count(lambda r: r['height_band_violations'] == 'n/a')}",
             f"넓은 공간 안내 기준 불일치(안내인데 같은 품종 3덩이 미만) {count(lambda r: r['wide_rule_ok'] == 'no')}"
             f" · 나무 겹침·이탈 {count(lambda r: r['tree_issue'] not in ('', '-'))}",
             f"참고(API 수준, 화면 판정 아님): 응답에 엔진 내부 문구 {count(lambda r: r['api_internal_text'] != '-')}"
             f" · 서버 진단 코드 있음 {count(lambda r: r['engine_diagnostics'] not in ('', '-'))}"]
    if throttled is not None:
        lines.append(f"429 재시도 {throttled}회 · 429로 끝난 조합 "
                     f"{count(lambda r: 'HTTP_429' in r['layout_job'] or 'HTTP_429' in r['quote'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, http: HttpFn = urllib_http,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="DEV API 주소. 운영으로 보이면 멈춘다")
    parser.add_argument("--allow-host", help="이름에 dev가 없는 DEV 호스트를 명시적으로 허용")
    parser.add_argument("--combos", help="조합 CSV(실행할 때 필수)")
    parser.add_argument("--rescore-json", help="--save-json 폴더를 네트워크 없이 다시 채점")
    parser.add_argument("--out", required=True)
    parser.add_argument("--catalog", help="productCode,band,heightCm (높이 밴드 검사용)")
    parser.add_argument("--reps", help="package,rank,productCode (대표수종 순위)")
    parser.add_argument("--internal-strings", help="내부 문구 목록 파일(한 줄에 하나)")
    parser.add_argument("--sleep", type=float, default=0.5, help="조합 사이 쉬는 초")
    parser.add_argument("--max-retries", type=int, default=5, help="429 재시도 횟수")
    parser.add_argument("--save-json", help="조합별 원본 응답을 남길 폴더(증거용, 공개 시트에 붙이지 않는다)")
    args = parser.parse_args(argv)
    try:
        if not args.rescore_json and not (args.base_url and args.combos):
            raise MatrixError("--base-url과 --combos가 필요합니다(저장한 응답만 다시 채점하려면 --rescore-json).")
        bands, representatives = load_bands(Path(args.catalog) if args.catalog else None,
                                            Path(args.reps) if args.reps else None)
        patterns = INTERNAL_STRINGS
        if args.internal_strings:
            patterns = [line.strip() for line in Path(args.internal_strings).read_text(encoding="utf-8").splitlines()
                        if line.strip()]
    except (MatrixError, OSError, KeyError, ValueError) as error:
        print(f"실행하지 않았습니다: {error}", file=sys.stderr)
        return 2
    if args.rescore_json:
        try:
            rows, throttled = rescore(Path(args.rescore_json), bands, representatives, patterns), None
        except (MatrixError, OSError, KeyError, ValueError) as error:
            print(f"다시 채점하지 못했습니다: {error}", file=sys.stderr)
            return 2
    else:
        try:
            base = guard_host(args.base_url, args.allow_host)
            combos = read_combos(Path(args.combos))
        except (MatrixError, OSError, ValueError) as error:
            print(f"실행하지 않았습니다: {error}", file=sys.stderr)
            return 2
        client = Client(base, http, sleep, args.max_retries, clock)
        rows = run(combos, client, bands, representatives, patterns, args.sleep,
                   Path(args.save_json) if args.save_json else None)
        throttled = client.throttled
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"만듦: {out}")
    print(summary(rows, throttled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
