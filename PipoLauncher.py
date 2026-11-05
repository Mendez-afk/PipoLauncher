import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import re
import os
import sys
import json
import zipfile
import platform
import hashlib
import ctypes
import threading
import time
import traceback
import shutil
import urllib.request
import urllib.error
import urllib.parse
import io
import base64
import shlex
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# RECURSOS (icono / fondo) -> funcionan en VS Code y dentro del .exe
# ---------------------------------------------------------------------------
def ruta_recurso(relativa):
    if getattr(sys, "frozen", False):  # ejecutando como .exe
        bases = [getattr(sys, "_MEIPASS", ""), os.path.dirname(sys.executable)]
    else:                              # ejecutando como .py (no depende del cwd)
        bases = [os.path.dirname(os.path.abspath(__file__))]
    for base in bases:
        ruta = os.path.join(base, relativa)
        if os.path.exists(ruta):
            return ruta
    return os.path.join(bases[0], relativa)

# ---------------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------------
carpeta_minecraft = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), ".minecraft")
carpeta_local = os.getenv("LOCALAPPDATA") or ""
carpeta_versiones = os.path.join(carpeta_minecraft, "versions")
carpeta_libs = os.path.join(carpeta_minecraft, "libraries")
carpeta_assets = os.path.join(carpeta_minecraft, "assets")

carpeta_pipolauncher = os.path.join(carpeta_minecraft, "Pipolauncher")
ruta_config = os.path.join(carpeta_pipolauncher, "config.json")
ruta_args_viejo = os.path.join(carpeta_pipolauncher, "args.txt")   # solo para migrar datos
ruta_args = os.path.join(carpeta_pipolauncher, "launch_args.txt")  # solo si el comando es larguísimo
carpeta_logs = os.path.join(carpeta_pipolauncher, "logs")
ruta_latest = os.path.join(carpeta_logs, "latest.log")
ruta_manifiesto = os.path.join(carpeta_pipolauncher, "version_manifest.json")  # copia local para uso sin internet
ruta_profiles = os.path.join(carpeta_minecraft, "launcher_profiles.json")      # lo exigen Forge, Fabric, NeoForge...
carpeta_java_local = os.path.join(carpeta_pipolauncher, "java")                # Java para la PC (instaladores de mods)
carpeta_perfiles = os.path.join(carpeta_pipolauncher, "profiles")              # un perfil (carpeta de juego) por versión

# Memoria que se deja libre para Windows: lo mayor entre RESERVA_MIN_GB y RESERVA_PORC del total.
# Ej: 8 GB -> máx 6 | 16 GB -> máx 12 | 32 GB -> máx 24 | 4 GB -> máx 2
RESERVA_MIN_GB = 2
RESERVA_PORC = 0.25

# Enlace que se abre (en el navegador por defecto) al tocar el logo y el título de la ventana principal
URL_CANAL = "https://www.youtube.com/@UncleJuan67"
# Repositorio de GitHub con la INFORMACIÓN del launcher (botón ⓘ de la ventana principal)
URL_INFO = "https://github.com/Mendez-afk/PipoLauncher"

# Servidores de Mojang y ajustes del instalador
URL_MANIFIESTO = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
URL_JAVA = "https://launchermeta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
URL_ASSETS = "https://resources.download.minecraft.net/"
URL_ADOPTIUM = "https://api.adoptium.net/v3"   # Eclipse Temurin: Java para instalar en la PC si no hay ninguno

# Actualizaciones del propio launcher (GitHub Releases).
# IMPORTANTE: subí VERSION en cada release, antes de compilar el .exe, y que coincida con el tag de la release
# (ej. VERSION = "1.1.0"  ->  tag "v1.1.0"). Si no coinciden, el launcher se ofrecería actualizar a sí mismo en bucle.
VERSION = "0.1.1.5"
GITHUB_REPO = "Mendez-afk/PipoLauncher"
ASSET_EXE = "PipoLauncher.exe"   # nombre del .exe que se sube como archivo de la release
# Se lee la LISTA de releases (no /releases/latest, que ignora las pre-releases) y se toma la de versión más alta
URL_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
URL_RELEASES_WEB = f"https://github.com/{GITHUB_REPO}/releases/latest"
PLATAFORMA_JAVA = "windows-x64"   # carpeta que usa Mojang para los runtimes de Java en Windows 64 bits
HILOS_DESCARGA = 16               # descargas simultáneas
# Java que usa cada runtime oficial (para mostrar un nombre claro en la pantalla de carga)
JAVA_MAYOR = {"jre-legacy": 8, "java-runtime-alpha": 16, "java-runtime-beta": 17,
              "java-runtime-gamma": 17, "java-runtime-gamma-snapshot": 17,
              "java-runtime-delta": 21, "java-runtime-epsilon": 25}
# Java que se instala en la preparación inicial. Poné () para que se baje únicamente cuando
# una versión lo necesite (la descarga por versión siempre se encarga de su propio Java).
JAVA_PRECARGADOS = tuple(JAVA_MAYOR)

