# Deploying hands

One container runs everything: the API, the operator console, the CoreOne mock app (internal only), headless
Chromium, and the built web UI. Railway hosts it. Vercel can optionally host the UI on its own.

```
browser ── https ──► Railway service (Dockerfile)
                       ├─ /            web UI (web/dist)
                       ├─ /api/*       hands API
                       ├─ /console/*   operator console + live-view websocket
                       └─ 127.0.0.1:8700  CoreOne mock app (not exposed)
                     volume /data: artifacts/, runs/
```

## Railway (API + UI in one service)

1. From `hands/`, create the project and service (one time):

```bash
railway init --name hands
```

```bash
railway up --detach
```

2. Add a volume mounted at `/data` (Railway dashboard: service, Settings, Volumes). Without it, recorded
   capabilities and run evidence are lost on every redeploy.

3. Set variables (dashboard: service, Variables), then redeploy:

| Variable | Value | Why |
| --- | --- | --- |
| `HANDS_API_TOKEN` | a long random string you generate | The UI and console require it; without it anyone with the URL can drive the live session |
| `ANTHROPIC_API_KEY` | your key | Enables discovery with Claude Sonnet 5.5; replay never needs it |
| `HANDS_CORS_ORIGINS` | your Vercel URL, only if you host the UI there | Lets that origin call the API |

`PORT`, `HANDS_DATA_DIR=/data` and `HANDS_HEADLESS=1` are already handled by the image.

4. Generate a public domain (dashboard: service, Settings, Networking). Open it, go to Settings in the UI and
   paste the access token.

The health check is `/api/health`. A fresh volume is seeded with the repo's capability, its prairie overlay,
and the recorded evidence runs, so the UI opens with real history.

## Vercel (optional, UI only)

The Railway service already serves the UI. To host the UI on Vercel as well:

```bash
cd web && npx vercel --prod
```

Set `VITE_HANDS_API_URL` to the Railway URL in the Vercel project's environment variables, and add the Vercel URL
to `HANDS_CORS_ORIGINS` on Railway. The live operator view connects to Railway directly over a websocket.

## Local

```bash
uv run hands serve --port 8080
```

Open http://127.0.0.1:8080. For Claude discovery locally, load the key first:
`set -a && source .env && set +a`.

## Limits of this deployment

- One run at a time; a second run gets HTTP 409.
- The token is a single shared secret, not per-user login.
- Model calls send masked screenshots and screen text to Anthropic.
- It is a demo of the mock app only. Real bank apps need the in-network runner described in the technical
  solution document.
