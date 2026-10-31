"""Validate a bounded human/agent Figma comparison receipt, including local evidence."""
import hashlib
import json
from pathlib import Path

class ReceiptError(ValueError): pass

def validate(path, required_nodes, required_viewports, revision, required_checks=()):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('revision') != revision:
        raise ReceiptError('스키마 또는 FE revision 불일치')
    if not data.get('observed_at') or not data.get('source_checked_at') or not data.get('source_url'):
        raise ReceiptError('실측 시각/원본 확인 시각/Figma 출처 누락')
    cells = data.get('cells', [])
    required={(n,v) for n in required_nodes for v in required_viewports}
    actual={(c.get('node'),c.get('viewport')) for c in cells}
    if not required or not required.issubset(actual): raise ReceiptError('필요한 Figma 노드/viewport 누락')
    evidence={}
    contradictions=False
    for cell in cells:
        if cell.get('verdict') not in ('MATCH','MISMATCH','UNKNOWN'): raise ReceiptError('잘못된 판정')
        checks=cell.get('checks')
        if not isinstance(checks,list) or not checks: raise ReceiptError('요소별 대조 내역 누락')
        check_ids = {check.get('item') for check in checks}
        if not set(required_checks).issubset(check_ids): raise ReceiptError('필수 비교 항목 누락')
        for check in checks:
            if cell['verdict'] == 'MATCH' and check.get('expected') != check.get('actual'):
                contradictions=True
            if not all(isinstance(check.get(k),str) and check[k].strip() for k in ('item','expected','actual')):
                raise ReceiptError('기대값·실제값 누락')
        for field in ('figma_screenshot','actual_screenshot'):
            rel=cell.get(field)
            if not isinstance(rel,str) or not rel: raise ReceiptError('양쪽 화면 증거 누락')
            file=(path.parent/rel).resolve()
            if not file.is_relative_to(path.parent) or not file.is_file() or not file.stat().st_size: raise ReceiptError('증거 파일 누락/범위 벗어남')
            evidence[str(file.relative_to(path.parent))]=hashlib.sha256(file.read_bytes()).hexdigest()
    return {'receipt':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'evidence':evidence,
            'verdict':'FAIL' if contradictions or any(c['verdict']=='MISMATCH' for c in cells) else 'BLOCKED' if any(c['verdict']=='UNKNOWN' for c in cells) else 'PASS'}
