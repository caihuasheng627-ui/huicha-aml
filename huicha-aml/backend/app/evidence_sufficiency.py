"""有界贪心最小充分证据集：不宣称数学全局最小。"""

from __future__ import annotations

from .reliability import compute_reliability
from .schema import EvidenceSufficiency

MAX_CANDIDATES = 4
MAX_ROUNDS = 3


def support_cluster(findings: list[dict], evidence_id: str) -> tuple[set[str], dict | None]:
    key_id = str(evidence_id or "")
    finding = next(
        (f for f in findings if key_id in (f.get("evidence_ids") or []) and f.get("polarity") == "support"),
        None,
    )
    removed = set((finding or {}).get("evidence_ids") or [key_id])
    return {str(x) for x in removed if str(x)}, finding


def drop_findings(findings: list[dict], removed_ids: set[str]) -> list[dict]:
    cf_findings = []
    for finding in findings:
        kept_ids = [e for e in (finding.get("evidence_ids") or []) if e not in removed_ids]
        if finding.get("evidence_ids") and not kept_ids and finding.get("polarity") != "context":
            continue
        cf_findings.append({**finding, "evidence_ids": kept_ids})
    return cf_findings


def _as_unique(ids) -> list[str]:
    out: list[str] = []
    for item in ids or []:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def used_evidence_ids(judge: dict) -> list[str]:
    ids: list[str] = []
    for row in judge.get("rationale") or []:
        ids.extend(row.get("evidence_ids") or [])
        args = row.get("args") if isinstance(row.get("args"), dict) else {}
        ids.extend(args.get("tx_ids") or [])
    return _as_unique(ids)


def cited_support_ids(judge: dict) -> list[str]:
    return _as_unique(judge.get("supporting_evidence_ids") or [])


def default_counterfactual(judge: dict, *, note: str = "") -> dict:
    return {
        "performed": False,
        "faithful": None,
        "removed_evidence_ids": [],
        "original_conclusion": (judge or {}).get("disposition") or "",
        "counterfactual_conclusion": "",
        "note": note or "无可剔除的关键支持证据，未执行 AI 反事实。",
    }


def map_counterfactual(
    *,
    original: dict,
    removed_ids: set[str],
    cf_judge: dict | None,
    cf_valid: dict | None,
    error: str = "",
) -> dict:
    original_disp = original.get("disposition") or ""
    if error and not cf_judge:
        result = default_counterfactual(original, note=f"反事实执行失败：{error}")
        result["validated"] = False
        return result
    passed = bool((cf_valid or {}).get("passed"))
    cf_disp = (cf_judge or {}).get("disposition") or ""
    changed = bool(cf_disp) and cf_disp != original_disp
    if not passed:
        note = "反事实轮次输出未通过引用校验，无法判断建议是否依赖该证据，已标记供人工复核"
        faithful = None
    elif changed:
        note = "移除模型声明的关键证据后建议随之变化"
        faithful = True
    else:
        note = "移除关键证据后建议未变化，已标记供人工复核"
        faithful = False
    return {
        "performed": True,
        "faithful": faithful,
        "validated": passed,
        "validation_issues": (cf_valid or {}).get("issues") or [],
        "removed_evidence_ids": sorted(removed_ids),
        "original_conclusion": original_disp,
        "counterfactual_conclusion": cf_disp,
        "note": note,
    }


def build_candidates(
    judge: dict,
    findings: list[dict],
    verified_claims: list[dict],
    *,
    max_candidates: int = MAX_CANDIDATES,
) -> list[dict]:
    candidates: list[dict] = []
    covered: set[frozenset[str]] = set()

    def add(kind: str, evidence_ids: list[str], *, title: str = "", predicate: str = "") -> None:
        ids = _as_unique(evidence_ids)
        if not ids:
            return
        key = frozenset(ids)
        if key in covered:
            return
        covered.add(key)
        candidates.append(
            {
                "kind": kind,
                "title": title,
                "predicate": predicate,
                "evidence_ids": ids,
                "status": "pending",
            }
        )

    support = cited_support_ids(judge)
    if support:
        cluster, finding = support_cluster(findings, support[0])
        add(
            "support_cluster",
            sorted(cluster),
            title=(finding or {}).get("title") or support[0],
        )
    for claim in verified_claims or []:
        add(
            "verified_claim",
            claim.get("evidence_ids") or [],
            title=str(claim.get("claim") or "")[:80],
            predicate=str(claim.get("predicate") or ""),
        )
    for finding in findings or []:
        if finding.get("polarity") != "support":
            continue
        add("support_cluster", finding.get("evidence_ids") or [], title=finding.get("title") or finding.get("code") or "")
    return candidates[: max(0, int(max_candidates))]


