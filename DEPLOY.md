# Planuoklio paleidimas

Planuoklis yra Python HTTP programa, kuri saugo duomenis SQLite duomenų bazėje `data/planner.sqlite3`. Aplankas `data/` neįkeliamas į Git.

## Svetainė kompiuteryje ir telefone

1. Įdiekite projekto priklausomybes: `python -m pip install -r requirements.txt`.
2. Įdiekite `cloudflared` arba įdėkite `cloudflared.exe` į `.tools/`.
3. VS Code lange pasirinkite **Run and Debug → Paleisti viešą planuoklį** arba atidarykite PowerShell projekto aplanke ir paleiskite `start_public.ps1`.
4. Įveskite bent 12 simbolių planuoklio slaptažodį. Scenarijus paleis serverį ir laikiną Cloudflare Quick Tunnel, atidarys QR kodą ir planuoklį kompiuterio naršyklėje.
5. Kompiuteryje naudokite `http://127.0.0.1:8000`. Telefone nuskaitykite QR kodą arba atidarykite terminale parodytą viešą HTTPS adresą.

Quick Tunnel adresas pasikeičia jį paleidus iš naujo. Telefonui prieiga veiks tik kol kompiuteris įjungtas ir `start_public.ps1` tunelis veikia. Svetainės serveris klausosi tik `127.0.0.1`; Cloudflare tunelis nukreipia užklausas į jį.

## ChatGPT MCP ryšys

`start_secure_mcp.ps1` paleidžia antrą, tik `127.0.0.1:8001` pasiekiamą MCP serverį ir OpenAI `tunnel-client`. Tam reikia, kad kompiuteris būtų įjungtas, o scenarijaus terminalas liktų atidarytas.

Pirmą kartą:

1. Atsisiųskite OpenAI `tunnel-client` vykdomąjį failą ir įdėkite jį į `.tools/tunnel-client.exe`.
2. OpenAI Platformoje sukurkite Secure MCP Tunnel ir susiekite jį su reikiama ChatGPT darbo sritimi.
3. Paleiskite `configure_secure_mcp.ps1`; įveskite tunelio ID ir runtime API raktą. Raktas įvedamas užmaskuotai ir neįrašomas į projekto failus.
4. ChatGPT **Add custom MCP server** lange pasirinkite **Tunnel**, tą patį tunelį ir **No authentication**, tada sukurkite bei įdiekite programėlę.

Kiekvieną kartą naudodami MCP įrankius paleiskite `start_secure_mcp.ps1` ir įveskite runtime raktą. Jis nėra tas pats, kas planuoklio svetainės slaptažodis. Niekada nedėkite runtime rakto į Git.

Svetainės tunelis ir MCP tunelis yra atskiri. Juos galima paleisti vienu metu dviejuose terminaluose; jie naudoja skirtingus prievadus, bet tą pačią SQLite duomenų bazę.

## Pasirenkama: HTTP Actions API

`openapi.yaml` yra atskiras, pasirenkamas GPT Actions API aprašas. Jis nėra reikalingas dabartiniam MCP ryšiui. Naudojant jį reikia viešai pasiekiamo HTTPS serverio, tikro serverio adreso OpenAPI faile ir serverio aplinkoje nustatyto `CHATGPT_API_KEY`. Rakto reikšmę laikykite serverio paslaptyse, ne faile ar Git saugykloje.

## Duomenų atsarginė kopija

Duomenų bazė yra `data/planner.sqlite3`. Prieš didelius pakeitimus ar perkėlimą sustabdykite abu scenarijus ir nukopijuokite visą `data/` aplanką į saugią vietą.
