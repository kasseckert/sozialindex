/* Datenassistent für den Sozialindex Oberfranken.
   Läuft vollständig im Browser. Externe Verbindungen nur auf Ihre Aktion hin:
   Vorschau → Regionalatlas-Datenserver, Speichern/Starten → api.github.com. */
(function () {
  "use strict";

  const DATEN_URL = "https://www.gis-idmz.nrw.de/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query";
  const KONFIG_PFAD = "konfiguration/indikatoren.json";
  const WORKFLOW = "aktualisieren.yml";
  const TYP = { kreis: 3, gemeinde: 5 };

  const Z = { konfig: null, katalog: null, katalogStand: "", quellenInfo: {}, kreise: [], ziel: null, geaendert: false,
    genesis: null, quelle: "regionalatlas" };
  const DB_NAME = { bildung: "Kommunale Bildungsdatenbank", zensus: "Zensus 2022", regio: "Regionaldatenbank", bayern: "GENESIS-Online Bayern" };
  const $ = (s) => document.querySelector(s);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (v, n = 1) => v == null ? "–" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: n }).format(v);
  const woerter = (t) => t.toLowerCase().split(/\s+/).filter(Boolean);

  // ---------------------------------------------------------------- Meldungen
  function melden(text, fehler = false) {
    const m = $("#meldung");
    m.textContent = text;
    m.classList.toggle("fehler", fehler);
    m.hidden = false;
  }

  // ------------------------------------------------------------------ Laden
  async function json(pfad) {
    const r = await fetch(pfad, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${pfad}: HTTP ${r.status}`);
    return r.json();
  }

  async function start() {
    try {
      Z.konfig = await json("data/indikatoren.json");
    } catch (e) {
      melden(`Die Konfiguration konnte nicht geladen werden (${e.message}). Die Seite muss über den Webserver aufgerufen werden.`, true);
      return;
    }
    try {
      const k = await json("data/katalog.json");
      Z.katalog = k.indikatoren; Z.katalogStand = k.stand;
    } catch { /* wird in trefferZeichnen erklärt */ }
    try { Z.quellenInfo = (await json("data/werte.json")).meta.quellen || {}; } catch { /* optional */ }
    try { Z.genesis = await json("data/genesis_katalog.json"); } catch { /* erst nach Lauf mit Zugangsdaten */ }
    try {
      Z.kreise = (await json("data/kreise.geojson")).features.map((f) => f.properties);
    } catch { /* optional */ }

    $("#gh-repo").value = localStorage.getItem("si-repo") || "";
    $("#gh-branch").value = localStorage.getItem("si-branch") || "main";
    verbinden();
    listeZeichnen();
    trefferZeichnen();
  }

  // ------------------------------------------------------- Hilfen Katalog
  function katalogEintrag(code) {
    if (!Z.katalog || !code) return null;
    const t = code.toLowerCase().replace(/-/g, "_");
    return Z.katalog.find((i) => i.tabelle === t);
  }
  function ebenenVon(ind) {
    const s = new Set();
    for (const l of Object.values(ind.jahre)) l.forEach((x) => s.add(x));
    return s;
  }
  function letztesJahr(ind, ebene) {
    const jahre = Object.keys(ind.jahre).filter((j) => ind.jahre[j].includes(ebene)).sort();
    return jahre.at(-1);
  }
  function jahresspanne(ind, ebene) {
    const jahre = Object.keys(ind.jahre).filter((j) => ind.jahre[j].includes(ebene)).sort();
    return jahre.length ? (jahre.length === 1 ? jahre[0] : `${jahre[0]}–${jahre.at(-1)}`) : null;
  }

  function quelleText(q) {
    if (q.typ === "regionalatlas") {
      if (q.code) {
        const k = katalogEintrag(q.code);
        const f = k?.felder.find((x) => x.code === (q.feld || "").toLowerCase());
        return `Regionalatlas ${q.code}${q.feld ? ", Feld " + q.feld : ""}${f ? ` (${f.titel})` : k ? ` (${k.titel})` : ""}`;
      }
      return `Regionalatlas, automatische Suche: „${[].concat(q.suche || []).join("“ oder „")}“` +
        (q.feld_suche ? `, Feld mit „${[].concat(q.feld_suche).join("“ oder „")}“` : "");
    }
    if (q.typ === "csv") return `Eigene Datei daten/import/${q.datei}`;
    if (q.typ === "genesis") {
      const db = DB_NAME[q.datenbank] || `GENESIS ${q.datenbank || ""}`;
      const filter = q.filter && Object.keys(q.filter).length ? `, Zeile „${Object.values(q.filter).join("“, „")}“` : "";
      if (q.tabelle) return `${db}, Tabelle ${q.tabelle}${filter}`;
      if (q.suche) return `${db}, automatische Suche: „${[].concat(q.suche).join("“ oder „")}“${filter}`;
      return `${db}, Tabelle noch nicht festgelegt`;
    }
    if (q.typ === "quotient") return `Anteil berechnet aus ${quelleText(q.zaehler)}${q.zeitlich_konstant ? ", für alle Jahre fortgeschrieben" : ""}`;
    if (q.typ === "schulen") {
      const art = { grundschule: "Grundschule", gymnasium: "Gymnasium", realschule: "Realschule", mittelschule: "Mittelschule" }[q.schulart] || q.schulart;
      return `Schulstandorte Bayern (Kultusministerium): Entfernung ${art === "Gymnasium" ? "zum nächsten Gymnasium" : "zur nächsten " + art}`;
    }
    return q.typ;
  }

  // -------------------------------------------------------- Konfigurationsliste
  function listeZeichnen() {
    const k = Z.konfig;
    $("#konfig-zaehler").textContent = `${k.indikatoren.length} Indikatoren in ${k.dimensionen.length} Dimensionen`;
    const dimOptionen = (wert) => k.dimensionen.map((d) => `<option value="${esc(d.id)}" ${d.id === wert ? "selected" : ""}>${esc(d.name)}</option>`).join("");

    $("#liste").innerHTML = k.indikatoren.map((ind, i) => {
      const zuletzt = ["kreis", "gemeinde"].map((e) => {
        const q = Z.quellenInfo[e]?.[ind.id];
        return q ? `${e === "kreis" ? "Kreise" : "Gemeinden"}: ${q.code ? q.code + (q.feld ? "/" + q.feld : "") : q.quelle}` : null;
      }).filter(Boolean).join(", ");
      return `<li class="a-ind" data-i="${i}" ${Z.ziel === i ? 'aria-current="true"' : ""}>
        <div class="a-ind-kopf">
          <span class="a-ind-name">${esc(ind.name)}</span>
          <span class="a-ind-dim">${esc(ind.einheit)}</span>
        </div>
        <div class="a-ind-felder">
          <label>Dimension<select data-feld="dimension">${dimOptionen(ind.dimension)}</select></label>
          <label>Richtung<select data-feld="polaritaet">
            <option value="1" ${ind.polaritaet === 1 ? "selected" : ""}>hoher Wert ist günstig</option>
            <option value="-1" ${ind.polaritaet === -1 ? "selected" : ""}>hoher Wert ist ungünstig</option></select></label>
          <label>Ebenen<span class="a-ebenen">
            <label><input type="checkbox" data-ebene="kreis" ${ind.ebenen.includes("kreis") ? "checked" : ""}> Kreise</label>
            <label><input type="checkbox" data-ebene="gemeinde" ${ind.ebenen.includes("gemeinde") ? "checked" : ""}> Gemeinden</label>
          </span></label>
        </div>
        <ol class="a-quellen">${ind.quellen.map((q, qi) => `<li>
            <span class="rang">${qi + 1}.</span>
            <span>${esc(quelleText(q))}</span>
            <span>${qi > 0 ? `<button type="button" class="klein" data-aktion="hoch" data-q="${qi}" aria-label="Quelle nach oben">nach oben</button>` : ""}
              <button type="button" class="klein gefahr" data-aktion="quelle-weg" data-q="${qi}">entfernen</button></span>
          </li>`).join("")}
          ${zuletzt ? `<li><span></span><span class="zuletzt">Zuletzt genutzt: ${esc(zuletzt)}</span><span></span></li>` : ""}
        </ol>
        <details class="a-mehr"><summary>Name, Einheit und Beschreibung</summary>
          <div class="a-ind-felder">
            <label>Name<input type="text" data-feld="name" value="${esc(ind.name)}"></label>
            <label>Einheit<input type="text" data-feld="einheit" value="${esc(ind.einheit)}"></label>
            <label>Nachkommastellen<input type="number" min="0" max="3" data-feld="nachkommastellen" value="${ind.nachkommastellen ?? 1}"></label>
            <label class="breit">Beschreibung<input type="text" data-feld="beschreibung" value="${esc(ind.beschreibung)}"></label>
          </div>
        </details>
        <div class="a-knoepfe">
          <button type="button" class="klein" data-aktion="ziel">${Z.ziel === i ? "Quellenwahl beenden" : "Quelle aus Katalog wählen"}</button>
          <button type="button" class="klein" data-aktion="csv">Eigene CSV-Datei als Quelle</button>
          <button type="button" class="klein" data-aktion="vorschau">Vorschau</button>
          <button type="button" class="klein gefahr" data-aktion="weg">Indikator entfernen</button>
        </div>
      </li>`;
    }).join("");
    zielHinweis();
  }

  function zielHinweis() {
    const h = $("#ziel-hinweis");
    if (Z.ziel == null) { h.hidden = true; return; }
    h.hidden = false;
    h.textContent = `Quellenwahl für „${Z.konfig.indikatoren[Z.ziel].name}“: Wählen Sie unten ein Feld mit „Als Quelle verwenden“.`;
  }

  function geaendert() {
    Z.geaendert = true;
    document.title = "• Datenassistent – Sozialindex Oberfranken";
  }

  // ---------------------------------------------------------- Katalogtreffer
  function trefferZeichnen() {
    $("#nur-gemeinde").closest("label").hidden = Z.quelle !== "regionalatlas";
    if (Z.quelle !== "regionalatlas") { genesisTrefferZeichnen(); return; }
    if (!Z.katalog) {
      $("#katalog-stand").textContent = "";
      $("#treffer").innerHTML = `<li>Der Katalog ist noch nicht vorhanden. Er wird beim ersten Datenabruf angelegt: Klicken Sie auf „Aktualisierung starten“ oder führen Sie <code>python etl/abrufen.py</code> aus.</li>`;
      return;
    }
    $("#katalog-stand").textContent = `${Z.katalog.length} Indikatoren, Stand ${new Date(Z.katalogStand).toLocaleDateString("de-DE")}`;
    const suche = woerter($("#suche").value);
    const nurGemeinde = $("#nur-gemeinde").checked;
    const liste = Z.katalog.filter((ind) => {
      if (nurGemeinde && !ebenenVon(ind).has("gemeinde")) return false;
      if (!ebenenVon(ind).has("kreis") && !ebenenVon(ind).has("gemeinde")) return false;
      const heu = `${ind.code} ${ind.thema} ${ind.titel} ${ind.titel_lang} ${ind.felder.map((f) => f.titel).join(" ")}`.toLowerCase();
      return suche.every((w) => heu.includes(w));
    }).slice(0, 40);

    if (!liste.length) {
      $("#treffer").innerHTML = `<li>Keine passenden Indikatoren. Versuchen Sie einen Wortstamm, etwa „arbeitslos“ statt „Arbeitslosenquote“.</li>`;
      return;
    }
    $("#treffer").innerHTML = liste.map((ind) => {
      const kreis = jahresspanne(ind, "kreis"), gem = jahresspanne(ind, "gemeinde");
      return `<li data-code="${esc(ind.code)}">
        <div class="a-t-kopf"><span class="a-t-titel">${esc(ind.titel)}</span><span class="a-t-code">${esc(ind.code)}</span></div>
        <p class="a-t-meta">${esc(ind.thema)}${ind.titel_lang && ind.titel_lang !== ind.titel ? ". " + esc(ind.titel_lang) : ""}<br>
          ${kreis ? `<span class="a-ebene-marke">Kreise ${kreis}</span>` : ""}${gem ? `<span class="a-ebene-marke gemeinde">Gemeinden ${gem}</span>` : ""}</p>
        <ul class="a-felder">${ind.felder.map((f) => `<li>
          <span>${esc(f.titel || f.code)} <span class="einheit">${esc(f.einheit)} · ${esc(f.code)}</span></span>
          <span class="knoepfe">
            <button type="button" class="klein" data-aktion="t-vorschau" data-feld="${esc(f.code)}">Vorschau</button>
            ${Z.ziel != null
              ? `<button type="button" class="klein primaer" data-aktion="t-quelle" data-feld="${esc(f.code)}">Als Quelle verwenden</button>`
              : `<button type="button" class="klein" data-aktion="t-neu" data-feld="${esc(f.code)}">Als neuer Indikator</button>`}
          </span></li>`).join("")}</ul>
      </li>`;
    }).join("");
  }

  function genesisTrefferZeichnen() {
    const db = Z.quelle;
    const liste = Z.genesis?.[db];
    if (!liste) {
      $("#katalog-stand").textContent = "";
      $("#treffer").innerHTML = `<li>Die Tabellenliste der ${esc(DB_NAME[db])} ist noch nicht vorhanden. Sie wird angelegt, sobald Zugangsdaten hinterlegt sind (GitHub: Secrets <code>GENESIS_${db.toUpperCase()}_USER</code> und <code>GENESIS_${db.toUpperCase()}_PASSWORD</code>) und ein Lauf stattgefunden hat.</li>`;
      return;
    }
    $("#katalog-stand").textContent = `${liste.length} Tabellen, Stand ${new Date(Z.genesis.stand).toLocaleDateString("de-DE")}`;
    const suche = woerter($("#suche").value);
    const treffer = liste.filter((t) => suche.every((w) => `${t.code} ${t.titel}`.toLowerCase().includes(w))).slice(0, 40);
    if (!treffer.length) { $("#treffer").innerHTML = `<li>Keine passenden Tabellen. Versuchen Sie einen Wortstamm wie „abschluss“, „schüler“ oder „betreu“.</li>`; return; }
    $("#treffer").innerHTML = treffer.map((t) => `<li data-db="${esc(db)}" data-tabelle="${esc(t.code)}">
        <div class="a-t-kopf"><span class="a-t-titel">${esc(t.titel)}</span><span class="a-t-code">${esc(t.code)}</span></div>
        <p class="a-t-meta">${esc(DB_NAME[db])}. Werte werden für Kreise abgerufen; die Wertspalte wird automatisch gewählt, andere Merkmale auf „Insgesamt“ gesetzt. Bitte das Ergebnis im Protokoll des nächsten Laufs prüfen.</p>
        <div class="a-knoepfe">${Z.ziel != null
          ? `<button type="button" class="klein primaer" data-aktion="g-quelle">Als Quelle verwenden</button>`
          : `<button type="button" class="klein" data-aktion="g-neu">Als neuer Indikator</button>`}</div>
      </li>`).join("");
  }

  function einheitKurz(u) {
    const t = (u || "").toLowerCase();
    if (t.startsWith("prozent") || t === "%") return "%";
    if (t === "eur" || t.startsWith("euro")) return "€";
    if (t.includes("m²") || t.includes("qm")) return "m²";
    return u || "";
  }
  function richtungRaten(text) {
    return /arbeitslos|sgb|bedarfsgemeinschaft|ohne abschluss|ohne haupt|schulden|kriminal|straftat|armut|mindestsicherung|pendel|unfall/i.test(text) ? -1 : 1;
  }

  function neuerIndikator(ind, feld) {
    const basis = feld.code.replace(/[^a-z0-9]/g, "");
    let id = basis, n = 2;
    while (Z.konfig.indikatoren.some((x) => x.id === id)) id = basis + n++;
    const ebenen = ["kreis", "gemeinde"].filter((e) => ebenenVon(ind).has(e));
    const name = feld.titel || ind.titel;
    Z.konfig.indikatoren.push({
      id, name, einheit: einheitKurz(feld.einheit), nachkommastellen: einheitKurz(feld.einheit) === "€" ? 0 : 1,
      beschreibung: ind.titel_lang || ind.titel, dimension: Z.konfig.dimensionen[0].id,
      polaritaet: richtungRaten(`${ind.titel} ${name}`), ebenen,
      quellen: [{ typ: "regionalatlas", code: ind.code, feld: feld.code }],
    });
    geaendert();
    listeZeichnen();
    melden(`„${name}“ wurde hinzugefügt. Bitte Dimension und Richtung prüfen.`);
    document.querySelector(`.a-ind[data-i="${Z.konfig.indikatoren.length - 1}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ---------------------------------------------------------------- Vorschau
  function sql(tabelle, typ, jahr) {
    if (!/^[a-z0-9_]+$/.test(tabelle) || ![3, 5].includes(typ) || !/^\d{4}$/.test(String(jahr))) throw new Error("ungültige Abfrage");
    return `SELECT * FROM verwaltungsgrenzen_gesamt LEFT OUTER JOIN ${tabelle} ON ags = ags2 and jahr = jahr2 ` +
      `WHERE typ = ${typ} AND jahr = ${jahr} AND (jahr2 = ${jahr} OR jahr2 IS NULL)`;
  }
  function gebietName(ags, fallback) {
    const k = Z.kreise.find((p) => p.ags === ags);
    if (!k) return fallback;
    return k.bez === "Landkreis" ? `Landkreis ${k.name}` : `${k.name} (Stadt)`;
  }
  async function abfragen(tabelle, feld, ebene, jahr) {
    const layer = { source: { type: "dataLayer", dataSource: { type: "queryTable", geometryType: "esriGeometryPolygon",
      workspaceId: "gdb", oidFields: "id", spatialReference: { wkid: 25832 }, query: sql(tabelle, TYP[ebene], jahr) } } };
    const p = new URLSearchParams({ layer: JSON.stringify(layer), f: "json", outFields: "*", returnGeometry: "false",
      where: "ags LIKE '094%'", spatialRel: "esriSpatialRelIntersects" });
    const r = await fetch(`${DATEN_URL}?${p}`);
    const d = await r.json();
    if (d.error) throw new Error(d.error.message || "Fehler des Datenservers");
    return (d.features || []).map((f) => f.attributes).filter((a) => String(a.ags).startsWith("094"))
      .map((a) => ({ ags: String(a.ags), name: gebietName(String(a.ags), a.gen || a.gen2), wert: a[feld] > 2e9 ? null : a[feld] }));
  }

  async function vorschau(code, feld) {
    const ind = katalogEintrag(code);
    const dlg = $("#dlg-vorschau");
    const inhalt = $("#vorschau-inhalt");
    if (!ind) { melden("Für diese Quelle ist keine Vorschau möglich (nur Regionalatlas-Quellen mit festem Code).", true); return; }
    const f = ind.felder.find((x) => x.code === feld) || ind.felder[0];
    $("#dlg-vorschau-titel").textContent = `${f.titel || ind.titel}`;
    inhalt.innerHTML = `<p class="a-leise">Werte werden beim Regionalatlas abgefragt …</p>`;
    dlg.showModal();
    const jahr = letztesJahr(ind, "kreis") || letztesJahr(ind, "gemeinde");
    const ebene = letztesJahr(ind, "kreis") ? "kreis" : "gemeinde";
    try {
      let zeilen = await abfragen(ind.tabelle, f.code, ebene, jahr);
      let genutztesJahr = jahr;
      if (!zeilen.some((z) => z.wert != null)) {   // neuestes Katalogjahr oft noch nicht geladen
        const vorher = Object.keys(ind.jahre).filter((j) => ind.jahre[j].includes(ebene) && j < jahr).sort().at(-1);
        if (vorher) { zeilen = await abfragen(ind.tabelle, f.code, ebene, vorher); genutztesJahr = vorher; }
      }
      const mitWert = zeilen.filter((z) => z.wert != null);
      const mittel = mitWert.reduce((s, z) => s + z.wert, 0) / (mitWert.length || 1);
      const zeigen = ebene === "kreis" ? zeilen : zeilen.slice(0, 15);
      inhalt.innerHTML = `<p class="a-leise">${ind.code}, Feld ${f.code}, ${f.einheit}. ${ebene === "kreis" ? "Kreise" : "Gemeinden"} Oberfrankens, ${genutztesJahr}: ${mitWert.length} von ${zeilen.length} mit Wert, Mittel ${fmt(mittel, 2)}.</p>
        <table class="a-vorschau"><thead><tr><th>Gebiet</th><th>Wert</th></tr></thead><tbody>
        ${zeigen.map((z) => `<tr><td>${esc(z.name)}</td><td>${z.wert == null ? "geheim/fehlt" : fmt(z.wert, 2)}</td></tr>`).join("")}
        </tbody></table>${ebene === "gemeinde" && zeilen.length > 15 ? `<p class="a-leise">… und ${zeilen.length - 15} weitere Gemeinden.</p>` : ""}`;
    } catch (e) {
      inhalt.innerHTML = `<p>Die Vorschau konnte nicht direkt im Browser geladen werden (${esc(e.message)}). Häufigster Grund: Der Datenserver erlaubt keine Abfragen von fremden Webseiten.</p>
        <p class="a-leise">Das betrifft nur die Vorschau. Beim automatischen Abruf über GitHub Actions oder <code>etl/abrufen.py</code> werden die Werte normal geholt; das Ergebnis steht danach im Protokoll des Laufs.</p>`;
    }
  }

  // ----------------------------------------------------------------- Prüfen
  function pruefen(k) {
    const fehler = [];
    const dims = new Set(k.dimensionen.map((d) => d.id));
    const ids = new Set();
    k.indikatoren.forEach((ind, i) => {
      const wer = ind.name || `Indikator ${i + 1}`;
      if (!/^[a-z0-9_]+$/.test(ind.id || "")) fehler.push(`${wer}: ungültige ID`);
      if (ids.has(ind.id)) fehler.push(`${wer}: ID „${ind.id}“ doppelt`);
      ids.add(ind.id);
      if (!dims.has(ind.dimension)) fehler.push(`${wer}: unbekannte Dimension`);
      if (![1, -1].includes(ind.polaritaet)) fehler.push(`${wer}: Richtung fehlt`);
      if (!ind.ebenen?.length) fehler.push(`${wer}: keine Ebene gewählt`);
      if (!ind.quellen?.length) fehler.push(`${wer}: keine Quelle`);
    });
    if (!k.indikatoren.length) fehler.push("Es ist kein Indikator festgelegt.");
    return fehler;
  }

  function konfigText() {
    return JSON.stringify(Z.konfig, null, 2) + "\n";
  }

  // ------------------------------------------------------------------ GitHub
  function base64Utf8(text) {
    const bytes = new TextEncoder().encode(text);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }
  async function github(methode, pfad, token, body) {
    const r = await fetch(`https://api.github.com${pfad}`, {
      method: methode,
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 204) return {};
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const hinweis = { 401: "Token ungültig oder abgelaufen.", 403: "Token hat nicht die nötigen Rechte.", 404: "Repository, Branch oder Datei nicht gefunden (oder kein Zugriff)." }[r.status] || "";
      throw new Error(`${hinweis} ${d.message || "HTTP " + r.status}`.trim());
    }
    return d;
  }
  function githubDaten() {
    const repo = $("#gh-repo").value.trim(), branch = $("#gh-branch").value.trim(), token = $("#gh-token").value.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error("Repository bitte als Besitzer/Name angeben.");
    if (!token) throw new Error("Bitte ein Zugangstoken eingeben.");
    localStorage.setItem("si-repo", repo); localStorage.setItem("si-branch", branch);
    return { repo, branch, token };
  }

  async function inGithubSpeichern() {
    const probleme = pruefen(Z.konfig);
    if (probleme.length) { melden("Bitte zuerst korrigieren: " + probleme.join("; "), true); return; }
    const { repo, branch, token } = githubDaten();
    melden("Speichere in GitHub …");
    let sha;
    try {
      sha = (await github("GET", `/repos/${repo}/contents/${KONFIG_PFAD}?ref=${encodeURIComponent(branch)}`, token)).sha;
    } catch (e) {
      if (!/nicht gefunden/.test(e.message)) throw e;
    }
    await github("PUT", `/repos/${repo}/contents/${KONFIG_PFAD}`, token, {
      message: $("#gh-notiz").value || "Indikatoren angepasst", content: base64Utf8(konfigText()), branch, ...(sha ? { sha } : {}),
    });
    Z.geaendert = false;
    document.title = "Datenassistent – Sozialindex Oberfranken";
    melden(`Gespeichert. GitHub Actions berechnet den Index jetzt neu; das dauert meist zwei bis fünf Minuten. Fortschritt: github.com/${repo}/actions`);
  }

  async function aktualisierungStarten() {
    const { repo, branch, token } = githubDaten();
    await github("POST", `/repos/${repo}/actions/workflows/${WORKFLOW}/dispatches`, token, { ref: branch });
    melden(`Aktualisierung gestartet. Fortschritt: github.com/${repo}/actions`);
  }

  // -------------------------------------------------------------- Ereignisse
  function verbinden() {
    let timer;
    $("#suche").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(trefferZeichnen, 150); });
    $("#nur-gemeinde").addEventListener("change", trefferZeichnen);
    document.querySelectorAll('input[name="katalog"]').forEach((r) =>
      r.addEventListener("change", (e) => { Z.quelle = e.target.value; trefferZeichnen(); }));

    $("#liste").addEventListener("change", (e) => {
      const li = e.target.closest(".a-ind"); if (!li) return;
      const ind = Z.konfig.indikatoren[+li.dataset.i];
      const feld = e.target.dataset.feld, ebene = e.target.dataset.ebene;
      if (feld === "polaritaet" || feld === "nachkommastellen") ind[feld] = Number(e.target.value);
      else if (feld) ind[feld] = e.target.value;
      if (ebene) ind.ebenen = ["kreis", "gemeinde"].filter((x) => li.querySelector(`[data-ebene="${x}"]`).checked);
      geaendert();
      if (feld === "name") listeZeichnen();
    });

    $("#liste").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-aktion]"); if (!b) return;
      const i = +b.closest(".a-ind").dataset.i;
      const ind = Z.konfig.indikatoren[i];
      const a = b.dataset.aktion;
      if (a === "ziel") { Z.ziel = Z.ziel === i ? null : i; listeZeichnen(); trefferZeichnen(); if (Z.ziel != null) $("#suche").focus(); return; }
      if (a === "weg") {
        if (!confirm(`„${ind.name}“ aus dem Index entfernen?`)) return;
        Z.konfig.indikatoren.splice(i, 1); Z.ziel = null;
      } else if (a === "quelle-weg") {
        ind.quellen.splice(+b.dataset.q, 1);
      } else if (a === "hoch") {
        const q = +b.dataset.q; [ind.quellen[q - 1], ind.quellen[q]] = [ind.quellen[q], ind.quellen[q - 1]];
      } else if (a === "csv") {
        const name = prompt("Dateiname in daten/import/ (Spalten ags;jahr;wert):", `${ind.id}.csv`);
        if (!name) return;
        if (!/^[\w.-]+\.csv$/i.test(name)) { melden("Bitte einen Dateinamen wie „alq.csv“ angeben.", true); return; }
        ind.quellen.push({ typ: "csv", datei: name });
      } else if (a === "vorschau") {
        const q = ind.quellen.find((x) => x.typ === "regionalatlas" && x.code)
          || (() => { const z = Z.quellenInfo.kreis?.[ind.id] || Z.quellenInfo.gemeinde?.[ind.id]; return z?.code ? { code: z.code, feld: z.feld } : null; })();
        if (!q) { melden("Vorschau ist für Quellen mit festem Regionalatlas-Code möglich. Automatische Suchen werden erst beim Abruf aufgelöst.", true); return; }
        vorschau(q.code, q.feld);
        return;
      }
      geaendert(); listeZeichnen(); trefferZeichnen();
    });

    $("#treffer").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-aktion]"); if (!b) return;
      if (b.dataset.aktion.startsWith("g-")) {
        const li = b.closest("li[data-tabelle]");
        const quelle = { typ: "genesis", datenbank: li.dataset.db, tabelle: li.dataset.tabelle };
        const titel = li.querySelector(".a-t-titel").textContent;
        if (b.dataset.aktion === "g-quelle" && Z.ziel != null) {
          const ziel = Z.konfig.indikatoren[Z.ziel];
          ziel.quellen.unshift(quelle);
          melden(`Für „${ziel.name}“ wird jetzt zuerst ${DB_NAME[quelle.datenbank]}, Tabelle ${quelle.tabelle} verwendet.`);
          Z.ziel = null;
        } else {
          let id = li.dataset.tabelle.toLowerCase().replace(/[^a-z0-9]/g, "_"), n = 2;
          while (Z.konfig.indikatoren.some((x) => x.id === id)) id = id + n++;
          Z.konfig.indikatoren.push({ id, name: titel.slice(0, 80), einheit: "", nachkommastellen: 1, beschreibung: titel,
            dimension: Z.konfig.dimensionen.find((d) => d.id === "bildung")?.id || Z.konfig.dimensionen[0].id,
            polaritaet: richtungRaten(titel), ebenen: ["kreis"], quellen: [quelle] });
          melden(`„${titel.slice(0, 60)}“ wurde hinzugefügt. Bitte Name, Einheit, Dimension und Richtung prüfen.`);
        }
        geaendert(); listeZeichnen(); trefferZeichnen();
        return;
      }
      const ind = katalogEintrag(b.closest("li[data-code]").dataset.code);
      const feld = ind.felder.find((f) => f.code === b.dataset.feld);
      if (b.dataset.aktion === "t-vorschau") vorschau(ind.code, feld.code);
      else if (b.dataset.aktion === "t-neu") neuerIndikator(ind, feld);
      else if (b.dataset.aktion === "t-quelle" && Z.ziel != null) {
        const ziel = Z.konfig.indikatoren[Z.ziel];
        ziel.quellen.unshift({ typ: "regionalatlas", code: ind.code, feld: feld.code });
        melden(`Für „${ziel.name}“ wird jetzt zuerst ${ind.code}/${feld.code} verwendet.`);
        Z.ziel = null; geaendert(); listeZeichnen(); trefferZeichnen();
      }
    });

    $("#btn-vorschau-zu").addEventListener("click", () => $("#dlg-vorschau").close());

    $("#btn-download").addEventListener("click", () => {
      const probleme = pruefen(Z.konfig);
      if (probleme.length) melden("Hinweis: " + probleme.join("; "), true);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([konfigText()], { type: "application/json" }));
      a.download = "indikatoren.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    });

    $("#btn-github").addEventListener("click", () => $("#dlg-github").showModal());
    $("#dlg-github").addEventListener("close", async () => {
      if ($("#dlg-github").returnValue !== "ok") return;
      try { await inGithubSpeichern(); } catch (e) { melden(`Speichern fehlgeschlagen: ${e.message}`, true); }
    });
    $("#btn-start").addEventListener("click", async () => {
      if (!$("#gh-token").value.trim()) { $("#dlg-github").showModal(); melden("Bitte zuerst Repository und Token eingeben; danach erneut auf „Aktualisierung starten“ klicken."); return; }
      try { await aktualisierungStarten(); } catch (e) { melden(`Start fehlgeschlagen: ${e.message}`, true); }
    });

    const details = $(".a-json");
    details.addEventListener("toggle", () => { if (details.open) $("#json").value = konfigText(); });
    $("#btn-json").addEventListener("click", () => {
      try {
        const neu = JSON.parse($("#json").value);
        const probleme = pruefen(neu);
        if (probleme.length) { melden("JSON nicht übernommen: " + probleme.join("; "), true); return; }
        Z.konfig = neu; geaendert(); listeZeichnen(); trefferZeichnen();
        melden("JSON übernommen.");
      } catch (e) { melden(`JSON fehlerhaft: ${e.message}`, true); }
    });

    window.addEventListener("beforeunload", (e) => { if (Z.geaendert) { e.preventDefault(); e.returnValue = ""; } });
  }

  start();
})();
