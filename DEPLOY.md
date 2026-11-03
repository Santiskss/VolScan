# Puesta en producción de VolScan

Objetivo: una URL pública para los jueces del Meta Global AI Developer Hackathon, con la IA respondiendo
con **Meta Muse Glimmer 30B** (pesos abiertos). Todo lo de abajo está probado salvo los dos `modal deploy`,
que necesitan vuestra cuenta.

## Qué hay

| Pieza | Archivo | Qué hace |
|---|---|---|
| Imagen de producción | `Dockerfile` | Compila la web (Vite) y sirve API + UI con uvicorn en el puerto `$PORT` (8200). Arranca en modo demo pública. |
| Modelo en GPU | `deploy/modal_glimmer.py` | Glimmer 30B con llama.cpp en una L40S de Modal, API compatible OpenAI, protegida con clave. Se apaga tras 10 min sin uso. |
| Web en Modal | `deploy/modal_app.py` | La misma imagen Docker desplegada en Modal, siempre encendida. |

Modo demo pública (`VOLSCAN_PUBLIC_DEMO=on`, por defecto en la imagen): cualquiera entra sin cuenta con rol
`tecnico` (agente, informes, exportaciones), pero no puede administrar usuarios ni cambiar el modelo o su URL.

Usuario del equipo: con `VOLSCAN_AUTH=on` además, los visitantes siguen entrando como "Demo pública" y el
equipo pulsa **Entrar** para iniciar sesión como admin. El usuario `tephra` (admin) ya está creado: la
contraseña y la línea `VOLSCAN_USERS_JSON=…` lista para pegar están en `config/PRODUCCION-credenciales.txt`
(fuera de git). Para crear otro: `python -m volscan.security add-user NOMBRE admin` y copiad `config/users.json`.

## Opción A · Todo en Modal (recomendada, ~20 min)

Modal da 30 $/mes gratis al crear la cuenta; si os llegan los 100 $ del hackathon, mejor.

```bash
pip install modal && modal setup                       # abre el navegador para iniciar sesión

# 1. Modelo
KEY=$(openssl rand -hex 24)
modal secret create volscan-glimmer LLAMA_API_KEY=$KEY
modal deploy deploy/modal_glimmer.py                    # imprime la URL …--volscan-glimmer-serve.modal.run

# 2. Web
modal secret create volscan-app \
  VOLSCAN_LLM_BASE=https://<workspace>--volscan-glimmer-serve.modal.run/v1 \
  VOLSCAN_LLM_MODEL=hf.co/meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M \
  VOLSCAN_LLM_KEY=$KEY \
  VOLSCAN_AUTH=on \
  VOLSCAN_USERS_JSON='<la línea de config/PRODUCCION-credenciales.txt>'
modal deploy deploy/modal_app.py                        # imprime la URL pública de VolScan
```

Primera petición al modelo: descarga ~18 GB al volumen (5-10 min, solo una vez). Después, arranque en frío de
1-3 min tras 10 min sin uso. Calentadlo antes de grabar y antes de que juzguen (5-8 nov): abrid el asistente y
haced una pregunta.

Coste orientativo: la web en CPU, céntimos al día; la L40S solo cuenta mientras está encendida (~2 $/h).

## Grabar el vídeo sin freír el Mac

Con el modelo en Modal, el Mac no carga los 30B: VolScan local usa la GPU de Modal. En `.env`:

```
VOLSCAN_LLM_BASE=https://<workspace>--volscan-glimmer-serve.modal.run/v1
VOLSCAN_LLM_MODEL=hf.co/meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M
VOLSCAN_LLM_KEY=<LLAMA_API_KEY>
```

Sigue siendo Muse Glimmer (pesos abiertos de Meta) y cuenta igual para el premio de open weights: las bases
aceptan "your own hardware or partner-provided inference". O grabad directamente sobre la URL pública.

## Opción B · Docker en cualquier sitio (Render, Railway, Fly.io, VPS)

```bash
docker build -t volscan .
docker run -p 8200:8200 -e VOLSCAN_LLM_BASE=… -e VOLSCAN_LLM_MODEL=… -e VOLSCAN_LLM_KEY=… volscan
```

Necesita ~2 GB de RAM (los planes gratis de 512 MB se quedan cortos). Comprobación de salud: `GET /api/status`.

## Opción C · Sin GPU (plan de emergencia)

Desplegad solo la web, sin variables de modelo. Todo funciona y el agente responde en modo determinista con
cifras y citas; la interfaz lo indica. Grabad la demo de IA en el Mac con Glimmer local.

## Cuando lleguen los créditos de Meta

En el secreto de la web: `META_API_KEY=…`, quitad `VOLSCAN_LLM_BASE` y la IA pasa a Muse Spark sin tocar código.

## Antes de entregar

- [ ] Repo público en GitHub (regla del hackathon)
- [ ] `/api/status` muestra `"provider": "meta-local"` y `"ok": true`
- [ ] Probar el asistente y el informe de La Palma desde la URL pública en una ventana de incógnito