# Lista de versiones: solo las releases normales del manifiesto de Mojang (sin snapshots, betas ni alphas).
# Las que no están instaladas se muestran con este prefijo.
PREFIJO_NO_INSTALADA = "[+] "
TIPOS_VANILLA = ("release",)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN (usuario, RAM, última versión elegida, logs)
# ---------------------------------------------------------------------------
def cargar_config():
    cfg = {"usuario": "Invitado", "ram": 4, "version": "", "logs": True, "instalado": False, "java_local": False,
           "perfiles": True, "perfil": "", "perfiles_migrado": False}
    if os.path.exists(ruta_config):
        try:
            with open(ruta_config, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    elif os.path.exists(ruta_args_viejo):  # migración desde el args.txt anterior
        try:
            with open(ruta_args_viejo, "r", encoding="utf-8") as f:
                txt = f.read()
            for clave, patron in (("usuario", r"--username (\S+)"),
                                  ("ram", r"-Xmx(\d+)G")):
                m = re.search(patron, txt)
                if m:
                    cfg[clave] = m.group(1)
        except Exception:
            pass
    cfg.pop("uuid", None)  # el UUID ya no se guarda: se calcula del nick en cada lanzamiento
    try:
        cfg["ram"] = int(cfg["ram"])
    except (TypeError, ValueError):
        cfg["ram"] = 4
    cfg["logs"] = bool(cfg.get("logs", True))
    cfg["instalado"] = bool(cfg.get("instalado", False))
    cfg["java_local"] = bool(cfg.get("java_local", False))
    cfg["perfiles"] = bool(cfg.get("perfiles", True))
    cfg["perfil"] = str(cfg.get("perfil") or "")
    cfg["perfiles_migrado"] = bool(cfg.get("perfiles_migrado", False))
    return cfg

def guardar_config(cfg):
    os.makedirs(carpeta_pipolauncher, exist_ok=True)
    with open(ruta_config, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# ---------------------------------------------------------------------------
# CUENTA MICROSOFT (Minecraft Java "premium")
# Inicio de sesión por código de dispositivo: el launcher muestra un código, el jugador lo escribe en
# microsoft.com/link y Microsoft entrega un token. Con él se encadena: Xbox Live -> XSTS -> Minecraft.
# No hay contraseñas ni secretos en el launcher (app pública). Solo se guarda el token de renovación, cifrado con
# la cuenta de Windows (DPAPI); el token de Minecraft (24 h) se pide de nuevo en cada lanzamiento. Nunca se imprime.
# ---------------------------------------------------------------------------
MS_CLIENT_ID = "2317a231-d53a-4864-bd89-7ffd916447f8"
MS_BASE = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
MS_SCOPE = "XboxLive.signin offline_access"
ruta_cuentas = os.path.join(carpeta_pipolauncher, "accounts.json")
_UA = {"User-Agent": f"PipoLauncher/{VERSION}", "Accept": "application/json"}
_XSTS_ERRORES = {
    2148916233: "Esa cuenta Microsoft no tiene perfil de Xbox (crealo en xbox.com e intentá de nuevo).",
    2148916235: "Xbox Live no está disponible en el país de esa cuenta.",
    2148916236: "La cuenta necesita verificación de adulto en Xbox.",
    2148916237: "La cuenta necesita verificación de adulto en Xbox.",
    2148916238: "Es una cuenta de menor: debe agregarse a una familia de Microsoft.",
}

class ErrorMicrosoft(Exception):
    """Error del inicio de sesión con un mensaje listo para mostrar. 'renovar' = hay que volver a iniciar sesión."""
    def __init__(self, mensaje, renovar=False):
        super().__init__(mensaje)
        self.renovar = renovar

def _http_json(url, datos=None, como_json=False, token=None, timeout=30):
    """(estado HTTP, dict). No lanza por errores HTTP; los de red se convierten en ErrorMicrosoft."""
    cab = dict(_UA)
    cuerpo = None
    if datos is not None:
        if como_json:
            cuerpo, cab["Content-Type"] = json.dumps(datos).encode(), "application/json"
        else:
            cuerpo = urllib.parse.urlencode(datos).encode()
            cab["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        cab["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, cuerpo, cab)
    ultimo = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}
        except (OSError, ValueError) as e:
            ultimo = e
            if i < 2:
                time.sleep(2)
    host = urllib.parse.urlsplit(url).hostname
    raise ErrorMicrosoft(f"No hay conexión con {host} ({getattr(ultimo, 'reason', ultimo)}). Revisá tu internet.")

def ms_pedir_codigo():
    est, d = _http_json(MS_BASE + "/devicecode", {"client_id": MS_CLIENT_ID, "scope": MS_SCOPE})
    if est != 200 or "user_code" not in d:
        raise ErrorMicrosoft(f"Microsoft rechazó la solicitud: {d.get('error_description') or d.get('error') or est}")
    return d

def ms_esperar_token(d, cancelado):
    """Espera a que el jugador ingrese el código. 'cancelado' es un threading.Event. Devuelve la respuesta de tokens."""
    limite = time.time() + int(d.get("expires_in", 900))
    espera = max(2, int(d.get("interval", 5)))
    while time.time() < limite:
        if cancelado.wait(espera):
            raise ErrorMicrosoft("Inicio de sesión cancelado.")
        est, t = _http_json(MS_BASE + "/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                                 "client_id": MS_CLIENT_ID, "device_code": d["device_code"]})
        if est == 200 and "access_token" in t:
            return t
        err = t.get("error")
        if err == "slow_down":
            espera += 5
        elif err != "authorization_pending":
            raise ErrorMicrosoft("No se pudo iniciar sesión: " + str(t.get("error_description") or err))
    raise ErrorMicrosoft("Se acabó el tiempo sin que se ingresara el código. Probá de nuevo.")

def ms_renovar(refresh):
    est, t = _http_json(MS_BASE + "/token", {"grant_type": "refresh_token", "client_id": MS_CLIENT_ID,
                                             "refresh_token": refresh, "scope": MS_SCOPE})
    if est != 200 or "access_token" not in t:
        raise ErrorMicrosoft("La sesión de Microsoft venció. Iniciá sesión de nuevo.", renovar=True)
    return t

def ms_cadena_minecraft(token_ms):
    """Token de Microsoft -> Xbox Live -> XSTS -> Minecraft. Devuelve {'token', 'expira', 'uuid', 'nombre', 'skin'}."""
    est, x = _http_json("https://user.auth.xboxlive.com/user/authenticate", {
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + token_ms},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}, como_json=True)
    if est != 200 or "Token" not in x:
        raise ErrorMicrosoft(f"Falló la autenticación con Xbox Live (HTTP {est}).")
    est, xs = _http_json("https://xsts.auth.xboxlive.com/xsts/authorize", {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [x["Token"]]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}, como_json=True)
    if est != 200 or "Token" not in xs:
        raise ErrorMicrosoft(_XSTS_ERRORES.get(xs.get("XErr"), f"Xbox rechazó la cuenta (HTTP {est}, XErr {xs.get('XErr')})."))
    uhs = xs["DisplayClaims"]["xui"][0]["uhs"]
    est, m = _http_json("https://api.minecraftservices.com/authentication/login_with_xbox",
                        {"identityToken": f"XBL3.0 x={uhs};{xs['Token']}"}, como_json=True)
    if est == 403:
        raise ErrorMicrosoft("Minecraft rechazó la aplicación del launcher (HTTP 403).")
    if est != 200 or "access_token" not in m:
        raise ErrorMicrosoft(f"Minecraft rechazó el inicio de sesión (HTTP {est}).")
    est, pf = _http_json("https://api.minecraftservices.com/minecraft/profile", token=m["access_token"])
    if est == 404:
        raise ErrorMicrosoft("Esta cuenta Microsoft no tiene Minecraft Java Edition, así que Mojang no le entrega nombre, UUID ni token para jugar. Podés seguir jugando sin cuenta (modo offline).")
    if est != 200 or "id" not in pf:
        raise ErrorMicrosoft(f"No se pudo leer el perfil de Minecraft (HTTP {est}).")
    uid = pf["id"]
    uid = f"{uid[0:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}" if "-" not in uid else uid
    skin = next((k.get("url") for k in pf.get("skins", []) if k.get("state") == "ACTIVE"), None)
    gamertag, foto = xbox_perfil(x["Token"])
    return {"token": m["access_token"], "expira": time.time() + int(m.get("expires_in", 86400)),
            "uuid": uid, "nombre": pf.get("name") or "Jugador", "skin": skin, "gamertag": gamertag, "foto": foto}

def xbox_perfil(token_xbl):
    """(gamertag, URL de la foto) de Xbox Live. Es solo cosmético: si algo falla devuelve (None, None) y se usa el
    nombre y la skin de Minecraft."""
    try:
        est, xs = _http_json("https://xsts.auth.xboxlive.com/xsts/authorize", {
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [token_xbl]},
            "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}, como_json=True)
        if est != 200 or "Token" not in xs:
            return None, None
        uhs = xs["DisplayClaims"]["xui"][0]["uhs"]
        req = urllib.request.Request(
            "https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,GameDisplayPicRaw",
            headers={**_UA, "Authorization": f"XBL3.0 x={uhs};{xs['Token']}", "x-xbl-contract-version": "2"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ajustes = json.loads(r.read() or b"{}")["profileUsers"][0]["settings"]
        val = {a.get("id"): a.get("value") for a in ajustes}
        return (val.get("Gamertag") or None), (val.get("GameDisplayPicRaw") or None)
    except Exception:
        return None, None

# ----- almacenamiento cifrado (DPAPI: solo esta cuenta de Windows puede descifrarlo) -----
def _dpapi(datos, cifrar):
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    f = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
    f.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                  ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    f.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(datos, len(datos))
    entrada = _Blob(len(datos), ctypes.cast(buf, ctypes.c_void_p))
    salida = _Blob()
    if not f(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida)):
        raise OSError("DPAPI falló")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)

def proteger(texto):
    """Cifra un texto para guardarlo en disco (base64). Fuera de Windows (solo pruebas) queda sin cifrar."""
    crudo = texto.encode("utf-8")
    return base64.b64encode(_dpapi(crudo, True) if os.name == "nt" else crudo).decode("ascii")

def desproteger(b64):
    crudo = base64.b64decode(b64)
    return (_dpapi(crudo, False) if os.name == "nt" else crudo).decode("utf-8")

def leer_cuenta():
    """Cuenta guardada (dict con nombre, uuid, skin y 'refresh' descifrado) o None."""
    d = leer_json_dict(ruta_cuentas)
    c = (d or {}).get("cuenta")
    if not isinstance(c, dict) or not c.get("refresh") or not c.get("uuid"):
        return None
    try:
        return {"nombre": c.get("nombre") or "Jugador", "uuid": c["uuid"], "skin": c.get("skin"),
                "gamertag": c.get("gamertag"), "foto": c.get("foto"), "refresh": desproteger(c["refresh"])}
    except Exception:
        return None  # archivo de otra PC/usuario o dañado: toca iniciar sesión de nuevo

def guardar_cuenta(nombre, uuid_, skin, refresh, gamertag=None, foto=None):
    os.makedirs(carpeta_pipolauncher, exist_ok=True)
    guardar_json_atomico(ruta_cuentas, {"schema": 1, "cuenta": {
        "nombre": nombre, "uuid": uuid_, "skin": skin, "gamertag": gamertag, "foto": foto,
        "refresh": proteger(refresh)}})

def borrar_cuenta():
    for ruta in (ruta_cuentas,):
        try:
            os.remove(ruta)
        except OSError:
            pass
    try:
        for f in os.listdir(carpeta_pipolauncher):
            if f.startswith("cara_") and f.endswith(".png"):
                os.remove(os.path.join(carpeta_pipolauncher, f))
    except OSError:
        pass

def completar_sesion(tokens_ms):
    """Tokens de Microsoft -> sesión de Minecraft, y guarda la cuenta (con el refresh token nuevo, que rota)."""
    ses = ms_cadena_minecraft(tokens_ms["access_token"])
    guardar_cuenta(ses["nombre"], ses["uuid"], ses["skin"], tokens_ms.get("refresh_token") or "",
                   ses.get("gamertag"), ses.get("foto"))
    return ses

def sesion_guardada():
    """Sesión de Minecraft vigente para la cuenta guardada (renueva los tokens). ErrorMicrosoft si no se puede."""
    c = leer_cuenta()
    if not c:
        raise ErrorMicrosoft("No hay una cuenta guardada. Iniciá sesión.", renovar=True)
    return completar_sesion(ms_renovar(c["refresh"]))

def datos_cuenta(ses):
    """Lo que la interfaz necesita de una sesión (sin tokens)."""
    return {"nombre": ses["nombre"], "uuid": ses["uuid"], "skin": ses.get("skin"),
            "gamertag": ses.get("gamertag"), "foto": ses.get("foto")}

def nombre_visible(c):
    """Lo que se muestra: el gamertag de Xbox (o, si no se pudo leer, el nombre de Minecraft)."""
    return c.get("gamertag") or c["nombre"]

def ruta_cara(c):
    """Archivo de caché de la foto; cambia si cambia la foto o la skin, así se renueva sola."""
    fuente = c.get("foto") or c.get("skin") or ""
    h = hashlib.md5(fuente.encode("utf-8")).hexdigest()[:8]
    return os.path.join(carpeta_pipolauncher, f"cara_{re.sub('[^0-9a-fA-F]', '', c['uuid'])}_{h}.png")

def _bajar_imagen(url, tope=3_000_000):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return Image.open(io.BytesIO(r.read(tope))).convert("RGBA")

def descargar_cara(c):
    """Foto de la cuenta (64x64): la de Xbox y, si no hay o falla, la cara de la skin de Minecraft.
    Se guarda en caché. Devuelve la ruta o None."""
    destino = ruta_cara(c)
    if os.path.isfile(destino):
        return destino
    img = None
    foto = c.get("foto")
    if foto and foto.startswith("https://") and (urllib.parse.urlsplit(foto).hostname or "").endswith("xboxlive.com"):
        try:
            img = _bajar_imagen(foto + ("&" if "?" in foto else "?") + "format=png&w=128&h=128").resize((64, 64), Image.LANCZOS)
        except Exception:
            img = None
    skin_url = c.get("skin")
    if img is None and skin_url and skin_url.startswith("https://textures.minecraft.net/"):
        try:
            skin = _bajar_imagen(skin_url, 2_000_000)
            img = skin.crop((8, 8, 16, 16))
            if skin.height >= 16:
                img.alpha_composite(skin.crop((40, 8, 48, 16)))
            img = img.resize((64, 64), Image.NEAREST)
        except Exception:
            img = None
    if img is None:
        return None
    try:
        prefijo = os.path.basename(destino).rsplit("_", 1)[0] + "_"
        for f in os.listdir(carpeta_pipolauncher):  # fotos viejas de la misma cuenta
            if f.startswith(prefijo) and f.endswith(".png"):
                os.remove(os.path.join(carpeta_pipolauncher, f))
        img.save(destino)
        return destino
    except OSError:
        return None

def ocultar_secretos(texto, *secretos):
    for sec in secretos:
        if sec and len(sec) > 8:
            texto = texto.replace(sec, "***")
    return texto

# ---------------------------------------------------------------------------
# PERFILES
# Un perfil = nombre + versión de Minecraft + parámetros de lanzamiento + su propia carpeta de juego:
#   .minecraft\Pipolauncher\profiles\<id>\game\          options.txt, servers.dat, mods\, config\, saves\ ...
#   .minecraft\Pipolauncher\profiles\<id>\profile.json   nombre, versión, parámetros y metadatos
# Así los mods, la configuración y los mundos de un perfil no se mezclan con los de otro (aunque usen la misma
# versión). Lo pesado y común sigue compartido en .minecraft: versions, libraries, assets, runtime y natives.
# ---------------------------------------------------------------------------
PERFIL_SCHEMA = 2
# Se copian de .minecraft al crear un perfil: datos personales que sirven en cualquier versión. Los mods y la
# config de mods NO se copian (son de un loader/versión concretos y podrían romper otra) y los mundos se preguntan.
IMPORTAR_AL_CREAR = ("options.txt", "optionsof.txt", "servers.dat", "resourcepacks")
LIMITE_IMPORTAR_MB = 300

def ahora_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def nombre_carpeta_perfil(texto):
    """Un nombre cualquiera como nombre de carpeta válido en Windows."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f\s]+', "_", str(texto)).strip(" ._") or "perfil"

def ruta_perfil(pid):
    return os.path.join(carpeta_perfiles, pid)

def leer_json_dict(ruta):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None

def guardar_json_atomico(ruta, datos):
    """Escribe a un temporal y lo mueve: un corte de luz a mitad no deja el JSON a medias."""
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ruta)

def tam_bytes(ruta, tope=None):
    """Tamaño de un archivo o carpeta; con 'tope' deja de contar al pasarlo (no recorre carpetas enormes)."""
    if os.path.isfile(ruta):
        return os.path.getsize(ruta)
    total = 0
    for base, _dirs, archivos in os.walk(ruta):
        for a in archivos:
            try:
                total += os.path.getsize(os.path.join(base, a))
            except OSError:
                pass
            if tope and total > tope:
                return total
    return total

def copiar_seguro(origen, destino):
    """Copia un archivo o carpeta SIN tocar el original; si falla a medias, no deja restos."""
    try:
        if os.path.isdir(origen):
            shutil.copytree(origen, destino)
        else:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy2(origen, destino)
        return True
    except (OSError, shutil.Error):
        if os.path.isdir(destino):
            shutil.rmtree(destino, ignore_errors=True)
        elif os.path.exists(destino):
            try:
                os.remove(destino)
            except OSError:
                pass
        return False

def importar_datos_existentes(juego):
    """Copia al perfil nuevo las opciones, servidores y resource packs que ya había en .minecraft.
    Devuelve (copiados, omitidos); lo que ya exista en el perfil no se pisa."""
    copiados, omitidos = [], []
    tope = LIMITE_IMPORTAR_MB * 1048576
    for nombre in IMPORTAR_AL_CREAR:
        origen, destino = os.path.join(carpeta_minecraft, nombre), os.path.join(juego, nombre)
        if not os.path.exists(origen) or os.path.exists(destino):
            continue
        if tam_bytes(origen, tope) > tope or not copiar_seguro(origen, destino):
            omitidos.append(nombre)
        else:
            copiados.append(nombre)
    return copiados, omitidos

def mundos_existentes():
    """(ruta, MB) de los mundos guardados en .minecraft\\saves, o None si no hay ninguno."""
    ruta = os.path.join(carpeta_minecraft, "saves")
    try:
        if not os.listdir(ruta):
            return None
    except OSError:
        return None
    return ruta, tam_bytes(ruta) / 1048576

def es_version_legacy(vid):
    """Versiones anteriores a 1.6 (índice de assets 'pre-1.6'): leen sus sonidos de <gameDir>\\resources, que el
    instalador deja en .minecraft. Para ellas no se separa la carpeta de juego."""
    try:
        data = cargar_version(vid)
        return ((data.get("assetIndex") or {}).get("id") or data.get("assets")) == "pre-1.6"
    except Exception:
        return False

def leer_perfil(pid):
    d = leer_json_dict(os.path.join(ruta_perfil(pid), "profile.json"))
    if d is None or not str(d.get("version") or "").strip():
        return None
    d["id"] = pid
    d["nombre"] = str(d.get("nombre") or d["version"]).strip() or d["version"]
    d["args"] = str(d.get("args") or "")
    return d

def listar_perfiles():
    """Perfiles existentes, ordenados por nombre."""
    try:
        carpetas = os.listdir(carpeta_perfiles)
    except OSError:
        return []
    res = [p for p in (leer_perfil(c) for c in carpetas) if p]
    res.sort(key=lambda p: (p["nombre"].lower(), p["id"]))
    return res

def guardar_perfil(datos):
    guardar_json_atomico(os.path.join(ruta_perfil(datos["id"]), "profile.json"), datos)

def crear_perfil(nombre, version, args=""):
    """Crea la carpeta y el profile.json de un perfil nuevo y lo devuelve."""
    nombre = " ".join(str(nombre).split())
    if not nombre or not version:
        raise ValueError("Falta el nombre o la versión.")
    pid = f"{nombre_carpeta_perfil(nombre)[:40]}-{os.urandom(3).hex()}"
    os.makedirs(os.path.join(ruta_perfil(pid), "game"), exist_ok=True)
    datos = {"schema": PERFIL_SCHEMA, "nombre": nombre, "version": version, "args": args.strip(),
             "creado": ahora_iso(), "ultimo_uso": None, "veces_jugado": 0, "importado": [], "omitidos": [],
             "mundos": None, "preparado": False}
    guardar_json_atomico(os.path.join(ruta_perfil(pid), "profile.json"), datos)
    datos["id"] = pid
    return datos

def eliminar_perfil(pid):
    """Borra la carpeta del perfil (con sus mods y mundos). Solo si está dentro de la carpeta de perfiles."""
    raiz = os.path.realpath(ruta_perfil(pid))
    base = os.path.realpath(carpeta_perfiles)
    if not pid or os.path.dirname(raiz) != base:
        raise ValueError("Ruta de perfil no válida.")
    shutil.rmtree(raiz)

def migrar_perfiles_antiguos(cfg):
    """Perfiles del sistema anterior (una carpeta por versión, sin nombre): se conservan tal cual como perfiles
    con el nombre de su versión. Si no hay ninguno y ya se había elegido una versión instalada, se crea uno con ella."""
    try:
        carpetas = os.listdir(carpeta_perfiles)
    except OSError:
        carpetas = []
    for c in carpetas:
        d = leer_json_dict(os.path.join(carpeta_perfiles, c, "profile.json"))
        if d is None or "nombre" in d or not d.get("version"):
            continue
        d.update({"schema": PERFIL_SCHEMA, "nombre": d["version"], "args": "", "preparado": True})
        try:
            guardar_json_atomico(os.path.join(carpeta_perfiles, c, "profile.json"), d)
        except OSError:
            pass
    if not cfg.get("perfiles_migrado"):
        cfg["perfiles_migrado"] = True
        v = cfg.get("version")
        if v and not listar_perfiles() and esta_instalada(v):
            try:
                p = crear_perfil(v, v)
                cfg["perfil"] = p["id"]
            except OSError:
                pass
        guardar_config(cfg)

def asegurar_perfil(pid):
    """Prepara un perfil: (datos, carpeta de juego, es_nuevo). Es idempotente. La primera vez copia a su carpeta las
    opciones/servidores/resource packs que ya había en .minecraft (sin tocar los originales)."""
    datos = leer_perfil(pid)
    if datos is None:
        raise OSError("El perfil no existe o está dañado.")
    juego = os.path.join(ruta_perfil(pid), "game")
    os.makedirs(juego, exist_ok=True)
    nuevo = not datos.get("preparado")
    if nuevo:
        datos["importado"], datos["omitidos"] = importar_datos_existentes(juego)
        datos["preparado"] = True
    for sub in ("mods", "resourcepacks", "saves"):  # carpetas que el jugador va a querer encontrar
        os.makedirs(os.path.join(juego, sub), exist_ok=True)
    if nuevo:
        guardar_perfil(datos)
    return datos, juego, nuevo

def actualizar_perfil(pid, **cambios):
    datos = leer_perfil(pid)
    if datos is not None:
        datos.update(cambios)
        guardar_perfil(datos)

def registrar_uso(pid):
    """Anota que el perfil se acaba de jugar (fecha y contador)."""
    datos = leer_perfil(pid)
    if datos is not None:
        actualizar_perfil(pid, ultimo_uso=ahora_iso(), veces_jugado=int(datos.get("veces_jugado") or 0) + 1)

# ----- parámetros de lanzamiento del perfil -----
_JVM_PREFIJOS = ("-X", "-D", "-javaagent", "-agentlib", "-agentpath", "-verbose", "-ea", "-da", "-esa", "-dsa",
                 "--add-opens", "--add-exports", "--add-modules", "--add-reads", "--enable-native-access",
                 "--illegal-access", "--patch-module", "--limit-modules")
_JVM_CON_VALOR = ("--add-opens", "--add-exports", "--add-modules", "--add-reads", "--patch-module",
                  "--limit-modules", "--enable-native-access")
_PROHIBIDOS = ("-cp", "-classpath", "--class-path", "-jar", "-p", "--module-path", "-m", "--module")
_AUTH_JUEGO = ("--username", "--uuid", "--accesstoken", "--session", "--usertype", "--xuid", "--clientid")

def parsear_args(texto):
    """Separa los parámetros de lanzamiento en (jvm, juego, error). Los de Java (-Xmx, -D..., --add-opens...) van
    antes de la clase principal; el resto (--width, --server...) va al final. Se rechazan los que romperían el
    arranque o la sesión (classpath, --accessToken...)."""
    texto = (texto or "").strip()
    if not texto:
        return [], [], None
    try:
        toks = shlex.split(texto, posix=False)
    except ValueError as e:
        return [], [], f"Comillas sin cerrar ({e})."
    toks = [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in toks]
    jvm, juego, i = [], [], 0
    while i < len(toks):
        t, bajo = toks[i], toks[i].lower()
        if bajo in _PROHIBIDOS:
            return [], [], f"«{t}» no se puede usar: el launcher lo define solo."
        if bajo in _AUTH_JUEGO:
            return [], [], f"«{t}» lo define el launcher según tu cuenta."
        if t.startswith(_JVM_PREFIJOS) and not bajo.startswith("-djava.library.path"):
            jvm.append(t)
            if t in _JVM_CON_VALOR and i + 1 < len(toks):
                i += 1
                jvm.append(toks[i])
        elif bajo.startswith("-djava.library.path"):
            return [], [], "«-Djava.library.path» lo define el launcher."
        elif t.startswith("-") and not t.startswith("--"):
            return [], [], f"«{t}» no parece un parámetro válido (los del juego empiezan con --)."
        else:
            juego.append(t)
        i += 1
    return jvm, juego, None

# ---------------------------------------------------------------------------
# VERSIONES PARA ELEGIR AL CREAR UN PERFIL (con filtros como el launcher original)
# ---------------------------------------------------------------------------
TIPOS_FILTRO = (("release", "Releases"), ("snapshot", "Snapshots"), ("old_beta", "Betas"),
                ("old_alpha", "Alphas"), ("mods", "Mods / Forge / Fabric"))

def versiones_para_perfil(manifiesto, tipos):
    """Ids de versión de la más nueva a la más vieja, solo de los tipos marcados. 'mods' incluye las versiones
    locales que Mojang no conoce (Forge, Fabric, OptiFine...), debajo de su versión base. Sin manifiesto
    (sin internet la primera vez) se ven todas las versiones instaladas."""
    locales = listar_versiones()
    if not manifiesto:
        return list(locales)
    todas = manifiesto.get("versions", [])
    conocidas = {v["id"] for v in todas}
    hijas, sueltas = {}, []
    for nombre in locales:
        if nombre in conocidas:
            continue
        raiz = raiz_de(nombre)
        (hijas.setdefault(raiz, []) if raiz in conocidas else sueltas).append(nombre)
    ids = list(sueltas) if "mods" in tipos else []
    for v in todas:
        if v.get("type") in tipos:
            ids.append(v["id"])
        if "mods" in tipos:
            ids.extend(hijas.get(v["id"], []))
    return ids

def importar_mundos(juego):
    """Copia .minecraft\\saves al perfil (los originales quedan intactos). Devuelve True si salió bien."""
    origen, destino = os.path.join(carpeta_minecraft, "saves"), os.path.join(juego, "saves")
    try:
        os.makedirs(destino, exist_ok=True)
        for nombre in os.listdir(origen):
            if os.path.exists(os.path.join(destino, nombre)):
                continue
            if not copiar_seguro(os.path.join(origen, nombre), os.path.join(destino, nombre)):
                return False
        return True
    except OSError:
        return False

def uuid_offline(nombre):
    """UUID de modo offline: el mismo algoritmo que usan los servidores offline
    (UUID.nameUUIDFromBytes("OfflinePlayer:<nick>")). Depende del nick exacto: otro nick => otro UUID."""
    h = bytearray(hashlib.md5(("OfflinePlayer:" + nombre).encode("utf-8")).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    return h.hex()

def ram_total_gb():
    try:
        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return max(2, round(m.ullTotalPhys / 1024 ** 3))
    except Exception:
        return 16

def ram_maxima_gb(total):
    """RAM máxima que se le permite usar al juego, dejando margen para el sistema operativo."""
    return max(1, total - max(RESERVA_MIN_GB, round(total * RESERVA_PORC)))

# ---------------------------------------------------------------------------
# LOGS: latest.log = sesión actual/última; las anteriores quedan como FECHA-HORA.log
# ---------------------------------------------------------------------------
class Registro:
    def __init__(self):
        os.makedirs(carpeta_logs, exist_ok=True)
        self._rotar()
        self._lock = threading.Lock()
        self._f = open(ruta_latest, "w", encoding="utf-8", errors="replace", buffering=1)

    @staticmethod
    def _rotar():
        if not os.path.isfile(ruta_latest):
            return
        try:
            marca = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(os.path.getmtime(ruta_latest)))
            destino, n = os.path.join(carpeta_logs, marca + ".log"), 1
            while os.path.exists(destino):
                destino = os.path.join(carpeta_logs, f"{marca}_{n}.log")
                n += 1
            os.replace(ruta_latest, destino)
        except OSError:
            pass  # si no se puede renombrar, latest.log simplemente se sobrescribe

    def escribir(self, texto):
        with self._lock:
            try:
                self._f.write(texto)
            except Exception:
                pass

    def info(self, msg, nivel="INFO"):
        self.escribir(f"[{time.strftime('%H:%M:%S')}] [Launcher/{nivel}]: {msg}\n")

    def cerrar(self):
        with self._lock:
            try:
                self._f.close()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# VERSIONES INSTALADAS
# ---------------------------------------------------------------------------
def listar_versiones():
    """Todas las versiones de .minecraft\\versions, de la más nueva a la más vieja.
    Se ordena por la fecha de salida de la versión base (la del .json), así que funciona igual
    con releases, snapshots y versiones nuevas o viejas. Forge/Fabric/etc. quedan justo debajo
    de su versión vanilla. Para orden inverso (vieja -> nueva) cambiá REVERSE a False."""
    REVERSE = True
    if not os.path.isdir(carpeta_versiones):
        return []

    def leer(nombre):
        try:
            with open(os.path.join(carpeta_versiones, nombre, nombre + ".json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    items = []
    for nombre in os.listdir(carpeta_versiones):
        data = leer(nombre)
        if data is None:
            continue
        base = data.get("inheritsFrom")
        data_base = (leer(base) if base else data) or data
        fecha = (data_base.get("releaseTime") or data_base.get("time") or "")[:19]
        nums = tuple(int(n) for n in re.findall(r"\d+", base or nombre)[:4])
        items.append((fecha, nums, (base is None) == REVERSE, nombre))

    items.sort(key=lambda t: t[3].lower())  # desempate estable por nombre
    items.sort(key=lambda t: t[:3], reverse=REVERSE)
    return [t[3] for t in items]

# ---------------------------------------------------------------------------
# CONSTRUCCIÓN DEL COMANDO A PARTIR DEL .json DE LA VERSIÓN
# ---------------------------------------------------------------------------
def cargar_version(vid):
    """Lee el json de la versión y lo fusiona con el de 'inheritsFrom' (Forge, Fabric, OptiFine...)."""
    ruta = os.path.join(carpeta_versiones, vid, vid + ".json")
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    padre = data.get("inheritsFrom")
    if not padre:
        data["_cadena"] = [vid]
        return data
    base = cargar_version(padre)
    res = dict(base)
    for k, v in data.items():
        if k == "libraries":
            res[k] = v + base.get(k, [])
        elif k == "arguments":
            ba = base.get("arguments", {})
            res[k] = {t: ba.get(t, []) + v.get(t, []) for t in ("jvm", "game")}
        else:
            res[k] = v
    res["_cadena"] = [vid] + base["_cadena"]
    return res

def arch_actual():
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x86"

def permitido(reglas):
    if not reglas:
        return True
    ok = False
    for r in reglas:
        coincide = True
        o = r.get("os")
        if o:
            if "name" in o and o["name"] != "windows":
                coincide = False
            if "arch" in o and o["arch"] != arch_actual():
                coincide = False
            if "version" in o and not re.match(o["version"], platform.version()):
                coincide = False
        for feat, valor in (r.get("features") or {}).items():
            if valor:  # no usamos demo, resolución custom, quickplay, etc.
                coincide = False
        if coincide:
            ok = (r.get("action") == "allow")
    return ok

def ruta_lib(lib, clasificador=None):
    dl = lib.get("downloads", {})
    art = dl.get("classifiers", {}).get(clasificador) if clasificador else dl.get("artifact")
    if art and art.get("path"):
        return os.path.join(carpeta_libs, *art["path"].split("/"))
    nombre, ext = lib["name"], "jar"
    if "@" in nombre:
        nombre, ext = nombre.split("@")
    partes = nombre.split(":")
    g, a, v = partes[:3]
    cl = partes[3] if len(partes) > 3 else clasificador
    archivo = f"{a}-{v}" + (f"-{cl}" if cl else "") + f".{ext}"
    return os.path.join(carpeta_libs, *g.split("."), a, v, archivo)

def extraer_natives(jar, destino):
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            if n.startswith("META-INF") or n.endswith("/"):
                continue
            if not os.path.exists(os.path.join(destino, n)):
                z.extract(n, destino)

def lista_args(items):
    salida = []
    for it in items:
        if isinstance(it, str):
            salida.append(it)
        elif permitido(it.get("rules")):
            v = it["value"]
            salida += v if isinstance(v, list) else [v]
    return salida

def sustituir(texto, variables):
    return re.sub(r"\$\{(\w+)\}", lambda m: variables.get(m.group(1), m.group(0)), texto)

def limpiar(args):
    """Quita argumentos con variables sin resolver (junto con su flag)."""
    salida = []
    for a in args:
        if "${" in a:
            if salida and salida[-1].startswith("--"):
                salida.pop()
            continue
        salida.append(a)
    return salida

def java_requerido(data):
    """(carpeta del runtime, versión mayor de Java) que pide la versión. Sin dato => Java 8 (jre-legacy)."""
    jv = data.get("javaVersion") or {}
    return jv.get("component", "jre-legacy"), jv.get("majorVersion", 8)

def rutas_java(comp):
    """Dónde puede estar el runtime: [launcher oficial de Microsoft Store, carpeta .minecraft\\runtime]."""
    return [
        os.path.join(carpeta_local, "Packages", "Microsoft.4297127D64EC6_8wekyb3d8bbwe", "LocalCache",
                     "Local", "runtime", comp, PLATAFORMA_JAVA, comp, "bin", "javaw.exe"),
        os.path.join(carpeta_minecraft, "runtime", comp, PLATAFORMA_JAVA, comp, "bin", "javaw.exe"),
    ]

class JavaNoEncontrado(RuntimeError):
    def __init__(self, comp, mayor, candidatos):
        super().__init__(
            f"No se encontró el Java '{comp}' que necesita esta versión.\n\n"
            "Descargá la versión de nuevo (o usá ⚙ → Verificar archivos) para que el launcher lo instale.\n\n"
            "Rutas probadas:\n" + "\n".join(candidatos))
        self.mayor = mayor

def buscar_java(data):
    comp, mayor = java_requerido(data)
    candidatos = rutas_java(comp)
    for c in candidatos:
        if os.path.isfile(c):
            return c
    raise JavaNoEncontrado(comp, mayor, candidatos)

def construir_comando(vid, usuario, ram, uuid_jugador, con_logs=False, dir_juego=None, args_extra="", sesion=None):
    """dir_juego: carpeta de juego del perfil (--gameDir). Sin ella se usa .minecraft como antes.
    args_extra: parámetros de lanzamiento del perfil (texto). sesion: {'token'} de una cuenta Microsoft; sin ella
    se juega en modo offline con el nick y UUID dados."""
    data = cargar_version(vid)
    java = buscar_java(data)
    extra_jvm, extra_juego, err_args = parsear_args(args_extra)
    if err_args:
        raise ValueError("Parámetros de lanzamiento del perfil: " + err_args)

    natives_dir = os.path.join(carpeta_minecraft, "bin", "pipolauncher", vid)
    os.makedirs(natives_dir, exist_ok=True)

    cp, vistos, faltan = [], set(), []
    for lib in data.get("libraries", []):
        if not permitido(lib.get("rules")):
            continue
        nat = lib.get("natives")
        if nat:  # formato viejo (<=1.18): natives en jar aparte que hay que extraer
            clasif = nat.get("windows")
            if not clasif:
                continue
            p = ruta_lib(lib, clasif.replace("${arch}", "64"))
            if os.path.isfile(p):
                extraer_natives(p, natives_dir)
            else:
                faltan.append(p)
            continue
        partes = lib["name"].split(":")
        clave = tuple(partes[:2]) + tuple(partes[3:4])
        if clave in vistos:  # si hay duplicados gana el de la versión hija (Forge/Fabric)
            continue
        vistos.add(clave)
        p = ruta_lib(lib)
        (cp if os.path.isfile(p) else faltan).append(p)

    # .jar del juego: el de la propia versión si existe, si no el de la versión base
    candidatos_jar = []
    if data.get("jar"):
        candidatos_jar.append(os.path.join(carpeta_versiones, data["jar"], data["jar"] + ".jar"))
    candidatos_jar += [os.path.join(carpeta_versiones, v, v + ".jar") for v in data["_cadena"]]
    jar = next((p for p in candidatos_jar if os.path.isfile(p)), None)
    # Forge/NeoForge modernos (1.17+) arrancan con BootstrapLauncher y arman el módulo 'minecraft' ellos mismos
    # (libraries\net\minecraft\client\...-srg.jar). Si el .jar vanilla también va en el classpath, Java lo toma como
    # un segundo módulo ("_1._20._1") y falla con ResolutionException: dos módulos exportan net.minecraft.client.main.
    arranque_modular = "bootstraplauncher" in str(data.get("mainClass", "")).lower()
    if jar:
        if not arranque_modular:
            cp.append(jar)
    else:
        faltan.append(candidatos_jar[0])

    sep = ";"
    variables = {
        "auth_player_name": usuario, "version_name": vid, "game_directory": dir_juego or carpeta_minecraft,
        "assets_root": carpeta_assets,
        "assets_index_name": (data.get("assetIndex") or {}).get("id") or data.get("assets", "legacy"),
        "auth_uuid": uuid_jugador, "auth_access_token": "0", "auth_session": "0",
        "clientid": "0", "auth_xuid": "0", "user_type": "legacy", "user_properties": "{}",
        "version_type": data.get("type", "release"), "natives_directory": natives_dir,
        "launcher_name": "PipoLauncher", "launcher_version": VERSION,
        "classpath": sep.join(cp), "classpath_separator": sep, "library_directory": carpeta_libs,
        "game_assets": os.path.join(carpeta_assets, "virtual", (data.get("assetIndex") or {}).get("id") or "legacy"),
    }

    if sesion:  # cuenta Microsoft: datos reales (los de <=1.6 leen auth_session; los nuevos, access_token)
        variables.update({"auth_access_token": sesion["token"], "auth_session": f"token:{sesion['token']}:{uuid_jugador.replace('-', '')}",
                          "user_type": "msa"})

    # JVM
    if data.get("arguments", {}).get("jvm"):
        jvm = lista_args(data["arguments"]["jvm"])
    else:
        jvm = []
    if not any("java.library.path" in a for a in jvm):
        jvm.append("-Djava.library.path=${natives_directory}")
    if not any("${classpath}" in a for a in jvm):
        jvm += ["-cp", "${classpath}"]

    # Juego
    if "arguments" in data and data["arguments"].get("game"):
        juego = lista_args(data["arguments"]["game"])
    else:
        juego = data.get("minecraftArguments", "").split()

    memoria = [f"-Xmx{ram}G", "-Xss1M", "-XX:+UnlockExperimentalVMOptions", "-XX:+UseG1GC",
               "-XX:G1NewSizePercent=20", "-XX:G1ReservePercent=20",
               "-XX:MaxGCPauseMillis=50", "-XX:G1HeapRegionSize=32M"]
    if con_logs:  # que la salida del juego llegue en UTF-8 al log (Java 19+; las anteriores lo ignoran)
        memoria += ["-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8"]

    jvm = limpiar([sustituir(a, variables) for a in jvm])
    juego = limpiar([sustituir(a, variables) for a in juego])
    return [java] + memoria + jvm + extra_jvm + [data["mainClass"]] + juego + extra_juego, faltan

def iniciar(cmd, registro=None, cwd=None):
    """Sin logs: lanza el juego y se olvida de él. Con logs: captura su salida hacia el registro.
    'cwd' es la carpeta de juego del perfil (por defecto .minecraft). Devuelve (proceso, hilo_lector)."""
    cwd = cwd or carpeta_minecraft
    if len(subprocess.list2cmdline(cmd)) > 30000:  # límite de Windows ~32k: usar @argfile
        os.makedirs(carpeta_pipolauncher, exist_ok=True)
        with open(ruta_args, "w", encoding="utf-8") as f:
            f.write("\n".join('"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"' for a in cmd[1:]))
        cmd = [cmd[0], "@" + ruta_args]
        if registro:
            registro.info(f"Comando demasiado largo, se usa @argfile: {ruta_args}")

        def borrar_argfile():  # Java lo lee al arrancar; después no debe quedar un token en disco
            try:
                os.remove(ruta_args)
            except OSError:
                pass
        t = threading.Timer(40, borrar_argfile)
        t.daemon = True
        t.start()
    nt = os.name == "nt"
    if registro is None:
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if nt else 0
        proc = subprocess.Popen(cmd, cwd=cwd, creationflags=flags, close_fds=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc, None
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if nt else 0
    proc = subprocess.Popen(cmd, cwd=cwd, creationflags=flags, close_fds=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8", errors="replace")

    def leer():
        for linea in proc.stdout:
            registro.escribir(linea if linea.endswith("\n") else linea + "\n")
    hilo = threading.Thread(target=leer, daemon=True)
    hilo.start()
    return proc, hilo

# ---------------------------------------------------------------------------
# ACTUALIZACIONES DEL LAUNCHER (GitHub Releases)
# ---------------------------------------------------------------------------
def version_a_tupla(s):
    """'v1.2.10' -> (1, 2, 10, 0). Se compara como números, no como texto ('1.10' > '1.9')."""
    nums = [int(n) for n in re.findall(r"\d+", str(s))[:4]]
    return tuple((nums + [0] * 4)[:4])

def limpiar_notas(md, maximo=700):
    """Notas de la release (Markdown) -> texto simple y corto para mostrar en la ventana."""
    t = re.sub(r"[#*`>]+", "", md or "").replace("\r", "")
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t if len(t) <= maximo else t[:maximo].rstrip() + "…"

def buscar_actualizacion(timeout=6):
    """Revisa el repositorio: entre TODAS las releases publicadas (pre-releases incluidas, borradores no) toma la
    de versión más alta y devuelve un dict si es MÁS NUEVA que VERSION, si no None.
    Cualquier fallo (sin internet, límite de la API, JSON raro) se ignora: el launcher abre igual."""
    # el parámetro t evita que GitHub/proxies sirvan una copia guardada de hace un rato
    req = urllib.request.Request(f"{URL_RELEASES_API}&t={int(time.time())}", headers={
        "User-Agent": f"PipoLauncher/{VERSION}", "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            lista = json.loads(r.read().decode("utf-8"))
        if not isinstance(lista, list):
            return None
        mejor = None
        for r_ in lista:
            if not isinstance(r_, dict) or r_.get("draft"):
                continue
            tag_ = str(r_.get("tag_name") or "")
            if not re.search(r"\d", tag_):
                continue
            v = version_a_tupla(tag_)
            if mejor is None or v > mejor[0]:
                mejor = (v, r_)
        if mejor is None or mejor[0] <= version_a_tupla(VERSION):
            return None
        rel = mejor[1]
        tag = str(rel.get("tag_name"))
        asset = next((a for a in rel.get("assets") or []
                      if str(a.get("name", "")).lower() == ASSET_EXE.lower()), None)
        digest = str((asset or {}).get("digest") or "").lower()
        return {
            "tag": tag,
            "pre": bool(rel.get("prerelease")),
            "titulo": str(rel.get("name") or tag),
            "notas": limpiar_notas(rel.get("body")),
            "pagina": str(rel.get("html_url") or URL_RELEASES_WEB),
            "url": (asset or {}).get("browser_download_url"),
            "size": int((asset or {}).get("size") or 0),
            "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
        }
    except Exception:
        return None

def puede_autoactualizar(info):
    """Solo se reemplaza a sí mismo el .exe compilado, con asset en la release y carpeta con permiso de escritura."""
    return bool(getattr(sys, "frozen", False) and os.name == "nt" and info.get("url")
                and os.access(os.path.dirname(sys.executable), os.W_OK))

def descargar_actualizacion(info, progreso, cancelar):
    """Baja el .exe nuevo a .minecraft\\Pipolauncher\\PipoLauncher.exe.nuevo y lo valida (tamaño, SHA-256 si la
    release lo publica, y que sea un ejecutable). Devuelve la ruta. Lanza InterruptedError si se cancela."""
    os.makedirs(carpeta_pipolauncher, exist_ok=True)
    nuevo = os.path.join(carpeta_pipolauncher, ASSET_EXE + ".nuevo")
    parcial = nuevo + ".part"
    req = urllib.request.Request(info["url"], headers={"User-Agent": f"PipoLauncher/{VERSION}"})
    h = hashlib.sha256()
    hecho = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(parcial, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            while True:
                if cancelar.is_set():
                    raise InterruptedError()
                bloque = r.read(65536)
                if not bloque:
                    break
                f.write(bloque)
                h.update(bloque)
                hecho += len(bloque)
                progreso(hecho, total)
        if total and hecho != total:
            raise OSError("La descarga quedó incompleta.")
        if info.get("sha256") and h.hexdigest().lower() != info["sha256"]:
            raise OSError("El archivo descargado no coincide con el publicado (SHA-256).")
        with open(parcial, "rb") as f:
            if f.read(2) != b"MZ":
                raise OSError("El archivo descargado no es un ejecutable válido.")
        os.replace(parcial, nuevo)
    except BaseException:
        try:
            os.remove(parcial)
        except OSError:
            pass
        raise
    return nuevo

def aplicar_actualizacion(nuevo):
    """Un .exe no puede pisarse mientras corre: se lanza un .bat que espera a que el launcher cierre, reemplaza
    el .exe y lo vuelve a abrir. Después de llamar a esto hay que cerrar el launcher."""
    viejo = sys.executable
    bat = os.path.join(carpeta_pipolauncher, "actualizar.bat")
    esc = lambda p: p.replace("%", "%%")
    script = (
        "@echo off\r\nchcp 65001 >nul\r\n"
        f'set "VIEJO={esc(viejo)}"\r\nset "NUEVO={esc(nuevo)}"\r\n'
        "for /l %%i in (1,1,90) do (\r\n"
        '  move /y "%NUEVO%" "%VIEJO%" >nul 2>&1\r\n'
        '  if not exist "%NUEVO%" goto listo\r\n'
        "  ping -n 2 127.0.0.1 >nul\r\n"   # 'timeout' falla con la entrada redirigida
        ")\r\nexit /b 1\r\n"
        ':listo\r\nstart "" "%VIEJO%"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )
    with open(bat, "w", encoding="utf-8", newline="") as f:
        f.write(script)
    # El .exe nuevo no debe heredar las variables internas de PyInstaller del proceso viejo (apuntan a una
    # carpeta temporal que se borra al cerrar): sin esto, a veces arranca roto.
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    # Ventana oculta: CREATE_NO_WINDOW se ignora si se combina con DETACHED_PROCESS (cmd abría una consola visible),
    # así que se usa solo y, por las dudas, también SW_HIDE.
    oculto = subprocess.STARTUPINFO()
    oculto.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    oculto.wShowWindow = 0  # SW_HIDE
    subprocess.Popen(["cmd.exe", "/c", bat], env=env, close_fds=True, startupinfo=oculto,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ---------------------------------------------------------------------------
# INSTALADOR / ACTUALIZADOR (.minecraft: versiones, librerías, assets y Java)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# MANIFIESTO DE MOJANG + LISTA COMPLETA DE VERSIONES
# ---------------------------------------------------------------------------
def _leer_json_version(vid):
    with open(os.path.join(carpeta_versiones, vid, vid + ".json"), "r", encoding="utf-8") as f:
        return json.load(f)

def leer_manifiesto_cache():
    """Última copia guardada del manifiesto (para mostrar la lista sin internet)."""
    try:
        with open(ruta_manifiesto, "r", encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m.get("versions"), list) else None
    except Exception:
        return None

def guardar_manifiesto_cache(m):
    try:
        os.makedirs(carpeta_pipolauncher, exist_ok=True)
        tmp = ruta_manifiesto + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f)
        os.replace(tmp, ruta_manifiesto)
    except OSError:
        pass

def pedir_manifiesto(timeout=8):
    """Una consulta rápida a Mojang (para la ventana principal). None si no hay conexión."""
    try:
        req = urllib.request.Request(URL_MANIFIESTO, headers={"User-Agent": "PipoLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            m = json.loads(r.read().decode("utf-8"))
        if not isinstance(m.get("versions"), list):
            return None
        guardar_manifiesto_cache(m)
        return m
    except Exception:
        return None

def esta_instalada(vid):
    """Una versión vanilla cuenta como instalada cuando están su .json y su .jar.
    El instalador baja el .jar AL FINAL, así que si el .jar existe es porque todo lo demás ya llegó."""
    return (os.path.isfile(os.path.join(carpeta_versiones, vid, vid + ".json"))
            and os.path.isfile(os.path.join(carpeta_versiones, vid, vid + ".jar")))

def raiz_de(vid):
    """Sigue 'inheritsFrom' hasta la versión vanilla de la que parte (Forge, Fabric, OptiFine...)."""
    for _ in range(5):
        try:
            padre = _leer_json_version(vid).get("inheritsFrom")
        except Exception:
            return vid
        if not padre:
            return vid
        vid = padre
    return vid

def construir_lista(manifiesto):
    """Devuelve (ids, no_instaladas). ids: de la más nueva a la más vieja, con todas las vanilla del
    manifiesto + las versiones locales que Mojang no conoce (Forge, Fabric...), puestas debajo de su base.
    Sin manifiesto (primera vez sin internet) solo se ven las versiones instaladas."""
    locales = listar_versiones()
    if not manifiesto:
        return locales, set()
    oficiales = [v["id"] for v in manifiesto.get("versions", []) if v.get("type") in TIPOS_VANILLA]
    conocidas = set(oficiales)
    excluidas = {v["id"] for v in manifiesto.get("versions", [])} - conocidas  # snapshots, betas, alphas
    hijas, sueltas = {}, []
    for nombre in locales:
        if nombre in conocidas or nombre in excluidas:
            continue
        raiz = raiz_de(nombre)
        if raiz in conocidas:
            hijas.setdefault(raiz, []).append(nombre)
        else:
            sueltas.append(nombre)
    ids = sueltas
    for vid in oficiales:
        ids.append(vid)
        ids.extend(hijas.get(vid, []))
    return ids, {v for v in oficiales if not esta_instalada(v)}

# ---------------------------------------------------------------------------
# INSTALADOR (.minecraft: versiones, librerías, assets y Java)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# launcher_profiles.json: los instaladores de Forge, Fabric, NeoForge... se niegan a instalar si no existe
# ---------------------------------------------------------------------------
def asegurar_launcher_profiles():
    """Crea .minecraft\\launcher_profiles.json si falta (o lo repara si está dañado). Si ya existe y es válido
    no se toca nada de lo que tenga (perfiles de otros launchers incluidos): solo se completan claves que falten."""
    por_defecto = {
        "profiles": {},
        "settings": {"crashAssistance": False, "enableAdvanced": False, "enableAnalytics": False,
                     "enableHistorical": False, "enableReleases": True, "enableSnapshots": False,
                     "keepLauncherOpen": False, "profileSorting": "ByLastPlayed", "showGameLog": False,
                     "showMenu": False, "soundOn": False},
        "launcherVersion": {"format": 21, "name": "PipoLauncher", "profilesFormat": 2},
        "authenticationDatabase": {},
        "version": 3,
    }
    try:
        os.makedirs(carpeta_minecraft, exist_ok=True)
        existe = os.path.isfile(ruta_profiles)
        data = {}
        if existe:
            try:
                with open(ruta_profiles, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = None
            if not isinstance(data, dict):  # dañado: se guarda una copia y se rehace
                try:
                    os.replace(ruta_profiles, ruta_profiles + ".bak")
                except OSError:
                    pass
                data = {}
        cambio = not existe
        for clave, valor in por_defecto.items():
            if not isinstance(data.get(clave), type(valor)):
                data[clave] = valor
                cambio = True
        if cambio:
            tmp = ruta_profiles + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, ruta_profiles)
        return True
    except OSError:
        return False

# ---------------------------------------------------------------------------
# JAVA LOCAL (el de la PC, no el de los runtimes de Mojang): lo necesitan los instaladores de mods
# ---------------------------------------------------------------------------
# Versiones de Temurin (Adoptium) disponibles para Windows según arquitectura, de la más nueva a la más vieja.
JAVA_PC_DISPONIBLE = {"x64": (25, 21, 17, 11, 8), "aarch64": (25, 21, 17), "x32": (21, 17, 11, 8)}

def version_java_de(exe):
    """Versión mayor de un java.exe, ejecutándolo de verdad. None si no existe o no funciona."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        r = subprocess.run([exe, "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=20, creationflags=flags, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', (r.stderr or "") + (r.stdout or ""))
    if r.returncode != 0 or not m:
        return None
    mayor = int(m.group(1))
    return int(m.group(2) or 0) if mayor == 1 else mayor  # "1.8.0_x" => Java 8

def buscar_java_sistema():
    """Busca un Java que ya funcione en la PC (JAVA_HOME, PATH, registro, carpetas habituales y el que instala
    el propio launcher). Devuelve (ruta de java.exe, versión mayor) o None. Sirve cualquier Java 8 o superior."""
    cand = []
    jh = os.getenv("JAVA_HOME")
    if jh:
        cand.append(os.path.join(jh, "bin", "java.exe"))
    en_path = shutil.which("java")
    if en_path:
        cand.append(en_path)
    try:
        import winreg
        for clave in (r"SOFTWARE\JavaSoft\JDK", r"SOFTWARE\JavaSoft\Java Runtime Environment", r"SOFTWARE\JavaSoft\JRE"):
            for vista in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave, 0, winreg.KEY_READ | vista) as k:
                        ver = winreg.QueryValueEx(k, "CurrentVersion")[0]
                        with winreg.OpenKey(k, ver) as kv:
                            cand.append(os.path.join(winreg.QueryValueEx(kv, "JavaHome")[0], "bin", "java.exe"))
                except OSError:
                    continue
    except ImportError:
        pass
    raices = [os.getenv("ProgramFiles"), os.getenv("ProgramW6432"), os.getenv("ProgramFiles(x86)"),
              os.path.join(carpeta_local, "Programs") if carpeta_local else None]
    marcas = ("java", "jdk", "jre", "temurin", "adoptium", "zulu", "corretto", "semeru", "microsoft",
              "openjdk", "bellsoft", "liberica")
    for raiz in filter(None, raices):
        try:
            nivel1 = os.listdir(raiz)
        except OSError:
            continue
        for n1 in nivel1:
            if not any(m in n1.lower() for m in marcas):
                continue
            p1 = os.path.join(raiz, n1)
            cand.append(os.path.join(p1, "bin", "java.exe"))
            try:
                for n2 in os.listdir(p1):
                    cand.append(os.path.join(p1, n2, "bin", "java.exe"))
            except OSError:
                pass
    try:  # el que instala el propio PipoLauncher
        for n in os.listdir(carpeta_java_local):
            cand.append(os.path.join(carpeta_java_local, n, "bin", "java.exe"))
    except OSError:
        pass

    vistos = set()
    for exe in cand:
        clave = os.path.normcase(os.path.abspath(exe))
        if clave in vistos or not os.path.isfile(exe):
            continue
        vistos.add(clave)
        mayor = version_java_de(exe)
        if mayor and mayor >= 8:
            return exe, mayor
    return None

def arch_windows():
    """Arquitectura REAL del equipo en el vocabulario de Adoptium (x64 / aarch64 / x32), aunque Python sea de 32 bits."""
    a = (os.getenv("PROCESSOR_ARCHITEW6432") or os.getenv("PROCESSOR_ARCHITECTURE") or platform.machine()).lower()
    if a in ("amd64", "x86_64"):
        return "x64"
    if a in ("arm64", "aarch64"):
        return "aarch64"
    return "x32"

def java_candidatos():
    """(arquitectura, [versiones de Java a probar, de la mejor a la más conservadora]) según el hardware y la
    versión de Windows: Java 25/21 piden Windows 10+, Java 17 Windows 8.1+, Java 11 Windows 7+."""
    arch = arch_windows()
    try:
        w = sys.getwindowsversion()
        ver = (w.major, w.minor)
    except AttributeError:
        ver = (10, 0)
    tope = 99 if ver >= (10, 0) else 17 if ver >= (6, 3) else 11 if ver >= (6, 1) else 8
    return arch, [v for v in JAVA_PC_DISPONIBLE.get(arch, (17, 11, 8)) if v <= tope] or [8]

def registrar_java_usuario(java_exe):
    """Deja el Java instalado por el launcher usable desde Windows SIN permisos de administrador (solo el usuario
    actual): JAVA_HOME y PATH, y la apertura de archivos .jar (doble clic al instalador de Forge) si ningún otro
    programa la tiene. Es 'mejor esfuerzo': si algo falla, el Java queda instalado igual."""
    try:
        import winreg
    except ImportError:
        return
    try:
        bin_dir = os.path.dirname(java_exe)
        home = os.path.dirname(bin_dir)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                path_actual = winreg.QueryValueEx(k, "Path")[0]
            except OSError:
                path_actual = ""
            if os.path.normcase(bin_dir) not in [os.path.normcase(p.strip()) for p in path_actual.split(";")]:
                nuevo = (path_actual.rstrip(";") + ";" if path_actual else "") + bin_dir
                winreg.SetValueEx(k, "Path", 0, winreg.REG_EXPAND_SZ, nuevo)
            try:
                winreg.QueryValueEx(k, "JAVA_HOME")
            except OSError:
                winreg.SetValueEx(k, "JAVA_HOME", 0, winreg.REG_SZ, home)
        try:  # avisar a Windows para que las ventanas nuevas lean las variables
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 2, 5000, None)
        except Exception:
            pass
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ".jar"))
        except OSError:  # nadie abre .jar todavía: se asocia al Java del launcher
            javaw = os.path.join(bin_dir, "javaw.exe")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.jar") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, "jarfile")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\jarfile\shell\open\command") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, f'"{javaw}" -jar "%1" %*')
            try:
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            except Exception:
                pass
    except OSError:
        pass

