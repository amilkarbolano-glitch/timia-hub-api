"""
Registro público de TR. Es el único endpoint sin sesión de la API, así que lo
que más se prueba aquí es lo que NO debe dejar pasar.
"""
import base64

from conftest import login

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 40).decode()


def registro(c, correo="santiago.coronado@timia.ai", fecha="2026-11-05", capturas=None):
    return c.post("/api/tr/registro", json={
        "correo": correo, "fecha": fecha,
        "capturas": capturas if capturas is not None else [{"nombre": "tr.png", "contenido": PNG}],
    })


# ─── Quién puede entrar ──────────────────────────────────────────────────────

def test_funciona_sin_sesion(client):
    """Ese es el punto: la gente sube desde el celular sin iniciar sesión."""
    assert client.get("/api/auth/me").status_code == 401
    assert registro(client).status_code == 200


def test_correo_de_fuera_rechazado(client):
    r = registro(client, correo="alguien@gmail.com")
    assert r.status_code == 403 and "equipo" in r.json()["detail"]


def test_correo_timia_que_no_esta_en_el_equipo(client):
    """El dominio no basta: hay que estar en timia_admin_users."""
    r = registro(client, correo="fantasma@timia.ai")
    assert r.status_code == 403


def test_el_correo_no_distingue_mayusculas_ni_espacios(client):
    r = registro(client, correo="  Santiago.Coronado@Timia.AI  ")
    assert r.status_code == 200
    assert r.json()["persona"] == "Santiago Coronado"


def test_persona_confirma_el_nombre(client):
    r = client.get("/api/tr/persona", params={"correo": "santiago.coronado@timia.ai"})
    assert r.status_code == 200 and r.json()["nombre"] == "Santiago Coronado"


def test_persona_no_filtra_datos_del_equipo(client):
    """Es un endpoint abierto: solo confirma un correo que ya se conoce."""
    r = client.get("/api/tr/persona", params={"correo": "santiago.coronado@timia.ai"})
    assert set(r.json().keys()) == {"nombre"}
    assert client.get("/api/tr/persona", params={"correo": "nadie@timia.ai"}).status_code == 404


# ─── Qué se acepta ───────────────────────────────────────────────────────────

def test_sin_capturas_no_entra(client):
    assert registro(client, capturas=[]).status_code == 400


def test_solo_imagenes(client):
    pdf = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4").decode()
    r = registro(client, capturas=[{"nombre": "x.pdf", "contenido": pdf}])
    assert r.status_code == 400 and "imágenes" in r.json()["detail"]


def test_captura_ilegible(client):
    r = registro(client, capturas=[{"nombre": "x.png", "contenido": "data:image/png;base64,###"}])
    assert r.status_code == 400


def test_limite_de_capturas(client):
    muchas = [{"nombre": f"{i}.png", "contenido": PNG} for i in range(11)]
    assert registro(client, capturas=muchas).status_code == 400


def test_imagen_demasiado_grande(client):
    gorda = "data:image/png;base64," + base64.b64encode(b"x" * (7 * 1024 * 1024)).decode()
    r = registro(client, capturas=[{"nombre": "gorda.png", "contenido": gorda}])
    assert r.status_code == 413


def test_fecha_con_formato_raro(client):
    assert registro(client, fecha="05/11/2026").status_code == 422


# ─── Qué queda guardado ──────────────────────────────────────────────────────

def test_sin_apps_script_configurado_lo_dice(client):
    """Mientras no tengamos la URL, se guarda la captura pero se avisa."""
    r = registro(client)
    assert r.status_code == 200
    assert r.json()["resultados"][0]["estado"] == "SIN_CONFIGURAR"


def test_el_registro_queda_en_la_base(client):
    registro(client, fecha="2026-11-05")
    login(client, "u-rodolfo")
    datos = client.get("/api/state/timia_tr_registros").json()
    assert len(datos) == 1
    assert datos[0]["correo"] == "santiago.coronado@timia.ai"
    assert datos[0]["fecha"] == "2026-11-05"
    assert datos[0]["persona"] == "Santiago Coronado"


