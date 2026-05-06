# Static assets (Vite `public/` directory)

Anything dropped into this folder is copied verbatim to `frontend/dist/`
during `npm run build` and served from the root of the deployed app.

## Add a logo

Drop a file here named **`logo.png`** (or `.svg`, `.webp`, `.jpg`) and rebuild
the frontend. The app's header will pick it up automatically when
`APP_LOGO_URL=/logo.png` (the default in `databricks.yml`).

To use a different filename or a remote URL, set `APP_LOGO_URL` in
`databricks.yml` (or `runtime_resources.json` → `app_logo_url`) — env vars
take priority. Examples:

```yaml
# Use a custom filename
- name: APP_LOGO_URL
  value: /my-logo.svg

# Or an external URL (no rebuild needed for this one)
- name: APP_LOGO_URL
  value: https://cdn.example.com/brand/capita.svg
```

A separate dark-mode variant can be set via `APP_LOGO_URL_DARK` — falls back
to `APP_LOGO_URL` if not provided.

## Recommended logo sizing

The header reserves up to **160 × 32 px** (`max-w-[160px]` × `h-8`) and uses
`object-contain`, so any aspect ratio works. PNG with transparent background
or SVG looks best.