class Cancelado(Exception):
    pass

class ErrorRed(Exception):
    pass

class ErrorVersion(Exception):
    pass

def marca_java(comp):
    """Archivo que el launcher deja cuando termina de instalar un runtime (así no vuelve a revisarlo por red)."""
    return os.path.join(carpeta_minecraft, "runtime", comp, PLATAFORMA_JAVA, comp + ".pipolauncher")

def java_completo(comp):
    return os.path.isfile(rutas_java(comp)[0]) or os.path.isfile(marca_java(comp))

def _marcar_java(comp):
    try:
        os.makedirs(os.path.dirname(marca_java(comp)), exist_ok=True)
        open(marca_java(comp), "w").close()
    except OSError:
        pass

class Instalador:
    """Descarga lo que falta desde los servidores de Mojang. Corre en un hilo: la interfaz consulta
    snapshot() para mostrar el avance. Los archivos que ya existen (librerías, assets y Java
    compartidos entre versiones) se saltean solos."""

    def __init__(self):
        self._cancelar = threading.Event()
        self._lock = threading.Lock()
        self._titulo = ""
        self._detalle = ""
        self._total_archivos = 0
        self._total_bytes = 0
        self._hechos = 0
        self._exitos = 0
        self._bytes = 0
        self._fallidos = []

    # ----- estado para la interfaz -----
    def cancelar(self):
        self._cancelar.set()

    def _fase(self, titulo, detalle=""):
        with self._lock:
            self._titulo, self._detalle = titulo, detalle

    def snapshot(self):
        with self._lock:
            s = {"titulo": self._titulo, "detalle": self._detalle, "frac": None}
            if self._total_archivos:
                s["frac"] = min(1.0, self._bytes / self._total_bytes) if self._total_bytes else 0.0
                s["detalle"] = (f"{self._hechos} de {self._total_archivos} archivos  ·  "
                                f"{self._bytes / 1048576:.0f} de {self._total_bytes / 1048576:.0f} MB")
            return s

    def _log(self, msg):
        try:
            os.makedirs(carpeta_logs, exist_ok=True)
            with open(os.path.join(carpeta_logs, "instalador.log"), "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except OSError:
            pass

    # ----- red -----
    def _json(self, url):
        for intento in range(3):
            if self._cancelar.is_set():
                raise Cancelado()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "PipoLauncher/1.0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError) as e:
                self._log(f"Fallo al leer {url}: {e} (intento {intento + 1})")
                time.sleep(1)
        raise ErrorRed(url)

    def obtener_manifiesto(self):
        """Manifiesto actual de Mojang; si no hay internet, la última copia guardada."""
        try:
            m = self._json(URL_MANIFIESTO)
            guardar_manifiesto_cache(m)
            return m
        except ErrorRed:
            m = leer_manifiesto_cache()
            if m:
                self._log("Sin conexión: se usa la copia guardada del manifiesto")
                return m
            raise

    def _descargar(self, url, destino, sha1=None, size=0, contar=False, algo="sha1"):
        """Descarga a un .part, verifica el hash (SHA1 por defecto) y recién ahí lo mueve a su lugar definitivo."""
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        tmp = destino + ".part"
        ultimo_error = None
        for intento in range(3):
            local = 0
            try:
                h = hashlib.new(algo)
                req = urllib.request.Request(url, headers={"User-Agent": "PipoLauncher/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                    while True:
                        if self._cancelar.is_set():
                            raise Cancelado()
                        bloque = r.read(65536)
                        if not bloque:
                            break
                        f.write(bloque)
                        h.update(bloque)
                        local += len(bloque)
                        if contar:
                            with self._lock:
                                self._bytes += len(bloque)
                if sha1 and h.hexdigest().lower() != sha1.lower():
                    raise OSError("el SHA1 no coincide")
                os.replace(tmp, destino)
                return
            except Cancelado:
                self._borrar(tmp)
                raise
            except Exception as e:
                ultimo_error = e
                self._borrar(tmp)
                if contar:
                    with self._lock:
                        self._bytes -= local
                time.sleep(1)
        raise OSError(f"{url}: {ultimo_error}")

    @staticmethod
    def _borrar(ruta):
        try:
            os.remove(ruta)
        except OSError:
            pass

    def _bajar(self, tarea):
        url, destino, sha1, size = tarea
        try:
            self._descargar(url, destino, sha1, size, contar=True)
            with self._lock:
                self._hechos += 1
                self._exitos += 1
        except Cancelado:
            raise
        except Exception as e:
            self._log(f"No se pudo descargar {destino}: {e}")
            with self._lock:
                self._hechos += 1
                self._fallidos.append(destino)

    def _descargar_grupo(self, titulo, tareas):
        self._fase(titulo)
        ex = ThreadPoolExecutor(max_workers=HILOS_DESCARGA)
        try:
            futuros = [ex.submit(self._bajar, t) for t in tareas]
            for fut in as_completed(futuros):
                fut.result()  # re-lanza Cancelado si corresponde
        except BaseException:
            self._cancelar.set()
            ex.shutdown(wait=False, cancel_futures=True)
            raise
        ex.shutdown(wait=True)

    # ----- análisis -----
    @staticmethod
    def _ok(destino, size):
        try:
            return os.path.getsize(destino) == size if size else os.path.isfile(destino)
        except OSError:
            return False

    def _agregar(self, tareas, url, destino, sha1, size):
        if destino not in tareas and not self._ok(destino, size):
            tareas[destino] = (url, destino, sha1, size)

    def _asegurar_json(self, vid, en_manifiesto, nivel=0):
        """Garantiza que exista el .json de la versión (y el de su versión base, si hereda)."""
        ruta = os.path.join(carpeta_versiones, vid, vid + ".json")
        try:
            data = _leer_json_version(vid)
        except (OSError, ValueError):
            data = None
        if data is None:
            info = en_manifiesto.get(vid)
            if not info:
                return False  # versión modificada/desconocida: no hay de dónde bajarla
            try:
                self._descargar(info["url"], ruta, info.get("sha1"))
                data = _leer_json_version(vid)
            except Cancelado:
                raise
            except Exception as e:
                self._log(f"No se pudo obtener el json de {vid}: {e}")
                return False
        padre = data.get("inheritsFrom")
        if padre and nivel < 5:
            self._asegurar_json(padre, en_manifiesto, nivel + 1)
        return True

    def _plan_version(self, data, libs, jars, assets, copias, indices_vistos, java_necesario):
        # .jar del cliente (de la versión y de su base). Se baja AL FINAL: es la marca de "instalada".
        for v in data["_cadena"]:
            try:
                raw = _leer_json_version(v)
            except Exception:
                continue
            cl = (raw.get("downloads") or {}).get("client")
            if cl and cl.get("url"):
                self._agregar(jars, cl["url"], os.path.join(carpeta_versiones, v, v + ".jar"),
                              cl.get("sha1"), cl.get("size", 0))

        # librerías
        for lib in data.get("libraries", []):
            if not permitido(lib.get("rules")):
                continue
            dl = lib.get("downloads") or {}
            nat = lib.get("natives")
            if nat:  # formato viejo: jar de natives aparte
                clasif = nat.get("windows")
                if not clasif:
                    continue
                clasif = clasif.replace("${arch}", "64")
                info = (dl.get("classifiers") or {}).get(clasif)
                destino = ruta_lib(lib, clasif)
            else:
                info = dl.get("artifact")
                destino = ruta_lib(lib)
            if info and info.get("url"):
                self._agregar(libs, info["url"], destino, info.get("sha1"), info.get("size", 0))
            elif not info and lib.get("url"):  # estilo Maven (Fabric, Quilt...)
                rel = os.path.relpath(destino, carpeta_libs).replace(os.sep, "/")
                self._agregar(libs, lib["url"].rstrip("/") + "/" + rel, destino,
                              lib.get("sha1"), lib.get("size", 0))

        # índice de assets y sus objetos
        ai = data.get("assetIndex")
        if ai and ai.get("id") and ai["id"] not in indices_vistos:
            indices_vistos.add(ai["id"])
            ruta_idx = os.path.join(carpeta_assets, "indexes", ai["id"] + ".json")
            idx = None
            if self._ok(ruta_idx, ai.get("size", 0)):
                try:
                    with open(ruta_idx, "r", encoding="utf-8") as f:
                        idx = json.load(f)
                except (OSError, ValueError):
                    idx = None
            if idx is None:
                self._descargar(ai["url"], ruta_idx, ai.get("sha1"))
                with open(ruta_idx, "r", encoding="utf-8") as f:
                    idx = json.load(f)
            objetos = idx.get("objects", {})
            for obj in objetos.values():
                h = obj["hash"]
                self._agregar(assets, URL_ASSETS + h[:2] + "/" + h,
                              os.path.join(carpeta_assets, "objects", h[:2], h), h, obj.get("size", 0))
            if idx.get("map_to_resources"):
                copias.append((os.path.join(carpeta_minecraft, "resources"), objetos))
            elif idx.get("virtual"):
                copias.append((os.path.join(carpeta_assets, "virtual", ai["id"]), objetos))

        comp, mayor = java_requerido(data)
        java_necesario[comp] = mayor

    def _copiar_virtuales(self, copias):
        """Versiones viejas (<=1.7) leen los sonidos con su nombre real, no por hash."""
        for base, objetos in copias:
            for nombre, obj in objetos.items():
                if self._cancelar.is_set():
                    raise Cancelado()
                h = obj["hash"]
                origen = os.path.join(carpeta_assets, "objects", h[:2], h)
                destino = os.path.join(base, *nombre.split("/"))
                if os.path.isfile(origen) and not self._ok(destino, obj.get("size", 0)):
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    shutil.copyfile(origen, destino)

    def _plan_java(self, comp, catalogo):
        """Tareas para instalar un runtime de Java; None si el catálogo de Mojang no lo ofrece."""
        if not catalogo.get(comp):
            return None
        man = self._json(catalogo[comp][0]["manifest"]["url"])
        base = os.path.join(carpeta_minecraft, "runtime", comp, PLATAFORMA_JAVA, comp)
        tareas = {}
        for ruta, f in (man.get("files") or {}).items():
            raw = (f.get("downloads") or {}).get("raw")
            if f.get("type") == "file" and raw:
                self._agregar(tareas, raw["url"], os.path.join(base, *ruta.split("/")),
                              raw.get("sha1"), raw.get("size", 0))
        return list(tareas.values())

    # ----- Java de la PC (para instaladores de Forge, etc.) -----
    def _instalar_java_local(self, mayor, arch):
        """Baja Temurin 'mayor' (JRE; si no hay, JDK) y lo deja en .minecraft\\Pipolauncher\\java\\java-<mayor>.
        Devuelve la ruta de java.exe, ya probado. Lanza excepción si no se puede (el llamador baja de versión)."""
        self._fase(f"Preparando Java {mayor}", "Consultando Eclipse Temurin…")
        paquete = None
        for tipo in ("jre", "jdk"):
            lista = self._json(f"{URL_ADOPTIUM}/assets/latest/{mayor}/hotspot?architecture={arch}"
                               f"&image_type={tipo}&os=windows&vendor=eclipse")
            if isinstance(lista, list) and lista:
                pkg = lista[0]["binary"]["package"]
                if str(pkg.get("name", "")).lower().endswith(".zip"):
                    paquete = pkg
                    break
        if not paquete:
            raise ErrorVersion(f"No hay un paquete de Java {mayor} para {arch}")

        destino = os.path.join(carpeta_java_local, f"java-{mayor}")
        tmp = destino + ".tmp"
        zip_ruta = os.path.join(carpeta_java_local, f"temurin-{mayor}.zip")
        with self._lock:
            self._total_archivos, self._total_bytes = 1, max(paquete.get("size", 0), 1)
            self._hechos = self._bytes = 0
        try:
            self._fase(f"Descargando Java {mayor}")
            self._descargar(paquete["link"], zip_ruta, paquete.get("checksum"), paquete.get("size", 0),
                            contar=True, algo="sha256")
            self._fase(f"Instalando Java {mayor}", "Extrayendo archivos…")
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(destino, ignore_errors=True)
            with zipfile.ZipFile(zip_ruta) as z:
                z.extractall(tmp)
            raiz = next((os.path.join(tmp, n) for n in os.listdir(tmp)
                         if os.path.isfile(os.path.join(tmp, n, "bin", "java.exe"))), None)
            if raiz is None:
                raise ErrorVersion("El paquete de Java descargado no tiene java.exe")
            os.replace(raiz, destino)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self._borrar(zip_ruta)
        exe = os.path.join(destino, "bin", "java.exe")
        if version_java_de(exe) is None:  # bajó bien pero no corre en este equipo => se prueba una versión menor
            shutil.rmtree(destino, ignore_errors=True)
            raise ErrorVersion(f"Java {mayor} no funciona en este equipo")
        return exe

    def asegurar_java_local(self):
        """Si la PC ya tiene un Java que funciona, no hace nada más. Si no, instala el mejor Java disponible para
        su hardware y su Windows (empezando por el más nuevo, p. ej. 25) y baja de versión si algo falla.
        Devuelve {'ruta', 'mayor', 'origen': 'sistema' | 'instalado'} o None si no se pudo instalar ninguno."""
        self._fase("Revisando Java del sistema", "Buscando Java en tu PC…")
        hallado = buscar_java_sistema()
        if self._cancelar.is_set():
            raise Cancelado()
        if hallado:
            self._log(f"Java local detectado: {hallado[0]} (Java {hallado[1]})")
            return {"ruta": hallado[0], "mayor": hallado[1], "origen": "sistema"}
        arch, versiones = java_candidatos()
        self._log(f"La PC no tiene Java. Arquitectura {arch}; se probará: {', '.join(map(str, versiones))}")
        for mayor in versiones:
            try:
                exe = self._instalar_java_local(mayor, arch)
            except Cancelado:
                raise
            except Exception as e:
                self._log(f"No se pudo instalar Java {mayor}: {e}. Se prueba con una versión anterior.")
                continue
            registrar_java_usuario(exe)
            self._log(f"Java {mayor} instalado en {exe}")
            return {"ruta": exe, "mayor": mayor, "origen": "instalado"}
        self._log("No se pudo instalar ninguna versión de Java en la PC")
        return None

    # ----- proceso completo -----
    def ejecutar(self, vids=(), java_extra=(), estricto=False, java_local=False):
        """Completa .minecraft para las versiones 'vids' (.json, librerías, assets, Java y .jar) más los
        runtimes de 'java_extra'. Con vids=() solo prepara Java (primer inicio). Con estricto=True
        (descarga de una versión puntual) cualquier problema con la versión lanza una excepción.
        Devuelve {'descargados', 'mb', 'errores', 'java', 'manifiesto'}."""
        try:
            os.makedirs(carpeta_logs, exist_ok=True)
            open(os.path.join(carpeta_logs, "instalador.log"), "w").close()
        except OSError:
            pass
        res = {"descargados": 0, "mb": 0, "errores": [], "java": [], "manifiesto": None, "java_local": None}
        asegurar_launcher_profiles()
        if java_local:  # primero, antes de tocar la red de Mojang: si la PC ya tiene Java no se descarga nada
            try:
                res["java_local"] = self.asegurar_java_local()
            except Cancelado:
                raise
            except Exception:
                self._log("Error al preparar el Java de la PC:\n" + traceback.format_exc())
            finally:
                with self._lock:  # el contador de progreso vuelve a cero para las descargas siguientes
                    self._total_archivos = self._total_bytes = self._hechos = self._exitos = self._bytes = 0
        self._fase("Analizando", "Conectando con los servidores de Mojang…")
        for d in (carpeta_versiones, carpeta_libs, carpeta_assets):
            os.makedirs(d, exist_ok=True)

        manifiesto = self.obtener_manifiesto()
        res["manifiesto"] = manifiesto
        en_manifiesto = {v["id"]: v for v in manifiesto["versions"]}

        # 1) qué le falta a cada versión (json, librerías, assets) y qué Java necesita
        libs, jars, assets, copias, indices, java_necesario = {}, {}, {}, [], set(), {}
        for vid in vids:
            self._fase("Analizando", f"Revisando Minecraft {vid}…")
            if not self._asegurar_json(vid, en_manifiesto):
                if estricto:
                    raise ErrorVersion(f"No se pudo obtener la información de la versión {vid}.")
                self._log(f"Se omite {vid}: no hay json y Mojang no la conoce")
                continue
            try:
                data = cargar_version(vid)
            except Exception as e:
                if estricto:
                    raise ErrorVersion(f"La versión {vid} está dañada o incompleta: {e}")
                self._log(f"Se omite {vid}: {e}")
                continue
            self._plan_version(data, libs, jars, assets, copias, indices, java_necesario)

        # 2) Java: los que pidan las versiones + los precargados. Solo se consulta la red si falta alguno.
        comps = {c: JAVA_MAYOR.get(c) for c in java_extra}
        comps.update(java_necesario)
        grupos_java, catalogo = [], None
        for comp in sorted(comps, key=lambda c: (comps[c] or 99, c)):
            res["java"].append(comps[comp] or comp)
            if java_completo(comp):
                continue
            self._fase("Analizando", f"Revisando Java {comps[comp] or comp}…")
            if catalogo is None:
                catalogo = self._json(URL_JAVA).get(PLATAFORMA_JAVA, {})
            tareas = self._plan_java(comp, catalogo)
            if tareas is None:
                if comp in java_necesario and estricto:
                    raise ErrorVersion(f"Mojang no ofrece Java {comps[comp] or comp} para esta plataforma.")
                res["java"].remove(comps[comp] or comp)
                continue
            if tareas:
                grupos_java.append((f"Instalando Java {comps[comp] or comp}", tareas,
                                    lambda c=comp: _marcar_java(c)))
            else:
                _marcar_java(comp)  # ya estaba todo

        # 3) descargas. El .jar va último y solo si todo lo anterior salió bien.
        grupos = []
        if libs:
            grupos.append(("Descargando librerías", list(libs.values()), None))
        grupos += grupos_java
        if assets:
            grupos.append(("Descargando sonidos, idiomas y recursos", list(assets.values()), None))
        grupo_jar = ("Descargando el juego", list(jars.values()), None) if jars else None
        todos = grupos + ([grupo_jar] if grupo_jar else [])
        with self._lock:
            self._total_archivos = sum(len(g[1]) for g in todos)
            self._total_bytes = sum(max(t[3], 1) for g in todos for t in g[1])

        for titulo, tareas, al_completar in grupos:
            antes = len(self._fallidos)
            self._descargar_grupo(titulo, tareas)
            if al_completar and len(self._fallidos) == antes:
                al_completar()

        if copias:
            self._fase("Preparando recursos del juego", "Ordenando archivos…")
            self._copiar_virtuales(copias)

        if grupo_jar and not self._fallidos:
            self._descargar_grupo(*grupo_jar[:2])

        res["descargados"] = self._exitos
        res["mb"] = round(self._bytes / 1048576)
        res["errores"] = list(self._fallidos)
        return res

# ---------------------------------------------------------------------------
# INTERFAZ
# ---------------------------------------------------------------------------
# Logo de la ventana (head.png de 96x96 en base64): aparece aunque no esté head.png junto al launcher.
LOGO_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAABPUlEQVR42u3csU3DQACG0bvIMkGhAtF6AnrmYJ+U2SclMyDRmQnS"
    "RqTCinCTzPAXFjZ5X33KOX66Kyz76nG/u5SkzWM0vNxtyqL7HbLxwykavir60wAAACAAAAQAgAAAEAAAAgBAAAAIAAABACAAAATg"
    "f1b7vo/eCxrHMZqg+/la9A06PLxE49u2tQJsQQIAQAAACAAAAQAgAHOtllIuboMVAEAAAAgAAAEAIAAABOAmauZ2Qcf9btLff37b"
    "WgECAEAAAAgAAAACAEAAbrU69dnRh6fXaHz6jVVa/I3b90c2gbOjbUECAEAAAAgAAAEAIADzLX4vKH22s/TS/9sN71aALUgAAAgA"
    "AAEAIAAABGCuNWWVPQ7qTp/ZDOv7bPyQHl9Up71D4zm7mmZtBdiCBACAAAAQAAACAEAA5toVG1IqeOz6PacAAAAASUVORK5CYII="
)


def cargar_logo(lado):
    """head.png junto al launcher si existe (así se puede cambiar); si no, el logo embebido."""
    import base64, io
    try:
        im = Image.open(ruta_recurso("head.png"))
        im.load()
    except Exception:
        im = Image.open(io.BytesIO(base64.b64decode(LOGO_B64)))
    # NEAREST: es pixel art, así los píxeles quedan nítidos al achicarlo
    return im.convert("RGBA").resize((lado, lado), Image.Resampling.NEAREST)


def hacer_fondos(W, H, BARRA):
    """Arma las imágenes de la interfaz con PIL: el fondo (con degradados oscuros arriba y abajo para que
    se lea el texto) y una versión desenfocada/oscura para la pantalla de configuración."""
    from PIL import ImageFilter, ImageEnhance, ImageOps
    base = None
    try:
        im = Image.open(ruta_recurso("fondo.png")).convert("RGB")
        esc = max(W / im.width, H / im.height)  # "cubrir": se escala y se recorta al centro
        im = im.resize((max(W, round(im.width * esc)), max(H, round(im.height * esc))), Image.Resampling.LANCZOS)
        izq, arriba = (im.width - W) // 2, (im.height - H) // 2
        base = im.crop((izq, arriba, izq + W, arriba + H))
    except Exception:
        base = None
    if base is None:  # sin fondo.png: degradado verde oscuro
        base = ImageOps.colorize(Image.linear_gradient("L").resize((W, H)), "#3d7a3a", "#0c160c")

    def degradado(w, h, a0, a1):
        return Image.linear_gradient("L").resize((w, h)).point(lambda v: int(a0 + (a1 - a0) * v / 255))

    alfa = Image.new("L", (W, H), 0)
    alfa.paste(degradado(W, 110, 150, 0), (0, 0))                       # sombra suave arriba (título)
    alfa.paste(degradado(W, 80, 0, 210), (0, H - BARRA - 80))           # transición hacia la barra
    alfa.paste(Image.new("L", (W, BARRA), 210), (0, H - BARRA))         # barra inferior
    principal = Image.composite(Image.new("RGB", (W, H), (8, 14, 8)), base, alfa)
    config = ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(5))).enhance(0.38)
    return principal, config


