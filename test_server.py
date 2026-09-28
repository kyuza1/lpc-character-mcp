"""Testes do MCP. Rode com: python -m pytest -q
Na primeira vez baixam as definições e alguns PNGs do GitHub (precisa de internet)."""
import asyncio

import pytest
from PIL import Image

import server as s

ELFA = [
    {"id": "body/body", "color": "light"},
    {"id": "head/heads/human/heads_human_female", "color": "light"},
    {"id": "head/ears/head_ears_elven", "color": "light"},
    {"id": "hair/long/hair_long_straight", "color": "platinum"},
    {"id": "torso/shirts/torso_clothes_tunic", "color": "forest"},
    {"id": "legs/pants/legs_cuffed", "color": "brown"},
    {"id": "feet/boots/feet_boots_basic", "color": "brown"},
    {"id": "weapons/ranged/bow/weapon_ranged_bow_normal"},
]


@pytest.fixture(autouse=True)
def output_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "OUT", tmp_path)


def test_catalogo_carregado():
    assert len(s.ITEMS) > 300
    assert "body/body" in s.ITEMS
    cats = s.list_categories()
    assert any(c.startswith("hair") for c in cats)


def test_busca_por_nome_e_categoria():
    ids = [x["id"] for x in s.search_items("elven")]
    assert "head/ears/head_ears_elven" in ids
    assert all(x["id"].startswith("hair") for x in s.search_items(category="hair", limit=20))
    assert len(s.search_items(limit=5)) == 5


def test_get_item_cores_e_variantes():
    hair = s.get_item("hair/short/hair_plain")
    assert "blonde" in hair["colors"] and hair["default_color"] == "orange"
    tunic = s.get_item("torso/shirts/torso_clothes_tunic")
    assert "forest" in tunic["variants"] and tunic["body_types"] == ["female"]


def test_recolor_troca_cor_do_cabelo():
    item = [{"id": "hair/short/hair_plain"}]
    base = Image.open(s.generate_character(item, animations=["walk"], filename="a.png")["file"])
    loiro = Image.open(s.generate_character([{**item[0], "color": "blonde"}],
                                            animations=["walk"], filename="b.png")["file"])
    assert base.size == loiro.size
    assert base.tobytes() != loiro.tobytes()


def test_color_escolhe_variante():
    d = s.ITEMS["torso/shirts/torso_clothes_tunic"]
    layer = d["layer_1"]
    verde = s._layer_image(d, layer, "female", "walk", None, ["forest"])
    vermelha = s._layer_image(d, layer, "female", "walk", None, ["red"])
    assert verde.tobytes() != vermelha.tobytes()


def test_gera_elfa_completa():
    r = s.generate_character(ELFA, body_type="female",
                             animations=["walk", "idle", "shoot"], filename="elfa.png",
                             layout="compact")
    img = Image.open(r["file"])
    assert img.size == tuple(r["size"])
    assert {"walk", "idle", "shoot"} <= set(r["animations"])
    # o arco anda numa animação especial de 128px
    assert r["animations"]["walk_128"]["frame"] == 128
    assert img.height == sum(a["height"] for a in r["animations"].values())
    # sem arte no repositório: túnica e arco em "idle" — deve ser avisado
    assert r["missing"] == {"torso/shirts/torso_clothes_tunic": ["idle"],
                            "weapons/ranged/bow/weapon_ranged_bow_normal": ["idle"]}


def test_masculino_avisa_item_so_feminino():
    r = s.generate_character([{"id": "body/body"}, {"id": "torso/shirts/torso_clothes_tunic"}],
                             animations=["walk"], filename="m.png")
    assert "torso/shirts/torso_clothes_tunic" in r["missing"]


def test_item_desconhecido():
    assert "error" in s.generate_character([{"id": "nao/existe"}])


def test_ferramentas_registradas_no_mcp():
    tools = asyncio.run(s.mcp.list_tools())
    nomes = {t.name for t in tools}
    assert {"list_categories", "search_items", "get_item", "generate_character"} <= nomes


