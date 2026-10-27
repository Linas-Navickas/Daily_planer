# Viešas planuoklio paleidimas

Planuoklis dabar turi serverinį API ir SQLite duomenų bazę, todėl prisijungus iš telefono ar kompiuterio matomos tos pačios užduotys. Serveris naudoja `0.0.0.0` ir prieglobos platformos `PORT` reikšmę.

## Laikinas viešas URL iš savo kompiuterio

Windows kompiuteryje įdiekite `cloudflared` (arba laikykite `cloudflared.exe` aplanke `.tools/`), tada paleiskite `start_public.ps1`. Įveskite bent 12 simbolių planuoklio slaptažodį. Scenarijus paleis serverį ir Cloudflare Quick Tunnel; terminale bus parodytas laikinas `trycloudflare.com` HTTPS URL. Gavęs naują adresą scenarijus atnaujins `planner-qr.png` tame pačiame aplanke. QR generavimui įdiekite projekto priklausomybes komanda `python -m pip install -r requirements.txt`.

Kompiuteris, šis scenarijus ir interneto ryšys turi veikti visą laiką, kai norite pasiekti planuoklį. Quick Tunnel nereikalauja Cloudflare paskyros, tačiau jo adresas laikinas ir gali pasikeisti jį paleidus iš naujo. Planuoklio duomenų bazė lieka kompiuterio `data/` aplanke. Viešas URL yra pasiekiamas kitiems, todėl perduokite jį tik norimiems žmonėms ir naudokite stiprų prisijungimo slaptažodį.

## Render

1. Įkelkite projekto failus į savo GitHub, GitLab arba Bitbucket saugyklą. Saugokite ją privačią.
2. Render paskyroje pasirinkite **New → Web Service** ir prijunkite saugyklą.
3. Pasirinkite **Python 3** aplinką; paleidimo komanda: `python main.py`.
4. Pridėkite saugius aplinkos kintamuosius:
   - `PLANNER_PASSWORD` — slaptažodis prisijungimui prie svetainės.
   - `CHATGPT_API_KEY` — atsitiktinis ilgas raktas API veiksmams.
   - `DATA_DIR` — `/var/data`.
5. Prie mokamo žiniatinklio serverio prijunkite persistent disk, kurio mount path yra `/var/data`. SQLite duomenų bazė bus kuriama `/var/data/planner.sqlite3`.
6. Paskelbus programą Render pateiks viešą HTTPS adresą.

Render nemokamo serverio vietiniai failai prarandami jam persikrovus ar persileidus, o nemokama Postgres duomenų bazė galioja ribotą laiką. Todėl šio SQLite varianto užduotims išsaugoti reikia persistent disk. Prieš kuriant mokamą paslaugą patikrinkite dabartines Render sąlygas ir kainą.

## ChatGPT Actions API

`openapi.yaml` yra API schema GPT veiksmams. Paskelbus svetainę, joje pakeiskite `https://YOUR-SERVICE.onrender.com` tikru Render adresu. API raktas ChatGPT pusėje ir serverio `CHATGPT_API_KEY` turi sutapti. Niekada nedėkite rakto į `index.html`, `app.js` ar Git saugyklą.

`CHATGPT_API_KEY` sugeneruokite komanda `python -c "import secrets; print(secrets.token_urlsafe(32))"`, o reikšmę saugiai įrašykite Render aplinkos kintamuosiuose. Jos nedėkite į kodą ar Git.

Svarbu dėl turimo ChatGPT Go plano: pagal dabartinius OpenAI apribojimus asmeninė Go paskyra negali kurti naujų GPT su Actions, o pilni rašymo veiksmai per privačią MCP integraciją galimi tik palaikomose Business, Enterprise arba Edu darbo srityse. `openapi.yaml` paruošta paskyrai, kurioje GPT Actions prieinami; ChatGPT Go paskyra šiuo metu negalės tiesiogiai pridėti užduočių per šią API. [GPT kūrimo galimybės](https://help.openai.com/en/articles/8554397-creating-and-editing-gpts) · [ChatGPT MCP prieinamumas](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)

Kitas variantas — įdėti AI pokalbį į pačią planuoklio svetainę. Tam reikia prijungti OpenAI API ar atskirai patvirtintą ChatGPT plano naudojimo integraciją; tai nėra tas pats, kas naudoti ChatGPT Go tiesiogiai per API. OpenAI API raktai ir API naudojimas atsiskaito atskirai.