def test_no_se_guardan_las_imagenes(client):
    """Pesan, y el Apps Script ya deja su copia en Drive."""
    registro(client)
    login(client, "u-rodolfo")
    crudo = str(client.get("/api/state/timia_tr_registros").json())
    assert "base64" not in crudo and PNG[30:60] not in crudo


def test_varios_envios_se_acumulan(client):
    registro(client, fecha="2026-11-04")
    registro(client, fecha="2026-11-05")
    login(client, "u-rodolfo")
    assert len(client.get("/api/state/timia_tr_registros").json()) == 2


def test_un_envio_con_tres_capturas_da_tres_resultados(client):
    tres = [{"nombre": f"tr{i}.png", "contenido": PNG} for i in range(3)]
    r = registro(client, capturas=tres)
    assert len(r.json()["resultados"]) == 3
    assert [x["captura"] for x in r.json()["resultados"]] == ["tr0.png", "tr1.png", "tr2.png"]


# ─── No es una puerta trasera ────────────────────────────────────────────────

def test_el_endpoint_publico_no_deja_escribir_otras_claves(client):
    """Sin sesión solo se puede registrar TR; el resto del estado sigue cerrado."""
    assert client.put("/api/state/timia_admin_users", json={"value": []}).status_code in (401, 403)
    assert client.get("/api/state/timia_plan_configs").status_code == 401


# ─── El día sale de la captura ───────────────────────────────────────────────

def test_sin_fecha_tambien_entra(client):
    """Lo normal: la persona sube la captura y el lector saca el día de ahí."""
    r = client.post("/api/tr/registro", json={
        "correo": "santiago.coronado@timia.ai",
        "capturas": [{"nombre": "tr.png", "contenido": PNG}],
    })
    assert r.status_code == 200
    login(client, "u-rodolfo")
    assert client.get("/api/state/timia_tr_registros").json()[0]["fecha"] is None


def test_la_fecha_sigue_aceptandose_si_la_mandan(client):
    """Cuando el lector no detecta el día, la persona lo escribe a mano."""
    assert registro(client, fecha="2026-11-04").status_code == 200
    login(client, "u-rodolfo")
    assert client.get("/api/state/timia_tr_registros").json()[0]["fecha"] == "2026-11-04"


# ─── Las capturas se leen a la vez, no una detrás de otra ────────────────────

def test_las_capturas_se_leen_en_paralelo(client, monkeypatch):
    """
    El lector tarda medio minuto por captura. Encadenadas, tres ya pasan del
    minuto que aguanta CloudFront y la persona recibe un 504 aunque sus
    capturas se hayan leído bien.
    """
    import asyncio, time
    from app.routers import tr as mod

    async def lento(correo, fecha, captura):
        await asyncio.sleep(0.2)
        return {"estado": "OK", "respuesta": {"captura": captura.nombre}}

    monkeypatch.setattr(mod, "_llamar_apps_script", lento)
    seis = [{"nombre": f"tr{i}.png", "contenido": PNG} for i in range(6)]

    t0 = time.monotonic()
    r = client.post("/api/tr/registro", json={
        "correo": "santiago.coronado@timia.ai", "capturas": seis,
    })
    tardo = time.monotonic() - t0

    assert r.status_code == 200
    assert len(r.json()["resultados"]) == 6
    # Con un tope de 4 a la vez: dos tandas, no seis. En serie serían 1,2 s.
    assert tardo < 0.8, f"tardó {tardo:.2f}s: se están leyendo en serie"


def test_el_tope_de_paralelo_se_respeta(client, monkeypatch):
    """Al otro lado hay un Apps Script escribiendo en una hoja: no se le abren
    veinte peticiones a la vez."""
    import asyncio
    from app.routers import tr as mod

    a_la_vez, pico = 0, 0

    async def cuenta(correo, fecha, captura):
        nonlocal a_la_vez, pico
        a_la_vez += 1
        pico = max(pico, a_la_vez)
        await asyncio.sleep(0.05)
        a_la_vez -= 1
        return {"estado": "OK"}

    monkeypatch.setattr(mod, "_llamar_apps_script", cuenta)
    client.post("/api/tr/registro", json={
        "correo": "santiago.coronado@timia.ai",
        "capturas": [{"nombre": f"t{i}.png", "contenido": PNG} for i in range(10)],
    })
    assert pico <= 4, f"llegaron a {pico} a la vez"


