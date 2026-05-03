# Live testing on a phone

The mobile PWA needs HTTPS for microphone + camera permission on iOS Safari.
Since the backend and the mobile dev server both live on this Mac mini's
localhost, we tunnel each to a public HTTPS URL via [cloudflared] quick
tunnels (free, no account needed).

## Currently running (this session)

| | URL |
|---|---|
| 📱 **Open this on your phone** | `https://thy-eligibility-characterized-docs.trycloudflare.com/` |
| Backend (for curl) | `https://camcorder-preston-tracy-modeling.trycloudflare.com/` |

These URLs **change every time you restart the tunnels** (cloudflared
quick tunnels are ephemeral). When you relaunch with the script below,
the new URLs print at the end.

## Relaunching everything

```bash
./scripts/dev-live.sh
```

That script:

1. Frees ports 8000 and 3000 (kills any zombies).
2. Starts `uvicorn` against `Backend/`.
3. Opens a cloudflared tunnel to localhost:8000 → grabs the public URL.
4. Starts `next dev` against `MobileApp/` with `NEXT_PUBLIC_BACKEND_BASE_URL`
   set to the backend tunnel URL.
5. Opens a second cloudflared tunnel to localhost:3000.
6. Prints both URLs.
7. Keeps running until you press Ctrl-C, then tears every subprocess down.

Logs stream to `${TMPDIR}/asu-museum-dev/`.

## Why this setup, not Vercel

Vercel CLI requires interactive browser login or a `VERCEL_TOKEN`. Quick
tunnels need neither and produce a working URL in ~5 seconds. They support
WebSocket upgrades, which the `/voice/ws` endpoint depends on.

For a more permanent deployment (custom domain, no flapping URLs), run
`vercel login` once and switch to a Vercel deployment of the static export.

## On the phone

1. Open the mobile URL (`https://...trycloudflare.com/`) in mobile Safari
   or Chrome.
2. Grant microphone permission when prompted.
3. (Optional) Tap **"Identify by camera"** at the top of the picker —
   grant camera permission, point at an artwork, tap shutter.
4. Otherwise, pick an artwork manually, then **press and hold** the
   terracotta button at the bottom and ask anything.
5. iOS users can also "Add to Home Screen" from the share menu — the
   app icon and themed splash come from `manifest.json`.

[cloudflared]: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/