def _cf_reliability_committed(cf_judge: dict | None, cf_valid: dict | None, baseline: dict | None, leftover: list[str]) -> bool:
    """同一档且引用通过时，再看 CF 本身能否形成可签发倾向；弃权则视为该簇仍必要。"""
    dummy = {"verified": True, "necessary_ids": list(leftover) or ["_cf_probe"]}
    reliability = compute_reliability(
        use_challenger=True,
        judge=cf_judge or {},
        judge_validation=cf_valid or {},
        baseline=baseline or {},
        counterfactual={"performed": False},
        evidence_sufficiency=dummy,
    )
    return reliability.get("stance") == "committed"


def search_minimal_set(
    *,
    judge: dict,
    findings: list[dict],
    verified_claims: list[dict] | None = None,
    run_round,
    max_candidates: int = MAX_CANDIDATES,
    max_rounds: int = MAX_ROUNDS,
    baseline: dict | None = None,
) -> tuple[dict, dict]:
    """反向贪心删除。run_round(removed_ids, message) -> {judge, validation, error}。"""
    original_disp = judge.get("disposition") or ""
    used = used_evidence_ids(judge)
    support = cited_support_ids(judge)
    unused = [eid for eid in support if eid not in used]
    candidates = build_candidates(judge, findings, verified_claims or [], max_candidates=max_candidates)
    all_possible = build_candidates(judge, findings, verified_claims or [], max_candidates=max(max_candidates, 32))
    working_removed = set(unused)
    necessary: list[str] = []
    redundant: list[str] = list(unused)
    rounds = 0
    first_cf = default_counterfactual(judge)
    first_error = ""

    for cand in candidates:
        leftover = [eid for eid in cand["evidence_ids"] if eid not in working_removed]
        if not leftover:
            cand["status"] = "redundant"
            continue
        if rounds >= max_rounds:
            cand["status"] = "untested"
            continue
        cluster = set(leftover)
        finding_title = cand.get("title") or leftover[0]
        is_first = rounds == 0
        rounds += 1
        removed_for_round = cluster if is_first else (set(working_removed) | cluster)
        try:
            payload = run_round(removed_for_round, f"移除指标「{finding_title}」及其证据后重新判断")
        except (RuntimeError, ValueError) as exc:
            payload = {"error": str(exc), "judge": None, "validation": {"passed": False, "issues": []}}
        error = str(payload.get("error") or "")
        cf_judge = payload.get("judge")
        cf_valid = payload.get("validation") or {}
        mapped = map_counterfactual(
            original=judge,
            removed_ids=cluster,
            cf_judge=cf_judge,
            cf_valid=cf_valid,
            error=error,
        )
        if rounds == 1:
            first_cf = mapped
            first_error = error
            if error and not mapped.get("performed"):
                break
        passed = bool(mapped.get("validated"))
        same = mapped.get("counterfactual_conclusion") == original_disp
        cf_committed = _cf_reliability_committed(cf_judge, cf_valid, baseline, leftover) if (mapped.get("performed") and passed and same) else False
        if mapped.get("performed") and passed and same and cf_committed:
            cand["status"] = "redundant"
            for eid in leftover:
                if eid not in redundant:
                    redundant.append(eid)
            working_removed |= cluster
        else:
            cand["status"] = "necessary"
            for eid in leftover:
                if eid not in necessary:
                    necessary.append(eid)

    untested = [c for c in candidates if c.get("status") in {"pending", "untested"}]
    truncated = len(all_possible) > len(candidates)
    budget_exhausted = bool(untested or truncated or (first_error and rounds <= 1 and not first_cf.get("performed")))
    universe = _as_unique([*used, *support])
    minimal = [eid for eid in universe if eid not in redundant]
    if not minimal:
        minimal = list(necessary) or list(universe)
    performed = bool(first_cf.get("performed")) or bool(unused)
    if not support and not used:
        note = "无支持引用，未搜索最小证据集。"
        verified = True
        budget_exhausted = False
    elif not candidates:
        note = "无可分拆候选簇，沿用当前引用集合。"
        verified = True
        budget_exhausted = False
        performed = False
    elif budget_exhausted:
        note = "有界贪心预算耗尽，结果不是全局最小充分集。"
        verified = False
    else:
        note = "有界贪心已在候选预算内收敛；不宣称数学全局最小。"
        verified = True

    sufficiency = EvidenceSufficiency(
        method="bounded_greedy",
        verified=verified,
        budget_exhausted=budget_exhausted,
        performed=performed,
        rounds=rounds,
        max_rounds=max_rounds,
        max_candidates=max_candidates,
        minimal_sufficient_set=minimal,
        necessary_ids=necessary,
        redundant_ids=redundant,
        candidates=candidates,
        note=note,
    ).model_dump()
    return sufficiency, first_cf