FERREIRO = [
    {"id": "body/body", "color": "bronze"},
    {"id": "head/heads/human/heads_human_male"},
    {"id": "torso/aprons/torso_aprons_apron", "color": "leather"},
    {"id": "tools/tool_hammer"},
]


def test_martelo_gera_animacao_especial():
    r = s.generate_character(FERREIRO, animations=["slash"], filename="f.png")
    anim = r["animations"]["tool_hammer"]
    assert anim["frame"] == 128 and anim["height"] == 4 * 128
    assert "tools/tool_hammer" not in r.get("missing", {})


def test_espada_aparece_no_golpe():
    r = s.generate_character([{"id": "body/body"}, {"id": "weapons/sword/weapon_sword_arming"}],
                             animations=["slash"], filename="e.png")
    assert "slash_128" in r["animations"]
    img = Image.open(r["file"])
    a = r["animations"]["slash_128"]
    area = img.crop((0, a["y"], img.width, a["y"] + a["height"]))
    assert area.getbbox() is not None


def test_cabeca_herda_cor_do_corpo():
    sem = s.generate_character(FERREIRO[:2], animations=["walk"], filename="h1.png")
    com = s.generate_character([FERREIRO[0], {**FERREIRO[1], "color": "bronze"}],
                               animations=["walk"], filename="h2.png")
    assert Image.open(sem["file"]).tobytes() == Image.open(com["file"]).tobytes()


def test_item_com_varias_cores():
    info = s.get_item("tools/tool_hammer")
    assert len(info["color_parts"]) == 2
    padrao = s.generate_character([{"id": "tools/tool_hammer"}], animations=["walk"], filename="c1.png")
    cabo = s.generate_character([{"id": "tools/tool_hammer", "color": [None, "red"]}],
                                animations=["walk"], filename="c2.png")
    assert Image.open(padrao["file"]).tobytes() != Image.open(cabo["file"]).tobytes()


def test_animacoes_especiais_lidas_do_repositorio():
    anims = s._custom_animations()
    assert anims["tool_hammer"]["single"] and anims["tool_hammer"]["frameSize"] == 128
    assert len(anims["slash_128"]["frames"]) == 4
    assert anims["slash_128"]["frames"][0][0] == "slash-n,0"


def test_layout_padrao_igual_ao_site():
    r = s.generate_character(FERREIRO, animations=["walk", "slash"], filename="p.png")
    assert r["layout"] == "standard"
    a = r["animations"]
    assert a["walk"]["y"] == 8 * 64 and a["slash"]["y"] == 12 * 64
    assert a["tool_hammer"]["y"] == s.SHEET_HEIGHT
    assert r["size"] == [9 * 128, s.SHEET_HEIGHT + 4 * 128]


def test_layout_padrao_sem_especiais_tem_tamanho_do_site():
    r = s.generate_character(FERREIRO[:2], filename="p2.png")
    assert r["size"] == [s.SHEET_WIDTH, s.SHEET_HEIGHT]


def test_layout_invalido():
    assert "error" in s.generate_character(FERREIRO, layout="xyz")


