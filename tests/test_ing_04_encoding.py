"""TC-ING-04 编码与老格式策略【单测｜M1——双后端参数化（服务层）+ 纯函数】。

- ① 上传 GBK 编码 TXT → 编码探测并转 UTF-8 后正常摄取（chunks 内容为解码文本）；
- ② `.doc/.xls/.ppt` 明确拒收并提示转存新格式（不引入 LibreOffice——零中间件
  纪律）；拒收发生在对象落盘**之前**（无孤儿对象）。
"""

from __future__ import annotations

import pytest

from knowledge_lattice.adapters.parser_docling import (
    UnsupportedFormatError,
    decode_txt_bytes,
    parse_document,
)

ORG = "org:tax"
GBK_TEXT = (
    "消费税征收范围注释：烟、酒、高档化妆品、贵重首饰及珠宝玉石、鞭炮焰火、"
    "成品油、小汽车、摩托车、高尔夫球及球具、高档手表、游艇等十五个税目。"
    "凡在中华人民共和国境内生产、委托加工和进口上述消费品的单位和个人，"
    "均为消费税的纳税人。"
)


def test_ing_04a_gbk_txt_decoded_and_ingested(qual_env) -> None:
    """① GBK TXT：探测 → 转 UTF-8（解码）→ 正常摄取（可检索）。"""
    env = qual_env
    db = env["db"]
    doc_id, task_id = env["service"].create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="消费税征收范围注释",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=GBK_TEXT.encode("gbk"), mime_type="text/plain",
        filename="consumption_scope.txt",
    )
    env["service"].run_task(task_id)

    doc = db.execute(
        "SELECT active_status FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    assert doc[0] == "searchable_full"
    content = db.execute(
        "SELECT content FROM chunks WHERE doc_id = ? ORDER BY seq LIMIT 1", (doc_id,)
    ).fetchone()[0]
    assert content.strip() == GBK_TEXT, "GBK 字节应被探测解码为原文本入库"


def test_ing_04b_legacy_formats_rejected_before_object_write(qual_env) -> None:
    """② .doc/.xls/.ppt 拒收：UploadValidationError（400）+ 转存提示；
    无对象孤儿（拒收先于落盘）。"""
    from knowledge_lattice.core.docs.ingest import UploadValidationError

    env = qual_env
    for suffix in (".doc", ".xls", ".ppt"):
        with pytest.raises(UploadValidationError, match="转存为新格式"):
            env["service"].create_document(
                org_id=ORG, dataset_id="ds:vat_lib", title="老格式文档",
                dims={"region": ["CN"]}, owner_user_id="u_full",
                file_bytes=b"\xd0xcf\x11\xe0 legacy bytes", mime_type="application/msword",
                filename=f"legacy{suffix}",
            )
    # 无孤儿对象、无文档行（拒收在校验链——先于对象落盘）
    objects = list(env["objects_dir"].glob("*")) if env["objects_dir"].exists() else []
    assert objects == [], f"拒收不得落盘对象（got {objects}）"
    assert db_count(env["db"], "documents") == 5  # matrix 既有 5 篇


def db_count(db, table: str) -> int:
    return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_ing_04c_decode_candidates_and_parser_reject(tmp_path) -> None:
    """纯函数面：解码候选择优（utf-8 干净直取 / GBK 回退）；parser 层老格式
    纵深拒收（UnsupportedFormatError）。"""
    text, enc = decode_txt_bytes("普通中文文本".encode("utf-8"))
    assert text == "普通中文文本" and enc == "utf-8-sig"
    text, enc = decode_txt_bytes(GBK_TEXT.encode("gbk"))
    assert text == GBK_TEXT and enc == "gb18030"

    legacy = tmp_path / "x.doc"
    legacy.write_bytes(b"legacy")
    with pytest.raises(UnsupportedFormatError, match="转存"):
        parse_document(legacy)

    txt = tmp_path / "plain.txt"
    txt.write_bytes("第一段。\n\n第二段。".encode("utf-8"))
    doc = parse_document(txt)
    assert [b.content for b in doc.blocks] == ["第一段。", "第二段。"]
    assert doc.parser.startswith("txt:")
