import json

from api.fund_metadata import read_fund_name, write_fund_metadata


def test_metadata_is_read_without_a_network_request(tmp_path):
    fund_dir = tmp_path / "110022"
    fund_dir.mkdir()
    (fund_dir / "metadata.json").write_text(
        json.dumps({"fund_code": "110022", "fund_name": "\u6613\u65b9\u8fbe\u6d88\u8d39\u884c\u4e1a\u80a1\u7968"}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert read_fund_name(fund_dir) == "\u6613\u65b9\u8fbe\u6d88\u8d39\u884c\u4e1a\u80a1\u7968"


def test_metadata_backfill_uses_existing_manifest_then_local_eastmoney_cache(tmp_path):
    manifest_dir = tmp_path / "260108"
    manifest_dir.mkdir()
    (manifest_dir / "_fund_manifest.json").write_text(
        json.dumps({"fund_name": "\u666f\u987a\u957f\u57ce\u65b0\u5174\u6210\u957f\u6df7\u5408A"}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert read_fund_name(manifest_dir) == "\u666f\u987a\u957f\u57ce\u65b0\u5174\u6210\u957f\u6df7\u5408A"

    js_dir = tmp_path / "163406"
    js_dir.mkdir()
    (js_dir / "pingzhongdata_163406.js").write_text(
        'var fS_name = "\u5174\u5168\u5408\u6da6\u6df7\u5408A";', encoding="utf-8"
    )
    assert read_fund_name(js_dir) == "\u5174\u5168\u5408\u6da6\u6df7\u5408A"


def test_metadata_write_is_atomic_and_contains_only_public_identity(tmp_path):
    fund_dir = tmp_path / "110022"
    written = write_fund_metadata(
        fund_dir,
        "110022",
        "\u6613\u65b9\u8fbe\u6d88\u8d39\u884c\u4e1a\u80a1\u7968",
        source="test",
    )
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["fund_code"] == "110022"
    assert payload["fund_name"] == "\u6613\u65b9\u8fbe\u6d88\u8d39\u884c\u4e1a\u80a1\u7968"
    assert payload["source"] == "test"
    assert not list(fund_dir.glob("*.tmp"))