# Paleta de la interfaz
C_CAMPO = "#1b261b"      # fondo de campos
C_BORDE = "#3d6b3d"
C_VERDE = "#5dbb3b"      # acento / botón jugar
C_VERDE_H = "#6fd14a"
C_AMBAR = "#f0a30a"      # botón descargar
C_AMBAR_H = "#ffb824"
C_GRIS = "#9db89d"


def main():
    cfg = cargar_config()
    asegurar_launcher_profiles()  # Forge & cía. no se instalan sin este archivo
    total_ram = ram_total_gb()
    ram_max = ram_maxima_gb(total_ram)
    cfg["ram"] = max(1, min(cfg["ram"], ram_max))  # por si el tope cambió desde la última vez
    try:
        migrar_perfiles_antiguos(cfg)  # perfiles del sistema anterior (uno por versión) -> perfiles con nombre
        if os.path.isfile(ruta_args):   # restos de un lanzamiento anterior (podría contener un token)
            os.remove(ruta_args)
    except OSError:
        pass

    ventana = tk.Tk()
    ventana.withdraw()  # oculta hasta terminar de revisar actualizaciones (ver el final de main)
    ventana.title("PipoLauncher")
    W, H, BARRA = 960, 540, 96
    x = (ventana.winfo_screenwidth() // 2) - (W // 2)
    y = (ventana.winfo_screenheight() // 2) - (H // 2)
    ventana.geometry(f"{W}x{H}+{x}+{y}")
    ventana.resizable(False, False)
    ventana.configure(bg="#0c160c")

    try:
        ventana.iconbitmap(ruta_recurso("icono.ico"))
    except Exception:
        pass

    img_principal, img_config = hacer_fondos(W, H, BARRA)
    ventana.fondo_principal = ImageTk.PhotoImage(img_principal)  # referencias para que no las borre el GC
    ventana.fondo_config = ImageTk.PhotoImage(img_config)

    # ----- estilos -----
    estilo = ttk.Style(ventana)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("Pipo.TCombobox", fieldbackground=C_CAMPO, background="#2d4a2d", foreground="white",
                     arrowcolor="white", bordercolor=C_BORDE, lightcolor=C_BORDE, darkcolor=C_BORDE,
                     selectbackground=C_CAMPO, selectforeground="white", padding=4)
    estilo.map("Pipo.TCombobox",
               fieldbackground=[("readonly", C_CAMPO), ("disabled", "#141c14")],
               foreground=[("disabled", "#6f826f")],
               selectbackground=[("readonly", C_CAMPO)], selectforeground=[("readonly", "white")],
               background=[("active", "#3a5f3a")])
    estilo.configure("Pipo.Horizontal.TProgressbar", troughcolor=C_CAMPO, background=C_VERDE,
                     bordercolor=C_BORDE, lightcolor=C_VERDE, darkcolor=C_VERDE)
    ventana.option_add("*TCombobox*Listbox.background", C_CAMPO)
    ventana.option_add("*TCombobox*Listbox.foreground", "white")
    ventana.option_add("*TCombobox*Listbox.selectBackground", C_VERDE)
    ventana.option_add("*TCombobox*Listbox.selectForeground", "black")
    ventana.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))

    def boton(padre, texto_, color, color_h, fuente, comando, fg="white"):
        b = tk.Button(padre, text=texto_, font=fuente, bg=color, fg=fg, activebackground=color_h,
                      activeforeground=fg, relief="flat", bd=0, cursor="hand2", command=comando)
        b.bind("<Enter>", lambda e: b.configure(bg=color_h) if str(b["state"]) != "disabled" else None)
        b.bind("<Leave>", lambda e: b.configure(bg=color))
        return b

    # ----- pantalla principal -----
    canvas = tk.Canvas(ventana, width=W, height=H, highlightthickness=0, bg="#0c160c")
    canvas.place(x=0, y=0)
    canvas.create_image(0, 0, image=ventana.fondo_principal, anchor="nw")

    def texto(cv, xx, yy, s, fuente, color="white", anchor="center", sombra=True):
        """Texto con sombra; devuelve los ids para poder cambiarlo después."""
        ids = []
        if sombra:
            ids.append(cv.create_text(xx + 1, yy + 1, text=s, font=fuente, fill="black", anchor=anchor))
        ids.append(cv.create_text(xx, yy, text=s, font=fuente, fill=color, anchor=anchor))
        return ids

    def cambiar_texto(ids, s):
        for i in ids:
            canvas.itemconfigure(i, text=s)

    # Logo + título: al tocarlos se abre URL_CANAL en el navegador por defecto del dispositivo
    fuente_titulo = ("Segoe UI", 24, "bold")
    x_titulo = 30
    try:
        LOGO = 46
        ventana.logo = ImageTk.PhotoImage(cargar_logo(LOGO))  # referencia para que no la borre el GC
        canvas.create_rectangle(29, 40 - LOGO // 2 - 1, 30 + LOGO, 40 + LOGO // 2 + 1,
                                outline="#0c160c", width=2, tags="enlace")
        canvas.create_image(30, 40, image=ventana.logo, anchor="w", tags="enlace")
        x_titulo = 30 + LOGO + 12
    except Exception:
        pass
    t1 = texto(canvas, x_titulo, 40, "PIPO", fuente_titulo, anchor="w")
    x2 = canvas.bbox(t1[-1])[2]
    t2 = texto(canvas, x2, 40, "LAUNCHER", fuente_titulo, color=C_VERDE, anchor="w")
    for i in t1 + t2:
        canvas.addtag_withtag("enlace", i)
    x_fin = canvas.bbox(t2[-1])[2]
    subrayado = canvas.create_line(x_titulo, 62, x_fin, 62, fill=C_VERDE, width=2, state="hidden")

    def sobre_enlace(e):
        bb = canvas.bbox("enlace")
        return bool(bb) and bb[0] - 4 <= e.x <= bb[2] + 4 and bb[1] - 4 <= e.y <= bb[3] + 4

    def mover_sobre_enlace(e):
        dentro = sobre_enlace(e)
        canvas.configure(cursor="hand2" if dentro else "")
        canvas.itemconfigure(subrayado, state="normal" if dentro else "hidden")

    def salir_de_enlace(_e):
        canvas.configure(cursor="")
        canvas.itemconfigure(subrayado, state="hidden")

    def abrir_url(url):
        """Abre url en el navegador por defecto; si no se puede, muestra el enlace para copiarlo."""
        try:
            abierto = webbrowser.open(url, new=2)
        except Exception:
            abierto = False
        if not abierto:
            messagebox.showinfo("Enlace", "No se pudo abrir el navegador.\n\n" + url)

    def abrir_canal(e):
        if sobre_enlace(e):
            abrir_url(URL_CANAL)
    canvas.bind("<Motion>", mover_sobre_enlace)
    canvas.bind("<Leave>", salir_de_enlace)
    canvas.bind("<Button-1>", abrir_canal)

    # Estado de la ventana
    estado = {"manifiesto": leer_manifiesto_cache(), "no_inst": set(), "aviso": "",
              "inst": None, "cerrando": False, "perfiles": [], "sel": None, "cuenta": leer_cuenta(), "sesion": None}

    # Línea de estado: avisos (sin conexión) y, durante una descarga, el avance
    linea = texto(canvas, W // 2, H - BARRA - 18, "", ("Segoe UI", 10, "bold"))

    # Barra inferior: nombre | versión | botón principal
    YC = H - BARRA // 2 + 8
    lbl_cuenta = texto(canvas, 27, H - BARRA + 14, "NOMBRE (OFFLINE)", ("Segoe UI", 8, "bold"), color=C_GRIS, anchor="w",
                       sombra=False)
    texto(canvas, 252, H - BARRA + 14, "PERFIL", ("Segoe UI", 8, "bold"), color=C_GRIS, anchor="w", sombra=False)

    # Esquina de la cuenta. Con sesión: foto + nombre en texto plano (no se edita). Sin sesión: campo editable
    # con el nick para jugar offline.
    caja_cuenta = canvas.create_rectangle(27, YC - 17, 227, YC + 17, fill=C_CAMPO, outline=C_BORDE)
    entry_usuario = tk.Entry(ventana, font=("Segoe UI", 12), bg=C_CAMPO, fg="white", insertbackground="white",
                             disabledbackground="#141c14", disabledforeground="#6f826f", relief="flat",
                             highlightthickness=1, highlightbackground=C_BORDE, highlightcolor=C_VERDE)
    entry_usuario.insert(0, cfg["usuario"] or "Invitado")
    win_usuario = canvas.create_window(27, YC, window=entry_usuario, width=200, height=34, anchor="w")
    img_cara = canvas.create_image(33, YC, anchor="w", state="hidden")
    txt_cuenta = canvas.create_text(33, YC, anchor="w", text="", font=("Segoe UI", 11, "bold"), fill="white")

    TXT_NUEVO = "＋  Crear nuevo perfil"
    combo = ttk.Combobox(ventana, values=[], state="readonly", font=("Segoe UI", 11), style="Pipo.TCombobox")
    canvas.create_window(252, YC, window=combo, width=300, height=34, anchor="w")
    btn_editar = boton(ventana, "✎", C_CAMPO, "#2d4a2d", ("Segoe UI Symbol", 12), lambda: dialogo_perfil(perfil_actual()))
    btn_editar.configure(highlightthickness=1, highlightbackground=C_BORDE)
    canvas.create_window(556, YC, window=btn_editar, width=34, height=34, anchor="w")

    # Botón principal (Jugar / Descargar) y, mientras se descarga, barra de progreso + cancelar
    BX, BW, BH = 606, 330, 54
    btn_jugar = boton(ventana, "JUGAR", C_VERDE, C_VERDE_H, ("Segoe UI", 17, "bold"),
                      lambda: lanzar(), fg="#0c1a0c")
    win_jugar = canvas.create_window(BX, YC - 2, window=btn_jugar, width=BW, height=BH, anchor="w")
    btn_descargar = boton(ventana, "DESCARGAR Y JUGAR", C_AMBAR, C_AMBAR_H, ("Segoe UI", 15, "bold"),
                          lambda: descargar_y_lanzar(), fg="#241800")
    win_descargar = canvas.create_window(BX, YC - 2, window=btn_descargar, width=BW, height=BH,
                                         anchor="w", state="hidden")

    barra = ttk.Progressbar(ventana, mode="determinate", maximum=100, style="Pipo.Horizontal.TProgressbar")
    win_barra = canvas.create_window(BX, YC - 2, window=barra, width=BW - 62, height=26,
                                     anchor="w", state="hidden")
    btn_cancelar = boton(ventana, "✕", "#8e2f2f", "#b03a3a", ("Segoe UI Symbol", 12, "bold"),
                         lambda: pedir_cancelar())
    win_cancelar = canvas.create_window(BX + BW - 52, YC - 2, window=btn_cancelar, width=52, height=26,
                                        anchor="w", state="hidden")

    # Engranaje / casa (arriba a la derecha)
    btn_cfg = tk.Button(ventana, text="⚙", font=("Segoe UI Symbol", 15), bg=C_CAMPO, fg="white",
                        activebackground="#2d4a2d", activeforeground="white", relief="flat", bd=0,
                        cursor="hand2", command=lambda: alternar_config(),
                        highlightthickness=1, highlightbackground=C_BORDE)
    btn_cfg.place(x=W - 18, y=18, anchor="ne", width=40, height=40)

    # Botón de información (a la izquierda del engranaje): abre el repositorio de GitHub
    btn_info = tk.Button(ventana, text="\u2139", font=("Segoe UI Symbol", 15, "bold"), bg=C_CAMPO, fg="white",
                         activebackground="#2d4a2d", activeforeground="white", relief="flat", bd=0,
                         cursor="hand2", command=lambda: abrir_url(URL_INFO),
                         highlightthickness=1, highlightbackground=C_BORDE)
    btn_info.place(x=W - 18 - 40 - 8, y=18, anchor="ne", width=40, height=40)
    btn_info.bind("<Enter>", lambda e: btn_info.configure(bg="#2d4a2d"))
    btn_info.bind("<Leave>", lambda e: btn_info.configure(bg=C_CAMPO))

    # Iniciar sesión (debajo de ℹ y ⚙, centrado entre los dos)
    btn_login = tk.Button(ventana, text="Iniciar sesión", font=("Segoe UI", 9, "bold"), bg=C_CAMPO, fg="white",
                          activebackground="#2d4a2d", activeforeground="white", relief="flat", bd=0,
                          cursor="hand2", command=lambda: alternar_sesion(),
                          highlightthickness=1, highlightbackground=C_BORDE)
    btn_login.place(x=W - 18 - (40 + 8 + 40) // 2, y=18 + 40 + 8, anchor="n", width=96, height=28)
    btn_login.bind("<Enter>", lambda e: btn_login.configure(bg="#2d4a2d") if str(btn_login["state"]) != "disabled" else None)
    btn_login.bind("<Leave>", lambda e: btn_login.configure(bg=C_CAMPO))

    # ----- lista de perfiles -----
    def perfil_actual():
        i = combo.current()
        return estado["perfiles"][i] if 0 <= i < len(estado["perfiles"]) else None

    def id_actual():
        """Versión de Minecraft del perfil elegido."""
        p = perfil_actual()
        return p["version"] if p else ""

    def refrescar_lista(manifiesto=None, seleccion=None):
        """Reconstruye la lista de perfiles (la versión sin instalar lleva '[+] ') y conserva el elegido."""
        if manifiesto:
            estado["manifiesto"] = manifiesto
        previa = seleccion or (perfil_actual() or {}).get("id") or cfg["perfil"]
        ps = listar_perfiles()
        estado["perfiles"] = ps
        conocidas = {v["id"] for v in (estado["manifiesto"] or {}).get("versions", [])}
        estado["no_inst"] = {p["version"] for p in ps if not esta_instalada(p["version"])
                             and (p["version"] in conocidas or not os.path.isfile(
                                 os.path.join(carpeta_versiones, p["version"], p["version"] + ".json")))}
        combo["values"] = [(PREFIJO_NO_INSTALADA if p["version"] in estado["no_inst"] else "")
                           + f'{p["nombre"]}  ({p["version"]})' for p in ps] + [TXT_NUEVO]
        idx = next((i for i, p in enumerate(ps) if p["id"] == previa), 0 if ps else None)
        if idx is None:
            combo.set("")
            estado["sel"] = None
        else:
            combo.current(idx)
            estado["sel"] = idx
            cfg["perfil"], cfg["version"] = ps[idx]["id"], ps[idx]["version"]
        aplicar_boton()

    def aplicar_boton():
        """Versión instalada => JUGAR; no instalada => DESCARGAR Y JUGAR (en el mismo lugar)."""
        if estado["inst"]:
            return
        vid = id_actual()
        instalada = not vid or vid not in estado["no_inst"]
        canvas.itemconfigure(win_jugar, state="normal" if instalada else "hidden")
        canvas.itemconfigure(win_descargar, state="hidden" if instalada else "normal")
        btn_editar.configure(state="normal" if perfil_actual() else "disabled")

    def al_elegir_perfil(_evento=None):
        if combo.current() == len(estado["perfiles"]):  # último ítem: «Crear nuevo perfil»
            if estado["sel"] is None:
                combo.set("")
            else:
                combo.current(estado["sel"])
            combo.selection_clear()
            dialogo_perfil(None)
            return
        estado["sel"] = combo.current()
        p = perfil_actual()
        if p:
            cfg["perfil"], cfg["version"] = p["id"], p["version"]
            guardar_config(cfg)
        aplicar_boton()
        combo.selection_clear()
    combo.bind("<<ComboboxSelected>>", al_elegir_perfil)

    # ----- ventanas auxiliares -----
    def ventana_modal(titulo, ancho, alto):
        top = tk.Toplevel(ventana)
        top.title(titulo)
        top.configure(bg="#142016")
        top.resizable(False, False)
        top.transient(ventana)
        x = ventana.winfo_x() + (W - ancho) // 2
        y = ventana.winfo_y() + (H - alto) // 2
        top.geometry(f"{ancho}x{alto}+{max(x, 0)}+{max(y, 0)}")
        try:
            top.iconbitmap(ruta_recurso("icono.ico"))
        except Exception:
            pass
        return top

    def abrir_modal(top):
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.focus_force()

    def dialogo_perfil(perfil):
        """Crear (perfil=None) o editar un perfil: nombre, versión (con filtros como el launcher original) y parámetros."""
        editar = perfil is not None
        top = ventana_modal("Editar perfil" if editar else "Crear nuevo perfil", 480, 470 if editar else 440)

        def etiqueta(y, s_):
            tk.Label(top, text=s_, font=("Segoe UI", 9, "bold"), bg="#142016", fg=C_GRIS).place(x=24, y=y)

        def campo(var, y):
            e = tk.Entry(top, textvariable=var, font=("Segoe UI", 12), bg=C_CAMPO, fg="white", insertbackground="white",
                         relief="flat", highlightthickness=1, highlightbackground=C_BORDE, highlightcolor=C_VERDE)
            e.place(x=24, y=y, width=432, height=34)
            return e

        etiqueta(16, "NOMBRE DEL PERFIL")
        var_nombre = tk.StringVar(value=perfil["nombre"] if editar else "")
        entrada = campo(var_nombre, 38)

        etiqueta(88, "VERSIÓN DE MINECRAFT")
        manif = estado["manifiesto"] or {}
        tipo_actual = next((v.get("type") for v in manif.get("versions", []) if editar and v["id"] == perfil["version"]),
                           "mods" if editar else "release")
        marcados = {k: tk.BooleanVar(value=(k in ("release", "mods") or k == tipo_actual)) for k, _n in TIPOS_FILTRO}
        elegida = [perfil["version"] if editar else None]
        ids_visibles = [[]]
        fila = tk.Frame(top, bg="#142016")
        fila.place(x=24, y=110, width=432, height=28)
        combo_v = ttk.Combobox(top, values=[], state="readonly", font=("Segoe UI", 11), style="Pipo.TCombobox")
        combo_v.place(x=24, y=146, width=432, height=34)

        def recargar():
            tipos = {k for k, v in marcados.items() if v.get()}
            ids = versiones_para_perfil(estado["manifiesto"], tipos)
            if editar and perfil["version"] not in ids:
                ids.insert(0, perfil["version"])  # la del perfil siempre se ve, aunque su filtro esté apagado
            ids_visibles[0] = ids
            conocidas = {v["id"] for v in manif.get("versions", [])}
            combo_v["values"] = [(PREFIJO_NO_INSTALADA if (i in conocidas and not esta_instalada(i)) else "") + i
                                 for i in ids]
            if elegida[0] not in ids:
                ultima = (manif.get("latest") or {}).get("release")
                elegida[0] = (next((i for i in ids if esta_instalada(i)), None) or (ultima if ultima in ids else None)
                              or (ids[0] if ids else None))
            if elegida[0] in ids:
                combo_v.current(ids.index(elegida[0]))
            else:
                combo_v.set("")

        def al_elegir_v(_e=None):
            i = combo_v.current()
            elegida[0] = ids_visibles[0][i] if 0 <= i < len(ids_visibles[0]) else None
            combo_v.selection_clear()
        combo_v.bind("<<ComboboxSelected>>", al_elegir_v)

        for k, nombre_f in TIPOS_FILTRO:
            tk.Checkbutton(fila, text=nombre_f, variable=marcados[k], indicatoron=False, command=recargar,
                           font=("Segoe UI", 8, "bold"), bg=C_CAMPO, fg="white", selectcolor="#3f7a2a",
                           activebackground="#2d4a2d", activeforeground="white", relief="flat", bd=0,
                           cursor="hand2", padx=8, pady=3, highlightthickness=1,
                           highlightbackground=C_BORDE).pack(side="left", padx=(0, 5))
        recargar()

        etiqueta(196, "PARÁMETROS DE LANZAMIENTO (OPCIONAL)")
        var_args = tk.StringVar(value=perfil["args"] if editar else "")
        campo(var_args, 218)
        tk.Label(top, text="Ej.: -Xmx6G -Dalgo=1 --width 1280 --height 720 --server mi.servidor.com\n"
                           "Los de Java (-X, -D, --add-opens…) van a la JVM; los demás, al juego.",
                 font=("Segoe UI", 8), bg="#142016", fg="#6f826f", justify="left").place(x=24, y=258)
        lbl_err = tk.Label(top, text="", font=("Segoe UI", 9), bg="#142016", fg="#e06c6c", wraplength=430, justify="left")
        lbl_err.place(x=24, y=298)

        def guardar_p():
            vid = elegida[0]
            if not vid:
                lbl_err.configure(text="Elegí una versión de la lista (probá activar más filtros).")
                return
            _j, _g, err = parsear_args(var_args.get())
            if err:
                lbl_err.configure(text=err)
                return
            nombre = " ".join(var_nombre.get().split()) or vid
            if editar and vid != perfil["version"] and not messagebox.askyesno(
                    "Cambiar versión", "Vas a cambiar la versión de este perfil.\n\nSus mods y mundos se conservan, "
                                       "pero pueden no ser compatibles con la versión nueva.\n\n¿Continuar?",
                    parent=top):
                return
            try:
                if editar:
                    actualizar_perfil(perfil["id"], nombre=nombre, version=vid, args=var_args.get().strip())
                    pid = perfil["id"]
                else:
                    pid = crear_perfil(nombre, vid, var_args.get())["id"]
            except (OSError, ValueError) as e:
                messagebox.showerror("Perfil", f"No se pudo guardar el perfil:\n{e}", parent=top)
                return
            cfg["perfil"], cfg["version"] = pid, vid
            guardar_config(cfg)
            top.destroy()
            refrescar_lista(seleccion=pid)

        def eliminar_p():
            mb = tam_bytes(ruta_perfil(perfil["id"])) / 1048576
            if not messagebox.askyesno(
                    "Eliminar perfil",
                    f"¿Eliminar el perfil «{perfil['nombre']}»?\n\nSe borra su carpeta de juego (mods, mundos, opciones y "
                    f"capturas): {mb:.0f} MB.\nNo se puede deshacer. La versión de Minecraft no se borra.",
                    icon="warning", default="no", parent=top):
                return
            try:
                eliminar_perfil(perfil["id"])
            except (OSError, ValueError) as e:
                messagebox.showerror("Perfil", f"No se pudo eliminar el perfil:\n{e}", parent=top)
                return
            if cfg["perfil"] == perfil["id"]:
                cfg["perfil"] = ""
            top.destroy()
            refrescar_lista()

        boton(top, "GUARDAR" if editar else "CREAR PERFIL", C_VERDE, C_VERDE_H, ("Segoe UI", 12, "bold"), guardar_p,
              fg="#0c1a0c").place(x=24, y=348, width=212, height=40)
        boton(top, "Cancelar", "#2a3d2a", "#3a5a3a", ("Segoe UI", 11), top.destroy).place(x=244, y=348, width=212, height=40)
        if editar:
            boton(top, "Eliminar perfil", "#6e2a2a", "#8e3a3a", ("Segoe UI", 9), eliminar_p).place(
                x=24, y=402, width=432, height=30)
        top.bind("<Return>", lambda _e: guardar_p())
        top.bind("<Escape>", lambda _e: top.destroy())
        abrir_modal(top)
        entrada.focus_set()

    # ----- cuenta Microsoft -----
    def poner_cara(ruta):
        try:
            ventana.cara = ImageTk.PhotoImage(Image.open(ruta).convert("RGBA").resize((26, 26), Image.NEAREST))
            canvas.itemconfigure(img_cara, image=ventana.cara)
        except Exception:
            canvas.itemconfigure(img_cara, image="")

    def mostrar_cuenta():
        """Con sesión: foto + gamertag. Sin sesión: «Sin sesión» (se juega offline)."""
        c = estado["cuenta"]
        if not c:
            canvas.itemconfigure(img_cara, state="hidden", image="")
            canvas.itemconfigure(txt_cuenta, text="")
            canvas.itemconfigure(caja_cuenta, state="hidden")
            canvas.itemconfigure(win_usuario, state="normal")
            cambiar_texto(lbl_cuenta, "NOMBRE (OFFLINE)")
            btn_login.configure(text="Iniciar sesión")
            return
        canvas.itemconfigure(win_usuario, state="hidden")
        canvas.itemconfigure(caja_cuenta, state="normal")
        cambiar_texto(lbl_cuenta, "CUENTA")
        canvas.itemconfigure(txt_cuenta, text=nombre_visible(c), fill="white", font=("Segoe UI", 11, "bold"))
        canvas.coords(txt_cuenta, 68, YC)
        canvas.itemconfigure(img_cara, state="normal", image="")
        btn_login.configure(text="Cerrar sesión")
        ruta = ruta_cara(c)
        if os.path.isfile(ruta):
            poner_cara(ruta)
            return
        r = {}

        def bajar():
            r["ruta"] = descargar_cara(c)
            r["fin"] = True
        threading.Thread(target=bajar, daemon=True).start()

        def esperar():
            if not r.get("fin"):
                ventana.after(200, esperar)
            elif r["ruta"] and estado["cuenta"] and estado["cuenta"]["uuid"] == c["uuid"]:
                poner_cara(r["ruta"])
        esperar()

    def alternar_sesion():
        if estado["cuenta"]:
            if messagebox.askyesno("Cerrar sesión", f"¿Cerrar la sesión de {nombre_visible(estado['cuenta'])}?\n\n"
                                   "Se borran los datos guardados de la cuenta. Podés volver a jugar sin cuenta "
                                   "(modo offline con el nombre que escribas) o iniciar sesión de nuevo."):
                borrar_cuenta()
                estado["cuenta"] = estado["sesion"] = None
                mostrar_cuenta()
        else:
            dialogo_sesion()

    def dialogo_sesion(al_terminar=None):
        top = ventana_modal("Iniciar sesión con Microsoft", 440, 350)
        cancelado = threading.Event()
        r = {"d": None, "ses": None, "err": None, "fin": False, "fase": "codigo"}
        tk.Label(top, text="INICIAR SESIÓN CON MICROSOFT", font=("Segoe UI", 12, "bold"), bg="#142016",
                 fg="white").pack(pady=(18, 4))
        lbl_info = tk.Label(top, text="Pidiendo el código a Microsoft…", font=("Segoe UI", 10), bg="#142016",
                            fg=C_GRIS, wraplength=390, justify="center")
        lbl_info.pack(pady=(0, 6))
        # El código va en una caja tipo «bloque de código» (se puede seleccionar) con su botón de copiar
        caja = tk.Frame(top, bg="#0b120b", highlightthickness=1, highlightbackground=C_BORDE)
        caja.pack(pady=(6, 4))
        var_codigo = tk.StringVar(value="")
        ent_codigo = tk.Entry(caja, textvariable=var_codigo, font=("Consolas", 26, "bold"), width=11, justify="center",
                              state="readonly", readonlybackground="#0b120b", fg=C_VERDE, relief="flat", bd=0,
                              highlightthickness=0)
        ent_codigo.pack(side="left", padx=(10, 6), pady=8)
        btn_copiar = boton(caja, "COPIAR", "#2a3d2a", "#3a5a3a", ("Segoe UI", 10, "bold"), lambda: copiar_codigo())
        btn_copiar.pack(side="left", padx=(0, 10), ipadx=8, ipady=6)
        btn_copiar.configure(state="disabled")

        def copiar_codigo():
            cod = var_codigo.get()
            if not cod:
                return
            try:
                top.clipboard_clear()
                top.clipboard_append(cod)
                top.update()  # que el portapapeles quede disponible
            except tk.TclError:
                pass
            btn_copiar.configure(text="¡COPIADO!")
            top.after(1500, lambda: btn_copiar.winfo_exists() and btn_copiar.configure(text="COPIAR"))
        lbl_pasos = tk.Label(top, text="", font=("Segoe UI", 9), bg="#142016", fg=C_GRIS, wraplength=390, justify="center")
        lbl_pasos.pack()
        fila_b = tk.Frame(top, bg="#142016")
        fila_b.pack(pady=(14, 0))
        btn_abrir = boton(fila_b, "ABRIR PÁGINA", C_VERDE, C_VERDE_H, ("Segoe UI", 11, "bold"), lambda: abrir_pagina(),
                          fg="#0c1a0c")
        btn_abrir.pack(side="left", padx=5, ipadx=8, ipady=5)
        btn_abrir.configure(state="disabled")
        btn_canc = boton(fila_b, "Cancelar", "#2a3d2a", "#3a5a3a", ("Segoe UI", 10), lambda: cerrar())
        btn_canc.pack(side="left", padx=5, ipadx=8, ipady=5)

        def abrir_pagina():
            d = r["d"]
            if d:
                copiar_codigo()
                abrir_url(d.get("verification_uri") or "https://www.microsoft.com/link")

        def cerrar():
            cancelado.set()
            top.destroy()

        def hilo():
            try:
                r["d"] = ms_pedir_codigo()
                tokens = ms_esperar_token(r["d"], cancelado)
                r["fase"] = "cuenta"
                ses = completar_sesion(tokens)
                r["ses"] = ses
                r["cara"] = descargar_cara(ses)
            except ErrorMicrosoft as e:
                r["err"] = str(e)
            except Exception as e:
                r["err"] = f"Error inesperado: {e}"
            r["fin"] = True
        threading.Thread(target=hilo, daemon=True).start()

        def sondear():
            if not top.winfo_exists():
                return
            d = r["d"]
            if d and not var_codigo.get() and not r["fin"]:
                var_codigo.set(d["user_code"])
                btn_copiar.configure(state="normal")
                lbl_info.configure(text="Abrí la página, escribí este código e iniciá sesión con tu cuenta de Minecraft.")
                lbl_pasos.configure(text="Copiá el código, pegalo en la página de Microsoft («Abrir página» también lo copia).\nEsta ventana espera hasta que termines.")
                btn_abrir.configure(state="normal")
            if r["fase"] == "cuenta" and not r["fin"]:
                var_codigo.set("")
                btn_copiar.configure(state="disabled")
                btn_abrir.configure(state="disabled")
                lbl_info.configure(text="Verificando tu cuenta de Minecraft…")
                lbl_pasos.configure(text="")
            if not r["fin"]:
                top.after(250, sondear)
                return
            if r["err"]:
                if not cancelado.is_set():
                    messagebox.showerror("Iniciar sesión", r["err"], parent=top)
                    top.destroy()
                return
            ses = r["ses"]
            estado["cuenta"] = datos_cuenta(ses)
            estado["sesion"] = ses
            top.destroy()
            mostrar_cuenta()
            if al_terminar:
                al_terminar()
        sondear()
        top.protocol("WM_DELETE_WINDOW", cerrar)
        abrir_modal(top)

    # ----- trabajos en segundo plano con progreso dentro de la ventana -----
    def bloquear(si):
        entry_usuario.configure(state="disabled" if si else "normal")
        combo.configure(state="disabled" if si else "readonly")
        btn_cfg.configure(state="disabled" if si else "normal")
        btn_login.configure(state="disabled" if si else "normal")
        if si:
            btn_editar.configure(state="disabled")
        canvas.itemconfigure(win_barra, state="normal" if si else "hidden")
        canvas.itemconfigure(win_cancelar, state="normal" if si else "hidden")
        if si:
            canvas.itemconfigure(win_jugar, state="hidden")
            canvas.itemconfigure(win_descargar, state="hidden")
            cambiar_texto(linea, "")
            btn_cancelar.configure(state="normal", text="✕")
        else:
            barra.stop()
            cambiar_texto(linea, estado["aviso"])
            aplicar_boton()

    def pedir_cancelar():
        if estado["inst"] and messagebox.askyesno(
                "Cancelar", "¿Cancelar la descarga?\n\nLo ya descargado se conserva y se retoma después."):
            btn_cancelar.configure(state="disabled", text="…")
            estado["inst"].cancelar()

    def correr_trabajo(trabajo, al_terminar):
        """Corre trabajo(instalador) en un hilo mostrando el progreso. Al terminar llama a
        al_terminar(salida) con salida = {'res'} | {'cancelado'} | {'error'}."""
        inst = Instalador()
        estado["inst"] = inst
        bloquear(True)
        salida, modo = {}, [None]

        def correr():
            try:
                salida["res"] = trabajo(inst)
            except Cancelado:
                salida["cancelado"] = True
            except Exception as e:
                inst._log(traceback.format_exc())
                salida["error"] = e
            finally:
                salida["fin"] = True
        threading.Thread(target=correr, daemon=True).start()

        def sondear():
            s = inst.snapshot()
            cambiar_texto(linea, s["titulo"] + (("  ·  " + s["detalle"]) if s["detalle"] else ""))
            if s["frac"] is None:
                if modo[0] != "ind":
                    barra.configure(mode="indeterminate")
                    barra.start(15)
                    modo[0] = "ind"
            else:
                if modo[0] != "det":
                    barra.stop()
                    barra.configure(mode="determinate")
                    modo[0] = "det"
                barra["value"] = s["frac"] * 100
            if not salida.get("fin"):
                ventana.after(100, sondear)
                return
            estado["inst"] = None
            bloquear(False)
            if estado["cerrando"]:
                ventana.destroy()
                return
            al_terminar(salida)
        sondear()

    def problema(salida, reintentar, aviso_cancelado=None):
        """True si el trabajo se canceló o falló (ya se le avisó al usuario)."""
        if salida.get("cancelado"):
            if aviso_cancelado:
                messagebox.showinfo("Cancelado", aviso_cancelado)
            return True
        if "error" in salida:
            e = salida["error"]
            msg = ("No se pudo conectar con los servidores de Mojang.\nRevisá tu conexión a internet."
                   if isinstance(e, ErrorRed) else f"Ocurrió un error:\n{e}")
            if messagebox.askretrycancel("No se pudo completar", msg + "\n\n¿Reintentar?"):
                reintentar()
            return True
        errores = salida["res"]["errores"]
        if errores:
            if messagebox.askretrycancel(
                    "Descarga incompleta",
                    f"No se pudieron descargar {len(errores)} archivos.\nRevisá tu conexión a internet.\n\n¿Reintentar?"):
                reintentar()
            return True
        return False

    def aplicar_resultado(salida, seleccion=None):
        m = (salida.get("res") or {}).get("manifiesto")
        refrescar_lista(m, seleccion)
        if m:
            estado["aviso"] = ""
            cambiar_texto(linea, "")

    # ----- descargar una versión (y lo que le falte) y ejecutarla -----
    def descargar_y_lanzar():
        perfil = perfil_actual()
        vid = id_actual()
        if not perfil:
            messagebox.showwarning("Atención", "Elegí un perfil o creá uno con «Crear nuevo perfil».")
            return
        if not estado["cuenta"]:
            if not entry_usuario.get().strip():
                messagebox.showwarning("Atención", "Escribí un nombre para jugar sin sesión.")
                return
            cfg["usuario"] = entry_usuario.get().strip()
        cfg["perfil"], cfg["version"] = perfil["id"], vid
        guardar_config(cfg)

        def fin(salida):
            aplicar_resultado(salida, perfil["id"])
            if problema(salida, descargar_y_lanzar):
                return
            lanzar(reparado=True)
        correr_trabajo(lambda inst: inst.ejecutar(vids=[vid], estricto=True), fin)

    # ----- lanzar -----
    def lanzar(reparado=False):
        """Con cuenta Microsoft primero renueva la sesión (en segundo plano); sin cuenta juega en modo offline."""
        perfil = perfil_actual()
        if not perfil:
            messagebox.showwarning("Atención", "Elegí un perfil o creá uno con «Crear nuevo perfil».")
            return
        if not estado["cuenta"]:
            _lanzar(reparado, None)
            return
        ses = estado["sesion"]
        if ses and ses["expira"] - time.time() > 600:  # el token de Minecraft dura 24 h: se reutiliza
            _lanzar(reparado, ses)
            return
        canvas.itemconfigure(win_jugar, state="hidden")
        canvas.itemconfigure(win_descargar, state="hidden")
        cambiar_texto(linea, "Verificando tu cuenta de Microsoft…")
        r = {}

        def hilo():
            try:
                r["ses"] = sesion_guardada()
            except ErrorMicrosoft as e:
                r["err"] = e
            except Exception as e:
                r["err"] = ErrorMicrosoft(f"Error inesperado: {e}")
            r["fin"] = True
        threading.Thread(target=hilo, daemon=True).start()

        def esperar():
            if not r.get("fin"):
                ventana.after(150, esperar)
                return
            cambiar_texto(linea, estado["aviso"])
            aplicar_boton()
            if "ses" in r:
                estado["sesion"] = r["ses"]
                estado["cuenta"] = datos_cuenta(r["ses"])
                mostrar_cuenta()
                _lanzar(reparado, r["ses"])
                return
            e = r["err"]
            if e.renovar:
                if messagebox.askyesno("Sesión vencida", f"{e}\n\n¿Iniciar sesión ahora?"):
                    dialogo_sesion(lambda: lanzar(reparado))
            else:
                c = estado["cuenta"]
                if messagebox.askyesno("Sin verificar la cuenta",
                                       f"No se pudo verificar la cuenta:\n{e}\n\n¿Jugar sin conexión como "
                                       f"«{c['nombre']}»?\n(No vas a poder entrar a servidores con cuenta premium.)"):
                    _lanzar(reparado, None, offline_como=c["nombre"])
        esperar()

    def _lanzar(reparado, sesion, offline_como=None):
        perfil = perfil_actual()
        vid = perfil["version"]
        # Con cuenta el juego usa el nombre de Minecraft; el gamertag es solo para mostrar. Sin cuenta: nick offline fijo
        usuario = sesion["nombre"] if sesion else (offline_como or entry_usuario.get().strip())
        if not usuario:
            messagebox.showwarning("Atención", "Escribí un nombre para jugar sin sesión.")
            return
        if vid in estado["no_inst"]:  # no debería pasar (el botón está oculto), pero por las dudas
            descargar_y_lanzar()
            return
        ram = max(1, min(cfg["ram"], ram_max))
        # Con cuenta: UUID real de Mojang. Sin cuenta: UUID de modo offline (otro nick => otro UUID)
        uuid_jugador = sesion["uuid"].replace("-", "") if sesion else uuid_offline(usuario)
        token = sesion["token"] if sesion else None
        if not sesion and not offline_como:
            cfg["usuario"] = usuario  # el nick offline se recuerda para la próxima vez
        cfg["perfil"], cfg["version"] = perfil["id"], vid
        guardar_config(cfg)

        registro = None
        if cfg["logs"]:
            try:
                registro = Registro()
            except OSError:
                registro = None  # si no se puede escribir el log, se juega igual

        def log(msg, nivel="INFO"):
            if registro:
                registro.info(msg, nivel)

        def cerrar_log():
            if registro:
                registro.cerrar()

        try:
            log(f"PipoLauncher | Windows {platform.version()} | Python {platform.python_version()}")
            log(f"Usuario: {usuario} | UUID: {uuid_jugador} | Cuenta Microsoft: {'sí' if sesion else 'no (offline)'} | "
                f"Perfil: {perfil['nombre']} | Versión: {vid} | RAM: {ram} GB "
                f"(PC: {total_ram} GB, máximo permitido: {ram_max} GB)")
            # Carpeta de juego propia del perfil (mods, config, mundos, opciones...)
            dir_juego = None
            if True:
                try:
                    if es_version_legacy(vid):
                        log("Versión anterior a 1.6: usa .minecraft directamente (sus sonidos están en .minecraft\\resources)")
                    else:
                        perfil, dir_juego, nuevo = asegurar_perfil(perfil["id"])
                        if nuevo:
                            log(f"Perfil creado: {dir_juego} | importado: {', '.join(perfil['importado']) or '-'}"
                                + (f" | omitido por tamaño o error: {', '.join(perfil['omitidos'])}"
                                   if perfil["omitidos"] else ""))
                            hay = mundos_existentes()
                            if hay:
                                if messagebox.askyesno(
                                        f"Perfil {perfil['nombre']}",
                                        f"Se creó la carpeta de juego del perfil «{perfil['nombre']}».\n\n"
                                        f"Encontramos mundos guardados en .minecraft\\saves ({hay[1]:.0f} MB).\n"
                                        "¿Copiarlos a este perfil?\n\n"
                                        "• Sí: se copian (los originales no se tocan).\n"
                                        "• No: el perfil empieza sin mundos; podés copiarlos después desde "
                                        "Configuración → «Abrir carpeta del perfil»."):
                                    ventana.configure(cursor="watch")
                                    ventana.update()
                                    ok = importar_mundos(dir_juego)
                                    ventana.configure(cursor="")
                                    actualizar_perfil(perfil["id"], mundos=ok)
                                    log("Mundos copiados al perfil" if ok else "No se pudieron copiar todos los mundos",
                                        "INFO" if ok else "WARN")
                                    if not ok:
                                        messagebox.showwarning(
                                            "Mundos", "No se pudieron copiar todos los mundos.\nSiguen intactos en "
                                                      ".minecraft\\saves; podés copiarlos a mano a la carpeta del perfil.")
                                else:
                                    actualizar_perfil(perfil["id"], mundos=False)
                        else:
                            log(f"Perfil: {dir_juego}")
                except OSError as e:
                    dir_juego = None
                    log(f"No se pudo preparar el perfil ({e}); se usa .minecraft", "WARN")
            try:
                cmd, faltan = construir_comando(vid, usuario, ram, uuid_jugador, con_logs=registro is not None,
                                                dir_juego=dir_juego, args_extra=perfil["args"], sesion=sesion)
            except JavaNoEncontrado as e:
                log(str(e), "WARN")
                if not reparado:
                    cerrar_log()
                    if messagebox.askyesno("Falta Java", f"Esta versión necesita Java {e.mayor} y todavía no está "
                                                         "instalado.\n\n¿Descargarlo ahora y jugar?"):
                        descargar_y_lanzar()
                    return
                raise
            log(f"Java: {cmd[0]}")
            for f in faltan:
                log(f"Falta el archivo: {f}", "WARN")
            if faltan:
                detalle = f"A la versión {vid} le faltan {len(faltan)} archivos, por ejemplo:\n{faltan[0]}\n\n"
                if not reparado:
                    r = messagebox.askyesnocancel(
                        "Archivos faltantes",
                        detalle + "¿Descargarlos ahora?\n\nSí = descargar y jugar\nNo = lanzar de todos modos\n"
                                  "Cancelar = volver")
                    if r is None:
                        log("Lanzamiento cancelado por el usuario")
                        cerrar_log()
                        return
                    if r:
                        log("El usuario eligió descargar los archivos faltantes")
                        cerrar_log()
                        descargar_y_lanzar()
                        return
                elif not messagebox.askyesno("Archivos faltantes",
                                             detalle + "Siguen faltando tras la descarga. ¿Lanzar de todos modos?"):
                    log("Lanzamiento cancelado por el usuario")
                    cerrar_log()
                    return
            log("Comando: " + ocultar_secretos(subprocess.list2cmdline(cmd), token))  # el token nunca va al log
            proc, hilo = iniciar(cmd, registro, cwd=dir_juego)
            log("Minecraft iniciado")
            if dir_juego:
                try:
                    registrar_uso(perfil["id"])
                except OSError:
                    pass
        except Exception as e:
            log(traceback.format_exc(), "ERROR")
            cerrar_log()
            messagebox.showerror("Error al lanzar", str(e))
            return

        if registro is None:  # sin logs: el launcher se cierra y el juego sigue solo
            ventana.destroy()
            return

        # Con logs: el launcher queda oculto leyendo la salida del juego y se cierra cuando el juego termina
        ventana.withdraw()

        def vigilar():
            codigo = proc.poll()
            if codigo is None:
                ventana.after(1000, vigilar)
                return
            if hilo:
                hilo.join(timeout=5)
            registro.info(f"Minecraft se cerró (código de salida: {codigo})")
            registro.cerrar()
            ventana.destroy()
        vigilar()

    # ----- preparación inicial y verificación -----
    def preparar():
        """Primer inicio: solo lo necesario para jugar (Java). Las versiones se bajan desde la lista."""
        primera = not cfg["instalado"]

        def fin(salida):
            aplicar_resultado(salida)
            if problema(salida, preparar,
                        "No se completó la preparación.\n\nSe reintentará la próxima vez que abras el launcher "
                        "(mientras tanto, cada versión baja su propio Java al descargarla)."):
                return
            res = salida["res"]
            jl = res.get("java_local")
            cfg["instalado"] = True
            cfg["java_local"] = bool(jl)  # si falló, se reintenta al abrir el launcher la próxima vez
            guardar_config(cfg)
            java_txt = ", ".join(str(j) for j in res["java"]) or "-"
            if jl and jl["origen"] == "instalado":
                java_pc = (f"  •  Java {jl['mayor']} instalado en tu PC (para instalar Forge y otros mods).\n"
                           "     Si vas a ejecutar un instalador, abrilo desde una ventana nueva.\n")
            elif jl:
                java_pc = f"  •  Java detectado en tu PC (versión {jl['mayor']}): no hizo falta instalar otro.\n"
            else:
                java_pc = ("  •  No se pudo instalar Java en tu PC (Forge lo necesita). "
                           "Se reintentará al abrir el launcher.\n")
            if primera:
                messagebox.showinfo(
                    "¡Bienvenido a PipoLauncher!",
                    "¡Bienvenido! Ya está lo necesario para jugar.\n\n"
                    f"  •  Java del juego: {java_txt}\n{java_pc}\n"
                    "La lista muestra todas las versiones de Minecraft. Las que tienen [+] todavía no están "
                    "instaladas: al elegirlas aparece «Descargar y jugar».")
            elif jl and jl["origen"] == "instalado":
                messagebox.showinfo("Java instalado", java_pc.replace("  •  ", "").strip())
        correr_trabajo(lambda inst: inst.ejecutar(java_extra=JAVA_PRECARGADOS, java_local=True), fin)

    def verificar_archivos():
        """Revisa las versiones instaladas (librerías, recursos y Java), repara lo que falte y actualiza la lista."""
        vids = [v for v in listar_versiones() if v not in estado["no_inst"]]

        def fin(salida):
            aplicar_resultado(salida)
            if problema(salida, verificar_archivos):
                return
            res = salida["res"]
            if res["descargados"]:
                messagebox.showinfo("Archivos verificados",
                                    f"Se descargaron o repararon {res['descargados']} archivos ({res['mb']} MB).")
            else:
                messagebox.showinfo("Archivos verificados", "Todo está al día: no faltaba ningún archivo.")
        correr_trabajo(lambda inst: inst.ejecutar(vids=vids, java_extra=JAVA_PRECARGADOS), fin)

    def refrescar_en_segundo_plano():
        """Trae el manifiesto actual de Mojang: así aparecen solas las versiones nuevas que salgan."""
        r = {}

        def hilo():
            r["m"] = pedir_manifiesto()
            r["fin"] = True
        threading.Thread(target=hilo, daemon=True).start()

        def sondear():
            if not r.get("fin"):
                ventana.after(150, sondear)
                return
            if r["m"]:
                estado["aviso"] = ""
                if not estado["inst"]:
                    refrescar_lista(r["m"])
                    cambiar_texto(linea, "")
                else:
                    estado["manifiesto"] = r["m"]
            else:
                estado["aviso"] = ("Sin conexión: se muestra la última lista conocida." if estado["manifiesto"]
                                   else "Sin conexión: solo se ven las versiones instaladas.")
                if not estado["inst"]:
                    cambiar_texto(linea, estado["aviso"])
        sondear()

    # ----- configuración (en la misma ventana, encima de la principal) -----
    panel_cfg = tk.Canvas(ventana, width=W, height=H, highlightthickness=0, bg="#0c160c")
    panel_cfg.create_image(0, 0, image=ventana.fondo_config, anchor="nw")
    DY = (H - 450) // 2   # el diseño original era de 800x450: se baja todo para centrarlo
    CX1, CX2, CY1, CY2 = W // 2 - 180, W // 2 + 180, 44 + DY, 420 + DY
    panel_cfg.create_rectangle(CX1, CY1, CX2, CY2, fill="#142016", outline=C_BORDE, width=2)
    panel_cfg.create_rectangle(CX1, CY1, CX2, CY1 + 4, fill=C_VERDE, outline=C_VERDE)
    var_ram = tk.StringVar()
    var_logs = tk.BooleanVar()
    en_config = [False]

    def texto_p(yy, s, fuente, color="white"):
        panel_cfg.create_text(W // 2, yy + DY, text=s, font=fuente, fill=color)

    texto_p(74, "CONFIGURACIÓN", ("Segoe UI", 14, "bold"))
    texto_p(108, "Memoria RAM (GB)", ("Segoe UI", 10, "bold"), C_GRIS)
    spin = tk.Spinbox(panel_cfg, from_=1, to=ram_max, textvariable=var_ram, font=("Segoe UI", 13),
                      justify="center", bg=C_CAMPO, fg="white", insertbackground="white",
                      buttonbackground="#2d4a2d", relief="flat", highlightthickness=1,
                      highlightbackground=C_BORDE, highlightcolor=C_VERDE)
    panel_cfg.create_window(W // 2, 136 + DY, window=spin, width=90, height=32)
    texto_p(163, f"Tu PC tiene {total_ram} GB · máximo permitido: {ram_max} GB", ("Segoe UI", 8), "#6f826f")
    chk = tk.Checkbutton(panel_cfg, text="Generar logs (Launcher + Juego)", variable=var_logs,
                         font=("Segoe UI", 10), bg="#142016", fg="white", activebackground="#142016",
                         activeforeground="white", selectcolor=C_CAMPO, cursor="hand2", bd=0,
                         highlightthickness=0)
    panel_cfg.create_window(W // 2, 192 + DY, window=chk)
    texto_p(213, "Se guardan en .minecraft\\Pipolauncher\\logs", ("Segoe UI", 8), "#6f826f")
    texto_p(243, "Cada perfil tiene su propia carpeta de juego", ("Segoe UI", 9, "bold"), C_GRIS)
    texto_p(264, "Mods, config, mundos y opciones separados · se editan con ✎", ("Segoe UI", 8), "#6f826f")

    def aplicar():
        try:
            v = int(var_ram.get())
            if not 1 <= v <= ram_max:
                raise ValueError
        except ValueError:
            messagebox.showwarning("RAM", f"Ingresá un número entre 1 y {ram_max}.")
            return False
        cfg["ram"] = v
        cfg["logs"] = bool(var_logs.get())
        guardar_config(cfg)
        return True

    def guardar():
        if aplicar():
            ocultar_config()

    def verificar():
        if aplicar():
            ocultar_config()
            verificar_archivos()

    def abrir_perfil():
        """Abre en el Explorador la carpeta de juego del perfil elegido (.minecraft si es anterior a 1.6)."""
        perfil = perfil_actual()
        try:
            if perfil and not es_version_legacy(perfil["version"]):
                ruta = asegurar_perfil(perfil["id"])[1]
            else:
                ruta = carpeta_minecraft
            if os.name == "nt":
                os.startfile(ruta)
            else:
                subprocess.Popen(["xdg-open", ruta])
        except Exception as e:
            messagebox.showerror("Carpeta del perfil", f"No se pudo abrir la carpeta:\n{e}")

    panel_cfg.create_window(W // 2, 306 + DY, width=220, height=40,
                            window=boton(panel_cfg, "GUARDAR", C_VERDE, C_VERDE_H, ("Segoe UI", 12, "bold"),
                                         guardar, fg="#0c1a0c"))
    panel_cfg.create_window(W // 2, 348 + DY, width=220, height=30,
                            window=boton(panel_cfg, "Abrir carpeta del perfil", "#2a3d2a", "#3a5a3a",
                                         ("Segoe UI", 10), abrir_perfil))
    panel_cfg.create_window(W // 2, 386 + DY, width=220, height=30,
                            window=boton(panel_cfg, "Verificar archivos", "#2a3d2a", "#3a5a3a",
                                         ("Segoe UI", 10), verificar))

    def mostrar_config():
        var_ram.set(str(cfg["ram"]))
        var_logs.set(cfg["logs"])
        panel_cfg.place(x=0, y=0)
        en_config[0] = True
        btn_cfg.configure(text="⌂")  # casa: vuelve a la pantalla principal sin guardar
        btn_cfg.lift()

    def ocultar_config():
        panel_cfg.place_forget()
        en_config[0] = False
        btn_cfg.configure(text="⚙")

    def alternar_config():
        if en_config[0]:
            ocultar_config()
        else:
            mostrar_config()

    def al_cerrar():
        inst = estado["inst"]
        if inst is None:
            ventana.destroy()
        elif messagebox.askyesno("Salir", "Hay una descarga en curso. ¿Cancelarla y salir?"):
            estado["cerrando"] = True
            btn_cancelar.configure(state="disabled", text="…")
            inst.cancelar()
    ventana.protocol("WM_DELETE_WINDOW", al_cerrar)

    # ----- aviso de actualización del launcher -----
    def mostrar_actualizacion(info, al_terminar=None):
        """Ventana de actualización. 'al_terminar' se llama cuando se cierra SIN actualizar (más tarde)."""
        top = tk.Toplevel(ventana)
        top.title("Actualización disponible")
        top.configure(bg="#142016")
        top.resizable(False, False)
        try:
            top.iconbitmap(ruta_recurso("icono.ico"))
        except Exception:
            pass
        AW, AH = 460, 430
        top.geometry(f"{AW}x{AH}+{ventana.winfo_x() + (W - AW) // 2}+{ventana.winfo_y() + (H - AH) // 2}")
        top.transient(ventana)
        cv = tk.Canvas(top, width=AW, height=AH, highlightthickness=0, bg="#142016")
        cv.pack()
        cv.create_rectangle(0, 0, AW, 4, fill=C_VERDE, outline=C_VERDE)
        cv.create_text(AW // 2, 40, text="ACTUALIZACIÓN DISPONIBLE", font=("Segoe UI", 15, "bold"), fill="white")
        cv.create_text(AW // 2, 72, text=f"v{VERSION}   →   {info['tag']}" + ("  (pre-release)" if info.get("pre") else ""),
                       font=("Segoe UI", 12, "bold"), fill=C_VERDE)
        cv.create_text(AW // 2, 100, text="Hay una nueva versión de PipoLauncher.", font=("Segoe UI", 9),
                       fill=C_GRIS)

        caja = tk.Text(cv, font=("Segoe UI", 9), bg=C_CAMPO, fg="white", relief="flat", wrap="word",
                       highlightthickness=1, highlightbackground=C_BORDE, padx=10, pady=8, cursor="arrow")
        caja.insert("1.0", "Novedades:\n" + (info["notas"] or "Sin notas para esta versión."))
        caja.configure(state="disabled")
        cv.create_window(AW // 2, 192, window=caja, width=400, height=134)

        msg = cv.create_text(AW // 2, 286, text="", font=("Segoe UI", 9, "bold"), fill=C_GRIS, width=400)
        barra = ttk.Progressbar(cv, style="Pipo.Horizontal.TProgressbar", mode="determinate", maximum=100)
        id_barra = cv.create_window(AW // 2, 312, window=barra, width=400, height=14, state="hidden")

        auto = puede_autoactualizar(info)
        d = {"ocupado": False, "cancelar": threading.Event(), "p": {"hecho": 0, "total": 0, "fin": False,
                                                                     "error": None, "ruta": None}}

        def cerrar():
            try:
                top.grab_release()
            except tk.TclError:
                pass
            top.destroy()
            if al_terminar:
                al_terminar()

        def mas_tarde():
            if d["ocupado"]:  # descargando: el botón pasa a ser «Cancelar»
                d["cancelar"].set()
                btn_tarde.configure(state="disabled", text="Cancelando…")
            else:
                cerrar()

        def volver_a_inicio(texto_msg="", color=C_GRIS):
            d["ocupado"] = False
            cv.itemconfigure(id_barra, state="hidden")
            cv.itemconfigure(msg, text=texto_msg, fill=color)
            btn_act.configure(state="normal")
            btn_tarde.configure(state="normal", text="Quizás más tarde")

        def sondear():
            if not top.winfo_exists():
                return
            p = d["p"]
            if p["total"]:
                barra["value"] = p["hecho"] * 100 / p["total"]
                cv.itemconfigure(msg, text=f"Descargando… {p['hecho'] / 1048576:.1f} / "
                                           f"{p['total'] / 1048576:.1f} MB", fill=C_GRIS)
            if not p["fin"]:
                top.after(100, sondear)
                return
            if p["error"] == "cancelado":
                volver_a_inicio("Descarga cancelada.")
            elif p["error"]:
                volver_a_inicio("No se pudo actualizar: " + p["error"], "#e07070")
                btn_act.configure(text="REINTENTAR")
            else:
                cv.itemconfigure(msg, text="Instalando… el launcher se va a reiniciar solo.", fill=C_VERDE)
                try:
                    aplicar_actualizacion(p["ruta"])
                except Exception as e:
                    volver_a_inicio(f"No se pudo instalar: {e}", "#e07070")
                    btn_act.configure(text="REINTENTAR")
                    return
                top.after(400, ventana.destroy)

        def trabajo():
            p = d["p"]
            try:
                p["ruta"] = descargar_actualizacion(info, lambda h, t: p.update(hecho=h, total=t), d["cancelar"])
            except InterruptedError:
                p["error"] = "cancelado"
            except Exception as e:
                p["error"] = str(e) or e.__class__.__name__
            p["fin"] = True

        def actualizar():
            if not auto:  # .py, carpeta sin permiso o release sin .exe: se abre la página de descarga
                webbrowser.open(info["pagina"])
                cerrar()
                return
            if estado["inst"] is not None:
                messagebox.showwarning("Descarga en curso", "Hay una descarga del juego en curso.\n"
                                       "Esperá a que termine para actualizar el launcher.", parent=top)
                return
            d["ocupado"] = True
            d["cancelar"].clear()
            d["p"].update(hecho=0, total=0, fin=False, error=None, ruta=None)
            btn_act.configure(state="disabled")
            btn_tarde.configure(text="Cancelar")
            barra["value"] = 0
            cv.itemconfigure(id_barra, state="normal")
            cv.itemconfigure(msg, text="Conectando…", fill=C_GRIS)
            threading.Thread(target=trabajo, daemon=True).start()
            sondear()

        btn_act = boton(cv, "ACTUALIZAR AHORA" if auto else "ABRIR DESCARGA", C_VERDE, C_VERDE_H,
                        ("Segoe UI", 12, "bold"), actualizar, fg="#0c1a0c")
        cv.create_window(AW // 2, 358, width=260, height=40, window=btn_act)
        btn_tarde = boton(cv, "Quizás más tarde", "#2a3d2a", "#3a5a3a", ("Segoe UI", 10), mas_tarde)
        cv.create_window(AW // 2, 404, width=260, height=30, window=btn_tarde)
        top.protocol("WM_DELETE_WINDOW", mas_tarde)
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.focus_force()

    def arrancar():
        """Lo que antes corría al abrir: ahora va DESPUÉS de revisar (y, si corresponde, ofrecer) la actualización."""
        mostrar_cuenta()
        refrescar_lista()
        if not cfg["instalado"] or not cfg["java_local"]:  # 2º caso: instalaciones sin revisar el Java de la PC
            ventana.after(300, preparar)
        else:
            refrescar_en_segundo_plano()

    # ----- arranque: antes de mostrar el launcher se revisa el repositorio -----
    # Mientras tanto solo se ve una ventanita «Buscando actualizaciones…». Si hay una versión más nueva se muestra
    # el aviso de actualización (Actualizar ahora / Quizás más tarde) y recién después se habilita el launcher.
    splash = tk.Toplevel(ventana)
    splash.overrideredirect(True)
    splash.configure(bg=C_BORDE)
    SW, SH = 360, 120
    splash.geometry(f"{SW}x{SH}+{(ventana.winfo_screenwidth() - SW) // 2}+{(ventana.winfo_screenheight() - SH) // 2}")
    interior = tk.Frame(splash, bg="#142016")
    interior.pack(fill="both", expand=True, padx=2, pady=2)
    tk.Label(interior, text="PIPO LAUNCHER", font=("Segoe UI", 14, "bold"), bg="#142016", fg="white").pack(pady=(18, 0))
    tk.Label(interior, text="Buscando actualizaciones…", font=("Segoe UI", 10), bg="#142016",
             fg=C_GRIS).pack(pady=(2, 8))
    barra_splash = ttk.Progressbar(interior, style="Pipo.Horizontal.TProgressbar", mode="indeterminate", length=280)
    barra_splash.pack()
    barra_splash.start(12)
    splash.attributes("-topmost", True)
    splash.lift()

    hallazgo = {"info": None, "listo": False}

    def revisar_actualizacion():
        try:
            hallazgo["info"] = buscar_actualizacion()
        finally:
            hallazgo["listo"] = True

    def terminar_revision():
        if not hallazgo["listo"]:
            ventana.after(100, terminar_revision)
            return
        barra_splash.stop()
        splash.destroy()
        ventana.deiconify()
        ventana.update_idletasks()
        if hallazgo["info"]:
            mostrar_actualizacion(hallazgo["info"], arrancar)
        else:
            arrancar()

    threading.Thread(target=revisar_actualizacion, daemon=True).start()
    ventana.after(100, terminar_revision)

    ventana.mainloop()


if __name__ == "__main__":
    main()