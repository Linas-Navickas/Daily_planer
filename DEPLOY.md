# Planuoklio paleidimas

Planuoklis yra FastAPI programa, kurią aptarnauja Uvicorn. Duomenys saugomi PostgreSQL konteineryje; Pydantic modeliai faile `schemas.py` tikrina įvestis, o lentelių pakeitimus valdo Alembic migracijos. `docker-compose.yml` paleidžia tris atskirus konteinerius: `db`, `app` ir `mcp`. PostgreSQL duomenys išsaugomi Docker tome `postgres_data`.

## Docker konteineriai

1. Įdiekite ir paleiskite Docker Desktop.
2. Jei `.env` dar nėra, nukopijuokite `.env.example` į `.env`. Jei `.env` jau yra, išsaugokite jame esantį `CONTROL_PLANE_API_KEY` ir papildykite PostgreSQL bei `PLANNER_PASSWORD` reikšmėmis iš pavyzdžio.
3. Projekto aplanke paleiskite `docker compose up -d --build`.
4. Atidarykite `http://127.0.0.1:8000`. MCP konteineris pasiekiamas vietoje per `http://127.0.0.1:8001/mcp`; paleiskite `start_secure_mcp.ps1`, kad OpenAI tunnel-client jį prijungtų.

Sustabdykite programų konteinerius su `docker compose stop app mcp`. PostgreSQL duomenys išlieka tome. Visiems konteineriams sustabdyti naudokite `docker compose down`; duomenų tomas bus paliktas. Norint ištrinti duomenis kartu su tomu, reikėtų naudoti `docker compose down -v`.

## Svetainė kompiuteryje ir telefone

1. Įdiekite projekto priklausomybes: `python -m pip install -r requirements.txt` (įdiegiami FastAPI, Uvicorn, Pydantic ir Alembic).
2. Įdiekite `cloudflared` arba įdėkite `cloudflared.exe` į `.tools/`.
3. VS Code lange pasirinkite **Run and Debug → Paleisti viešą planuoklį** arba atidarykite PowerShell projekto aplanke ir paleiskite `start_public.ps1`.
4. Įveskite bent 12 simbolių planuoklio slaptažodį. Scenarijus paleis PostgreSQL, programos ir MCP konteinerius, laikiną Cloudflare Quick Tunnel, atidarys QR kodą ir planuoklį kompiuterio naršyklėje.
5. Kompiuteryje naudokite `http://127.0.0.1:8000`. Telefone nuskaitykite QR kodą arba atidarykite terminale parodytą viešą HTTPS adresą.

Quick Tunnel adresas pasikeičia jį paleidus iš naujo. Telefonui prieiga veiks tik kol kompiuteris įjungtas ir `start_public.ps1` tunelis veikia. Svetainės serveris klausosi tik `127.0.0.1`; Cloudflare tunelis nukreipia užklausas į jį.

## ChatGPT MCP ryšys

`start_secure_mcp.ps1` paleidžia `db`, `app` ir `mcp` konteinerius. MCP prievadas `8001` susietas tik su kompiuterio `127.0.0.1`, o OpenAI `tunnel-client` jungiasi prie šio MCP konteinerio. Kompiuteris ir scenarijaus terminalas turi likti įjungti.

Pirmą kartą:

1. Atsisiųskite OpenAI `tunnel-client` vykdomąjį failą ir įdėkite jį į `.tools/tunnel-client.exe`.
2. OpenAI Platformoje sukurkite Secure MCP Tunnel ir susiekite jį su reikiama ChatGPT darbo sritimi.
3. Paleiskite `configure_secure_mcp.ps1`; įveskite tunelio ID ir runtime API raktą. Raktas įvedamas užmaskuotai ir neįrašomas į projekto failus.
4. ChatGPT **Add custom MCP server** lange pasirinkite **Tunnel**, tą patį tunelį ir **No authentication**, tada sukurkite bei įdiekite programėlę.

Kiekvieną kartą naudodami MCP įrankius paleiskite `start_secure_mcp.ps1`. Runtime raktas pirmą kartą įrašomas į `.env`, kurį saugo `.gitignore`; vėliau scenarijus jį nuskaito automatiškai. Jis nėra tas pats, kas planuoklio svetainės slaptažodis. Niekada nedėkite runtime rakto į Git.

Svetainės Quick Tunnel ir OpenAI MCP tunelis yra atskiri. Juos galima paleisti vienu metu dviejuose terminaluose; `app` ir `mcp` konteineriai jungiasi prie tos pačios PostgreSQL duomenų bazės.

## Pasirenkama: HTTP Actions API

`openapi.yaml` yra atskiras, pasirenkamas GPT Actions API aprašas. Jis nėra reikalingas dabartiniam MCP ryšiui. Naudojant jį reikia viešai pasiekiamo HTTPS serverio, tikro serverio adreso OpenAPI faile ir serverio aplinkoje nustatyto `CHATGPT_API_KEY`. Rakto reikšmę laikykite serverio paslaptyse, ne faile ar Git saugykloje.

## Duomenų atsarginė kopija

PostgreSQL duomenys laikomi tome `postgres_data`. Atsarginę kopiją sukurkite komanda `docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > planner-backup.sql` (PowerShell aplinkoje naudokite `docker compose exec -T db pg_dump -U daily_planner daily_planner > planner-backup.sql`).
