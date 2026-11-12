"""
Corte diario del plan de trabajo.

La presentación de seguimiento es siempre una foto a cierto corte. Quien la arma
necesita poder volver a sacar la de la semana pasada, y para eso el plan tiene
que acordarse de cómo estaba ese día.

Quién guarda qué
----------------
El registro de movimientos (`timia_plan_pct_historial`) es la fuente de verdad:
cada cambio de % queda con su valor anterior, su autor y su hora, así que el
estado de cualquier fecha se reconstruye deshaciendo hacia atrás. Eso lo hace el
front y no necesita nada de aquí.

El corte diario que se guarda en `timia_plan_cortes` es otra cosa: un punto fijo
por día, con los % tal cual estaban a esa hora. Sirve para dos cosas que el
historial solo no da — tener un punto en la línea de tiempo aunque ese día nadie
tocara nada, y poder comprobar que la reconstrucción coincide con lo que de
verdad había. Si alguna vez no coinciden, el corte manda: es un dato medido, no
calculado.

Por qué un hilo y no un cron del sistema
----------------------------------------
La API corre en un contenedor que se enciende y se apaga, así que un cron de
fuera tendría que hablar con algo que puede no estar. El hilo vive dentro: si la
API está arriba a las 18:00, el corte sale; si estuvo apagada, al arrancar
comprueba si falta el de hoy y lo toma. Lo que no hace es inventar los días que
el contenedor estuvo apagado entero: para ésos está el historial, que sí los
tiene porque nadie pudo cambiar nada con la API caída.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db

CORTES_KEY = "timia_plan_cortes"
PCTS_KEY = "timia_plan_pcts"
CONFIGS_KEY = "timia_plan_configs"

# Bogotá no tiene horario de verano, así que un desfase fijo basta y evita
# depender de la base de zonas horarias del contenedor.
BOGOTA = timezone(timedelta(hours=-5))
HORA_CORTE = 18


def hoy_bogota() -> str:
    return datetime.now(BOGOTA).date().isoformat()


def proximo_corte(ahora: datetime) -> datetime:
    """La próxima vez que toca cortar: hoy a las 18:00, o mañana si ya pasó."""
    hoy = ahora.astimezone(BOGOTA)
    objetivo = hoy.replace(hour=HORA_CORTE, minute=0, second=0, microsecond=0)
    if hoy >= objetivo:
        objetivo += timedelta(days=1)
    return objetivo


def planes_de(pcts: dict[str, Any], configs: Any) -> list[str]:
    """
    Los cronogramas que hay que fotografiar.

    Las claves de los % son `planKey-entregableId-actIdx`, y un planKey puede
    llevar guiones, así que separarlas a la brava no funciona. Se toman los
    planKey de las configuraciones, que es donde están declarados.
    """
    if isinstance(configs, dict):
        return sorted(configs.keys())
    return []


def pcts_de_plan(pcts: dict[str, Any], plan_key: str) -> dict[str, Any]:
    prefijo = f"{plan_key}-"
    return {k: v for k, v in pcts.items() if k.startswith(prefijo)}


async def tomar_corte(fecha: str | None = None, motivo: str = "diario") -> dict[str, Any]:
    """
    Guarda la foto de hoy, si no está ya.

    Es idempotente a propósito: que la API se reinicie tres veces en una tarde
    no debe dejar tres cortes del mismo día compitiendo por ser el bueno.
    """
    fecha = fecha or hoy_bogota()
    previos = await db.read_key(CORTES_KEY) or []
    if not isinstance(previos, list):
        previos = []
    if any(isinstance(c, dict) and c.get("fecha") == fecha for c in previos):
        return {"tomado": False, "razon": "ya existe el corte de ese día", "fecha": fecha}

    pcts = await db.read_key(PCTS_KEY) or {}
    if not isinstance(pcts, dict):
        pcts = {}
    configs = await db.read_key(CONFIGS_KEY) or {}
    claves = planes_de(pcts, configs)

    corte = {
        "id": f"corte-{fecha}",
        "fecha": fecha,
        "tomadoEn": datetime.now(timezone.utc).isoformat(),
        "motivo": motivo,
        "planes": [{"planKey": k, "pcts": pcts_de_plan(pcts, k)} for k in claves],
        # Los % que no caen bajo ningún cronograma declarado se guardan aparte en
        # vez de perderse: si aparecen, es que falta una configuración.
        "sueltos": {k: v for k, v in pcts.items() if not any(k.startswith(f"{c}-") for c in claves)},
    }
    await db.write_key(CORTES_KEY, [*previos, corte], by="corte-diario")
    return {"tomado": True, "fecha": fecha, "planes": len(corte["planes"])}


async def bucle_diario(stop: asyncio.Event) -> None:
    """Toma el corte que falte al arrancar y luego uno cada día a las 18:00."""
    try:
        await tomar_corte(motivo="arranque")
    except Exception as e:                                  # noqa: BLE001
        print(f"[cortes] no se pudo tomar el corte de arranque: {e}")
    while not stop.is_set():
        ahora = datetime.now(BOGOTA)
        espera = (proximo_corte(ahora) - ahora).total_seconds()
        try:
            await asyncio.wait_for(stop.wait(), timeout=espera)
            return                                          # apagando
        except asyncio.TimeoutError:
            pass
        try:
            res = await tomar_corte()
            if res["tomado"]:
                print(f"[cortes] corte diario de {res['fecha']}: {res['planes']} cronograma(s)")
        except Exception as e:                              # noqa: BLE001
            print(f"[cortes] error en el corte diario: {e}")
