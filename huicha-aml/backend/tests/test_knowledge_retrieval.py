from app.knowledge import retrieve_for_alert, search_knowledge, search_unit_count


def test_article_chunks_outnumber_catalog():
    assert search_unit_count() >= 150


def test_hybrid_prefers_ctr_article_14_for_exclusion_query():
    hits = search_knowledge("关掉告警要写排除理由 人工分析", kind="regulation", top_k=5)
    assert hits
    assert hits[0]["retrieval"] == "hybrid-keyword-tfidf"
    ids = [h["id"] for h in hits]
    assert "KB-CTR-03-a14" in ids or hits[0]["id"] == "KB-REG-02"
    # 向量通道应给出非零分（字符重叠）
    assert any(h.get("score_vector", 0) > 0 for h in hits)


def test_retrieve_for_alert_covers_str_core_and_typology():
    hits = retrieve_for_alert("拆分存入", "个人-无固定职业", as_of="2026-09-10")
    assert hits
    ids = [h["id"] for h in hits]
    parents = {h.get("parent_id") for h in hits}
    assert any(i.startswith("KB-TYP-") for i in ids)
    assert "KB-CTR-03" in parents or any(i.startswith("KB-REG-") for i in ids)
    # 同篇规章不应占满列表
    ctr_chunks = [i for i in ids if i.startswith("KB-CTR-03-")]
    assert len(ctr_chunks) <= 1