def test_split_salva_animacoes_separadas(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk", "slash"], filename="sp.png", split=True)
    nomes = {p.name for p in (tmp_path / "sp_anims").iterdir()}
    assert nomes == {"walk.png", "slash.png", "tool_hammer.png"}
    assert Image.open(tmp_path / "sp_anims" / "tool_hammer.png").size == (9 * 128, 4 * 128)


def test_creditos_so_das_artes_usadas(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk"], filename="cr.png")
    c = r["credits"]
    txt = (tmp_path / "cr_credits.txt").read_text(encoding="utf8")
    assert "body/bodies/male" in txt and "tools/hammer" in txt
    assert "Stephen Challener (Redshrike)" in c["authors"]
    assert "CC-BY-SA 3.0" in c["licenses"]
    assert (tmp_path / "cr_credits.csv").read_text(encoding="utf8").startswith("file,notes,authors")
    # item não usado não entra
    assert "hair/" not in txt


URL = ("https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/"
       "#sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light")


def test_le_link_do_site():
    r = s.from_site_url(URL)
    assert r["body_type"] == "male"
    assert r["items"] == [{"id": "body/body", "color": "light"},
                          {"id": "head/heads/human/heads_human_male", "color": "light"},
                          {"id": "head/faces/face_neutral", "color": "light"}]
    assert "unresolved" not in r


def test_link_ida_e_volta_com_variante_e_varias_cores():
    items = [{"id": "body/body", "color": "bronze"},
             {"id": "hair/short/hair_plain", "color": "dark_brown"},
             {"id": "torso/aprons/torso_aprons_apron", "variant": "leather"},
             {"id": "tools/tool_hammer", "color": ["gold", "walnut"]}]
    url = s.to_site_url(items, "female")
    assert "apron=Apron_leather" in url and "handle=Handle_walnut" in url
    r = s.from_site_url(url)
    assert r["body_type"] == "female" and r["items"] == items


def test_link_com_parametro_desconhecido():
    r = s.from_site_url(URL + "&foo=Bar_baz")
    assert r["unresolved"] == {"foo": "Bar_baz"}


def test_personagem_aleatorio_repetivel():
    a = s.random_character("female", seed=42)
    b = s.random_character("female", seed=42)
    assert a == b
    ids = [i["id"] for i in a["items"]]
    assert ids[0] == "body/body" and any(i.startswith("head/heads/human/") for i in ids)
    assert any(i.startswith("torso/") for i in ids) and any(i.startswith("legs/") for i in ids)
    assert all(s._supports(i, "female") for i in ids[1:])
    assert a["url"].startswith(s.SITE)


def test_aleatorio_com_item_fixo():
    r = s.random_character("male", seed=1, fixed_items=[{"id": "tools/tool_hammer"}])
    assert r["items"][-1] == {"id": "tools/tool_hammer"}


def test_gera_lote(tmp_path):
    r = s.generate_batch(3, seed=5, prefix="vila", animations=["walk"], layout="compact")
    assert r["count"] == 3
    for n, c in enumerate(r["characters"], 1):
        assert "error" not in c
        assert (tmp_path / f"vila_{n:02d}.png").exists()
        assert (tmp_path / f"vila_{n:02d}_credits.txt").exists()


def test_previa_devolve_imagem_pelo_mcp():
    res = asyncio.run(s.mcp.call_tool("preview_character", {"items": FERREIRO}))
    tipos = [c.type for c in res.content]
    assert "image" in tipos and "text" in tipos


def test_previa_de_animacao_especial():
    img_data = s.preview_character(FERREIRO, animation="tool_hammer")[0].data
    import io
    img = Image.open(io.BytesIO(img_data))
    assert img.size == (4 * 128 * 2, 128 * 2)


def test_previa_animacao_invalida():
    assert "desconhecida" in s.preview_character(FERREIRO, animation="xyz")


def test_animacoes_reais_de_cada_item():
    tunic = s.get_item("torso/shirts/torso_clothes_tunic")["animations"]
    assert "walk" in tunic["female"] and "idle" not in tunic["female"]
    assert "idle" in s.get_item("body/body")["animations"]["male"]


def test_busca_com_filtros():
    r = s.search_items("apron", body_type="male", animation="idle")
    ids = [x["id"] for x in r]
    assert "torso/aprons/torso_aprons_apron" not in ids
    assert "torso/aprons/torso_aprons_overalls" in ids
    assert [x["id"] for x in s.search_items("leather armour")] == ["torso/armour/torso_armour_leather"]
    assert all(x["type"] == "hair" for x in s.search_items(type_name="hair", limit=10))
    assert all("female" in s.get_item(x["id"])["body_types"]
               for x in s.search_items(category="torso", body_type="female", limit=10))
