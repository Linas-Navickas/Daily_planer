# Viešas planuoklio paleidimas

Planuoklis dabar turi serverinį API ir SQLite duomenų bazę, todėl prisijungus iš telefono ar kompiuterio matomos tos pačios užduotys. Serveris naudoja `0.0.0.0` ir prieglobos platformos `PORT` reikšmę.

## Laikinas viešas URL iš savo kompiuterio

Windows kompiuteryje įdiekite `cloudflared` (arba laikykite `cloudflared.exe` aplanke `.tools/`), tada paleiskite `start_public.ps1`. Įveskite bent 12 simbolių planuoklio slaptažodį. Scenarijus paleis serverį ir Cloudflare Quick Tunnel; terminale bus parodytas laikinas `trycloudflare.com` HTTPS URL. Gavęs naują adresą scenarijus atnaujins `planner-qr.png` tame pačiame aplanke. QR generavimui įdiekite projekto priklausomybes komanda `python -m pip install -r requirements.txt`.

Kompiuteris, šis scenarijus ir interneto ryšys turi veikti visą laiką, kai norite pasiekti planuoklį. Quick Tunnel nereikalauja Cloudflare paskyros, tačiau jo adresas laikinas ir gali pasikeisti jį paleidus iš naujo. Planuoklio duomenų bazė lieka kompiuterio `data/` aplanke. Viešas URL yra pasiekiamas kitiems, todėl perduokite jį tik norimiems žmonėms ir naudokite stiprų prisijungimo slaptažodį.

## ChatGPT planuoklio papildinys

Serveris turi MCP jungtį su užduočių, svorio, žingsnių ir sveikatos įrašų skaitymo bei įrašymo įrankiais. Jungtis naudoja OAuth: pirmą kartą ChatGPT atidarys planuoklio prisijungimo puslapį, kuriame įveskite tą patį planuoklio slaptažodį. Slaptažodis ChatGPT įrankiams neperduodamas; serveris išduoda riboto galiojimo prieigos raktą.

1. Paleiskite `start_public.ps1` ir nukopijuokite terminale parodytą `https://...trycloudflare.com` adresą.
2. ChatGPT žiniatinklio versijoje atverkite **Plugins** → **+** → **Add custom MCP server**.
3. Nurodykite serverio URL su `/mcp` pabaigoje, pvz., `https://jusu-adresas.trycloudflare.com/mcp`, ir pasirinkite OAuth autentifikaciją.
4. Sukurkite, įdiekite papildinį ir pirmą kartą naudodami patvirtinkite planuoklio prisijungimą.
5. Pokalbyje pasirinkite papildinį ir aiškiai nurodykite, ką įrašyti, pvz., „įrašyk rytoj 8 val. darbą: paskambinti gydytojui“ arba „įrašyk šiandien 8500 žingsnių“.

Quick Tunnel adresas keičiasi jį paleidus iš naujo. Pakeitus adresą, ChatGPT papildinyje reikės atnaujinti MCP serverio URL. ChatGPT gali prašyti patvirtinti kiekvieną įrašymo veiksmą.

## Įkelti ChatGPT paruoštą tekstą (veikia ir su Go)

1. Atidarykite planuoklį ir pasirinkite meniu **Iš ChatGPT**.
2. Paspauskite **Kopijuoti nurodymą**, įklijuokite jį į ChatGPT ir po juo padiktuokite ar parašykite, ką įrašyti.
3. Nukopijuokite ChatGPT grąžintas paprasto teksto eilutes ir įklijuokite į planuoklio lauką.
4. Paspauskite **Peržiūrėti įrašus**, patikrinkite datas bei reikšmes ir tada **Išsaugoti**.

Planuoklis gali įkelti užduotis, svorį, žingsnių skaičių ir pulso/kraujospūdžio rodmenis. Svorio, žingsnių ar sveikatos įrašas tai pačiai datai bus atnaujintas; užduotys bus pridėtos. Šis kelias tekstą perduoda kopijuojant ir įklijuojant; papildomas ChatGPT planas ar OpenAI API raktas nereikalingas.

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

Ši MCP jungtis paruošta palaikomai ChatGPT darbo sričiai, bet jos įdiegti į asmeninę Go paskyrą negalima. Be to, individualūs MCP serveriai jungiami per ChatGPT žiniatinklį; mobiliojoje programėlėje jų prijungti negalima. Galite telefone padiktuoti tekstą į ChatGPT, tačiau automatinis įrašymas į šį planuoklį veiks tik paskyroje, kurioje įmanoma prijungti šią rašymo teises turinčią MCP jungtį. [OpenAI MCP jungčių reikalavimai](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)

Kitas variantas — įdėti AI pokalbį į pačią planuoklio svetainę. Tam reikia prijungti OpenAI API ar atskirai patvirtintą ChatGPT plano naudojimo integraciją; tai nėra tas pats, kas naudoti ChatGPT Go tiesiogiai per API. OpenAI API raktai ir API naudojimas atsiskaito atskirai.