def test_el_envio_agrupa_las_capturas(client):
    """El navegador parte el envío en varias peticiones; el id las junta."""
    for i in range(2):
        assert client.post("/api/tr/registro", json={
            "correo": "santiago.coronado@timia.ai", "envio": "e-123",
            "capturas": [{"nombre": f"tr{i}.png", "contenido": PNG}],
        }).status_code == 200
    login(client, "u-rodolfo")
    filas = client.get("/api/state/timia_tr_registros").json()
    assert [f["envio"] for f in filas] == ["e-123", "e-123"]


# ─── Buscador de personas ────────────────────────────────────────────────────

def test_el_buscador_encuentra_por_nombre(client):
    r = client.get("/api/tr/buscar", params={"q": "santi"})
    assert r.status_code == 200
    personas = r.json()["personas"]
    assert personas and personas[0]["id"]
    assert "Santiago" in personas[0]["nombre"]


def test_el_buscador_tapa_el_correo(client):
    """Es un endpoint abierto: no publica la lista de correos del equipo."""
    personas = client.get("/api/tr/buscar", params={"q": "santi"}).json()["personas"]
    assert personas[0]["correo"].endswith("@timia.ai")
    assert "santiago.coronado@timia.ai" not in personas[0]["correo"]


def test_el_buscador_no_busca_por_correo(client):
    """Buscar por correo sería adivinarlo, que es justo lo que no queremos."""
    assert client.get("/api/tr/buscar", params={"q": "santiago.coronado@"}).json()["personas"] == []


def test_el_buscador_pide_dos_letras(client):
    assert client.get("/api/tr/buscar", params={"q": "s"}).json()["personas"] == []


def test_se_puede_registrar_con_el_id_de_la_persona(client):
    persona = client.get("/api/tr/buscar", params={"q": "santi"}).json()["personas"][0]
    r = client.post("/api/tr/registro", json={
        "persona_id": persona["id"], "fecha": "2026-11-05",
        "capturas": [{"nombre": "tr.png", "contenido": PNG}],
    })
    assert r.status_code == 200 and r.json()["persona"]


def test_un_id_inventado_no_registra_nada(client):
    r = client.post("/api/tr/registro", json={
        "persona_id": "u-fantasma", "capturas": [{"nombre": "tr.png", "contenido": PNG}]})
    assert r.status_code == 403


def test_sin_correo_ni_id_no_registra_nada(client):
    r = client.post("/api/tr/registro", json={"capturas": [{"nombre": "tr.png", "contenido": PNG}]})
    assert r.status_code == 403


# ─── Las claves del TR no quedan al alcance de cualquier sesión ──────────────

def test_el_anexo_no_lo_reescribe_cualquiera(client):
    """Es contra el anexo que se valida todo: quien lo cambie, cuadra lo que quiera."""
    login(client, "u-santiago")   # desarrollador: tiene tr.view, no tr.load_any
    for clave in ("timia_tr_puestos", "timia_tr_trimestres", "timia_tr_alias_personas"):
        r = client.put(f"/api/state/{clave}", json={"value": [{"id": "x", "sda": "SDATOOL-1"}]})
        assert r.status_code == 403, clave


def test_los_registros_del_lector_tampoco(client):
    login(client, "u-santiago")
    cuerpo = {"value": [{"id": "tr-1", "correo": "santiago.coronado@timia.ai"}]}
    assert client.put("/api/state/timia_tr_registros", json=cuerpo).status_code == 403


def test_quien_carga_el_tr_si_puede(client):
    login(client, "u-amilkar")
    cuerpo = {"value": [{"id": "x", "sda": "SDATOOL-1"}]}
    assert client.put("/api/state/timia_tr_puestos", json=cuerpo).status_code == 200
