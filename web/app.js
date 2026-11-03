/* Sozialindex Oberfranken – Kartenanwendung
   Benötigt: Leaflet 1.9, Chart.js 4 (beide lokal unter vendor/). */
(function () {
  "use strict";

  // ------------------------------------------------------------ Zustand
  const Z = {
    daten: null, kreise: null, gemeinden: null,
    ebene: "kreis", merkmal: "index", jahr: null,
    auswahl: null,            // ags des geöffneten Gebiets
    reiter: "profil",
  };
  const Karte = { map: null, flaechen: null, grenzen: null, layerNachAgs: new Map(), popup: null, diagramm: null,
    hoverRand: null, hoverAgs: null, hoverLayer: null, auswahlRand: null };
  // Geräte ohne Maus (Tablet, Handy): keine Hover-Effekte, ein Tippen öffnet das Popup.
  const mitMaus = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const reduziert = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const STUFEN = [85, 92, 97, 103, 108, 115];   // Klassengrenzen auf der 100er-Skala
  const DIM_KURZ = { arbeit: "Arbeit", demografie: "Demografie", bildung: "Bildung", versorgung: "Versorgung" };

  // ------------------------------------------------------------ Helfer
  const $ = (s) => document.querySelector(s);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmt = (wert, stellen = 1) =>
    wert == null || Number.isNaN(wert) ? "–"
      : new Intl.NumberFormat("de-DE", { minimumFractionDigits: stellen, maximumFractionDigits: stellen }).format(wert);
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function indikator(id) { return Z.daten.meta.indikatoren.find((i) => i.id === id); }
  function dimension(id) { return Z.daten.meta.dimensionen.find((d) => d.id === id); }

  function mitEinheit(wert, ind) {
    if (wert == null) return "–";
    const zahl = fmt(wert, ind.nachkommastellen ?? 1);
    if (ind.einheit === "%") return `${zahl} %`;
    if (ind.einheit === "€") return `${zahl} €`;
    if (ind.einheit === "m²") return `${zahl} m²`;
    return zahl;   // Einheiten wie "je 1.000 EW" stehen bereits im Namen
  }

  function anzeigeName(props, ebene) {
    if (ebene === "kreis") {
      return props.bez === "Landkreis" ? `Landkreis ${props.name}` : `${props.name} (Stadt)`;
    }
    return props.name;
  }
  function kreisVon(agsGemeinde) {
    return Z.kreise.features.find((f) => f.properties.ags === agsGemeinde.slice(0, 5))?.properties;
  }
  function unterzeile(props, ebene) {
    if (ebene === "kreis") return props.bez;
    const k = kreisVon(props.ags);
    if (props.ags.endsWith("000")) return "Kreisfreie Stadt";
    return `${props.bez}, ${k ? anzeigeName(k, "kreis") : ""}`;
  }

  function ebenenDaten() { return Z.daten[Z.ebene]; }
  function gebietDaten(ags, ebene = Z.ebene) { return Z.daten[ebene].gebiete[ags]; }

  /** Wert auf der 100er-Skala (höher = günstiger) für das aktuelle Merkmal. */
  function skalenwert(ags, merkmal = Z.merkmal, jahr = Z.jahr, ebene = Z.ebene) {
    const g = gebietDaten(ags, ebene);
    if (!g) return null;
    const j = String(jahr);
    if (merkmal === "index") return g.index[j] ?? null;
    if (merkmal.startsWith("dim:")) return g.dimensionen[merkmal.slice(4)]?.[j] ?? null;
    const id = merkmal.slice(4);
    const wert = g.werte[id]?.[j];
    const ref = Z.daten[ebene].referenz[id]?.[j];
    const sd = Z.daten[ebene].statistik[id]?.sd;
    if (wert == null || ref == null || !sd) return null;
    return 100 + 10 * indikator(id).polaritaet * (wert - ref) / sd;
  }

  /** Text für Kurzinfo und Rangliste. */
  function anzeigeWert(ags, merkmal = Z.merkmal) {
    if (merkmal === "index" || merkmal.startsWith("dim:")) return fmt(skalenwert(ags, merkmal), 1);
    const id = merkmal.slice(4);
    return mitEinheit(gebietDaten(ags)?.werte[id]?.[String(Z.jahr)], indikator(id));
  }

  function farbe(wert) {
    if (wert == null) return css("--ohne-daten");
    let k = 0;
    while (k < STUFEN.length && wert >= STUFEN[k]) k++;
    return css(`--s${k + 1}`);
  }

  function merkmalName(m = Z.merkmal) {
    if (m === "index") return "Sozialindex gesamt";
    if (m.startsWith("dim:")) return dimension(m.slice(4)).name;
    return indikator(m.slice(4)).name;
  }

  // ------------------------------------------------------------ Laden
  async function laden() {
    if (window.__SOZIALINDEX__) return window.__SOZIALINDEX__;   // gebündelte Vorschau
    const holen = async (pfad) => {
      const r = await fetch(pfad, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${pfad}: HTTP ${r.status}`);
      return r.json();
    };
    const [kreise, gemeinden, werte] = await Promise.all([
      holen("data/kreise.geojson"), holen("data/gemeinden.geojson"), holen("data/werte.json"),
    ]);
    return { kreise, gemeinden, werte };
  }

  // ------------------------------------------------------------ Steuerung
  function merkmalOptionenAufbauen() {
    const sel = $("#merkmal");
    const verfuegbar = new Set(ebenenDaten().indikatoren);
    const gruppen = [];
    gruppen.push(`<option value="index">Sozialindex gesamt</option>`);
    const dimsDa = new Set(ebenenDaten().dimensionen || Z.daten.meta.dimensionen.map((d) => d.id));
    gruppen.push(`<optgroup label="Dimensionen">${Z.daten.meta.dimensionen.filter((d) => dimsDa.has(d.id))
      .map((d) => `<option value="dim:${d.id}">${esc(d.name)}</option>`).join("")}</optgroup>`);
    for (const d of Z.daten.meta.dimensionen) {
      const inds = Z.daten.meta.indikatoren.filter((i) => i.dimension === d.id && verfuegbar.has(i.id));
      if (inds.length) {
        gruppen.push(`<optgroup label="${esc(d.name)}">${inds
          .map((i) => `<option value="ind:${i.id}">${esc(i.name)}</option>`).join("")}</optgroup>`);
      }
    }
    sel.innerHTML = gruppen.join("");
    if (![...sel.options].some((o) => o.value === Z.merkmal)) Z.merkmal = "index";
    sel.value = Z.merkmal;
  }

  function suchlisteAufbauen() {
    const fc = Z.ebene === "kreis" ? Z.kreise : Z.gemeinden;
    $("#suchliste").innerHTML = fc.features
      .filter((f) => gebietDaten(f.properties.ags))
      .map((f) => suchText(f.properties))
      .sort((a, b) => a.localeCompare(b, "de"))
      .map((t) => `<option value="${esc(t)}"></option>`).join("");
  }
  function suchText(p) {
    if (Z.ebene === "kreis") return anzeigeName(p, "kreis");
    if (p.ags.endsWith("000")) return `${p.name} (kreisfreie Stadt)`;
    const k = kreisVon(p.ags);
    return `${p.name} (${k ? anzeigeName(k, "kreis") : ""})`;
  }

  function steuerungVerbinden() {
    const jahre = Z.daten.meta.jahre;
    const regler = $("#jahr");
    regler.min = Math.min(...jahre); regler.max = Math.max(...jahre); regler.value = Z.jahr;
    $("#jahr-anzeige").textContent = Z.jahr;

    regler.addEventListener("input", () => {
      Z.jahr = Number(regler.value);
      $("#jahr-anzeige").textContent = Z.jahr;
      aktualisieren();
    });
    $("#merkmal").addEventListener("change", (e) => { Z.merkmal = e.target.value; aktualisieren(); });
    document.querySelectorAll('input[name="ebene"]').forEach((r) =>
      r.addEventListener("change", (e) => {
        Z.ebene = e.target.value;
        Z.auswahl = null;
        Karte.map.closePopup();
        merkmalOptionenAufbauen();
        suchlisteAufbauen();
        flaechenZeichnen();
        aktualisieren();
      }));
    $("#suche").addEventListener("change", (e) => {
      const fc = Z.ebene === "kreis" ? Z.kreise : Z.gemeinden;
      const treffer = fc.features.find((f) => suchText(f.properties) === e.target.value)
        || fc.features.find((f) => f.properties.name.toLowerCase() === e.target.value.trim().toLowerCase());
      if (treffer) { gebietOeffnen(treffer.properties.ags, true); e.target.value = ""; }
    });
  }

  // ------------------------------------------------------------ Karte
  function karteAnlegen() {
    Karte.map = L.map("karte", {
      zoomSnap: 0.25, zoomDelta: 0.5, attributionControl: true,
      zoomAnimation: !reduziert, fadeAnimation: !reduziert, markerZoomAnimation: !reduziert,
    });
    // Eigene Ebenen für Umrisse über den Flächen; sie fangen keine Mausereignisse ab.
    for (const [name, z] of [["grenzen", 410], ["auswahl", 420], ["hover", 430]]) {
      Karte.map.createPane(name);
      Karte.map.getPane(name).style.zIndex = z;
      Karte.map.getPane(name).style.pointerEvents = "none";
    }
    Karte.map.on("mouseout", hoverAus);
    Karte.map.attributionControl.setPrefix(false);
    Karte.map.attributionControl.addAttribution("Grenzen © GeoBasis-DE / BKG (dl-de/by-2-0)");
    const grenzen = L.geoJSON(Z.kreise).getBounds();
    Karte.map.fitBounds(grenzen, { padding: [24, 24] });
    Karte.map.setMinZoom(Karte.map.getZoom() - 1);
    Karte.map.setMaxBounds(grenzen.pad(0.5));
    Karte.map.on("popupclose", () => {
      if (Karte.diagramm) { Karte.diagramm.destroy(); Karte.diagramm = null; }
      Z.auswahl = null;
      ranglisteMarkieren();
      stileSetzen();
    });
  }

  function flaechenZeichnen() {
    hoverAus();
    if (Karte.flaechen) Karte.flaechen.remove();
    if (Karte.grenzen) Karte.grenzen.remove();
    Karte.layerNachAgs.clear();
    const fc = Z.ebene === "kreis" ? Z.kreise : Z.gemeinden;

    Karte.flaechen = L.geoJSON(fc, {
      style: () => ({}),
      onEachFeature: (f, layer) => {
        const p = f.properties;
        Karte.layerNachAgs.set(p.ags, layer);
        const freiesGebiet = p.bez === "Gemeindefreies Gebiet";
        if (mitMaus) layer.bindTooltip(() => freiesGebiet
          ? `<span>${esc(p.name)}</span><br><span>Gemeindefreies Gebiet, keine Daten</span>`
          : `<strong>${esc(anzeigeName(p, Z.ebene))}</strong><br>${esc(merkmalName())}: <b>${esc(anzeigeWert(p.ags))}</b>`,
        { sticky: true, className: "kurzinfo", direction: "top", offset: [0, -8] });
        if (freiesGebiet) {
          layer.on("mouseover", () => { hoverAus(); Karte.hoverLayer = layer; });
          return;
        }
        layer.on({
          mouseover: () => hoverAn(layer),
          mouseout: () => { if (Karte.hoverAgs === p.ags) hoverAus(); },
          click: () => { hoverAus(); gebietOeffnen(p.ags, false); },
        });
      },
    }).addTo(Karte.map);

    if (Z.ebene === "gemeinde") {
      Karte.grenzen = L.geoJSON(Z.kreise, {
        interactive: false, pane: "grenzen",
        style: { fill: false, color: css("--kreisgrenze"), weight: 1.6, opacity: 0.85 },
      }).addTo(Karte.map);
    } else {
      Karte.grenzen = null;
    }
    stileSetzen();
  }

  function stilFuer(layer, p) {
    layer.setStyle({
      fillColor: p.bez === "Gemeindefreies Gebiet" ? css("--ohne-daten") : farbe(skalenwert(p.ags)),
      fillOpacity: 1,
      color: css("--kontur"),
      weight: Z.ebene === "kreis" ? 1.4 : 0.6,
    });
  }
  /** Umriss als eigene, nicht anklickbare Ebene; die Flächen werden nie umsortiert. */
  function umriss(feature, pane, gewicht) {
    return L.geoJSON(feature, {
      pane, interactive: false,
      style: { fill: false, color: css("--tinte"), weight: gewicht, opacity: 1 },
    }).addTo(Karte.map);
  }
  function hoverAn(layer) {
    if (!mitMaus) return;
    const ags = layer.feature.properties.ags;
    if (Karte.hoverAgs === ags) return;
    hoverAus();   // Vorgänger immer ausdrücklich zurücksetzen
    Karte.hoverAgs = ags;
    Karte.hoverLayer = layer;
    if (ags !== Z.auswahl) Karte.hoverRand = umriss(layer.feature, "hover", 2.5);
  }
  function hoverAus() {
    if (Karte.hoverRand) Karte.hoverRand.remove();
    if (Karte.hoverLayer) Karte.hoverLayer.closeTooltip();
    Karte.hoverRand = null;
    Karte.hoverAgs = null;
    Karte.hoverLayer = null;
  }
  function stileSetzen() {
    Karte.flaechen.eachLayer((l) => stilFuer(l, l.feature.properties));
    if (Karte.grenzen) Karte.grenzen.setStyle({ color: css("--kreisgrenze") });
    if (Karte.auswahlRand) { Karte.auswahlRand.remove(); Karte.auswahlRand = null; }
    const sel = Z.auswahl && Karte.layerNachAgs.get(Z.auswahl);
    if (sel) Karte.auswahlRand = umriss(sel.feature, "auswahl", 3);
  }

  // ------------------------------------------------------------ Legende & Rangliste
  function legendeZeichnen() {
    $("#legende-titel").textContent = `${merkmalName()}, ${Z.jahr}`;
    $("#skala").innerHTML = [1, 2, 3, 4, 5, 6, 7].map((k) => `<span style="background:var(--s${k})"></span>`).join("");
    const istIndikator = Z.merkmal.startsWith("ind:");
    $("#legende-hinweis").textContent = istIndikator
      ? `Farbe zeigt die Abweichung vom Durchschnitt der ${Z.ebene === "kreis" ? "Kreise" : "Gemeinden"}. ${indikator(Z.merkmal.slice(4)).beschreibung}.`
      : `100 = Durchschnitt der ${Z.ebene === "kreis" ? "oberfränkischen Kreise" : "oberfränkischen Gemeinden"}. Stufen: unter 85, 85–92, 92–97, 97–103, 103–108, 108–115, ab 115. ${abdeckungText()}`;
  }

  function abdeckungText() {
    const e = ebenenDaten();
    const nDims = (e.dimensionen || []).length, alle = Z.daten.meta.dimensionen.length;
    if (nDims >= alle) return "";
    const namen = Z.daten.meta.dimensionen.filter((d) => e.dimensionen.includes(d.id)).map((d) => d.name).join(", ");
    return `Auf dieser Ebene liegen Daten für ${e.indikatoren.length} Indikatoren in ${nDims} von ${alle} Dimensionen vor (${namen}).`;
  }

  function ranglisteZeichnen() {
    const fc = Z.ebene === "kreis" ? Z.kreise : Z.gemeinden;
    const zeilen = fc.features
      .map((f) => ({ p: f.properties, w: skalenwert(f.properties.ags) }))
      .filter((z) => z.w != null)
      .sort((a, b) => b.w - a.w);
    $("#rang-titel").textContent = `Rangliste, ${zeilen.length} ${Z.ebene === "kreis" ? "Kreise" : "Gemeinden"}`;
    $("#rang").innerHTML = zeilen.map((z, i) => {
      const abw = Math.max(-30, Math.min(30, z.w - 100));
      const links = abw < 0 ? 50 + (abw / 30) * 50 : 50;
      const breite = Math.abs(abw / 30) * 50;
      return `<li><button type="button" data-ags="${z.p.ags}">
        <span class="rang-nr">${i + 1}</span>
        <span class="rang-name" title="${esc(anzeigeName(z.p, Z.ebene))}">${esc(anzeigeName(z.p, Z.ebene))}</span>
        <span class="rang-balken" aria-hidden="true"><i style="left:${links}%;width:${breite}%;background:${farbe(z.w)}"></i></span>
        <span class="rang-wert">${Z.merkmal.startsWith("ind:") ? "" : fmt(z.w, 0)}</span>
      </button></li>`;
    }).join("");
    $("#rang").querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => gebietOeffnen(b.dataset.ags, true)));
    ranglisteMarkieren();
  }
  function ranglisteMarkieren() {
    $("#rang").querySelectorAll("button").forEach((b) =>
      b.setAttribute("aria-current", b.dataset.ags === Z.auswahl ? "true" : "false"));
  }

  // ------------------------------------------------------------ Popup
  function gebietOeffnen(ags, zoomen) {
    const layer = Karte.layerNachAgs.get(ags);
    if (!layer) return;
    Z.auswahl = ags;
    const oeffnen = () => {
      if (!Karte.popup) {
        Karte.popup = L.popup({ maxWidth: 400, minWidth: 280, autoPanPaddingTopLeft: [20, 70], autoPanPaddingBottomRight: [20, 20] });
      }
      Karte.popup.setLatLng(layer.getBounds().getCenter()).setContent(popupInhalt(layer.feature.properties)).openOn(Karte.map);
      // openOn löst bei einem bereits offenen Popup "popupclose" aus → Auswahl wiederherstellen
      Z.auswahl = ags;
      reiterZeigen(Z.reiter);
      stileSetzen();
      ranglisteMarkieren();
    };
    if (zoomen) {
      Karte.map.closePopup();
      Z.auswahl = ags;
      stileSetzen();
      // erst zoomen, dann Popup öffnen, damit es vollständig sichtbar ins Bild geschoben wird
      Karte.map.once("moveend", oeffnen);
      Karte.map.fitBounds(layer.getBounds(), {
        maxZoom: Z.ebene === "kreis" ? 9.5 : 11,
        paddingTopLeft: [40, Math.round(Math.min(300, Karte.map.getSize().y * 0.42))], paddingBottomRight: [40, 30],
        animate: !reduziert,
      });
      // Falls sich der Ausschnitt nicht ändert, feuert kein moveend
      setTimeout(() => { if (!Karte.map.hasLayer(Karte.popup) || Z.auswahl !== ags) { Karte.map.off("moveend", oeffnen); oeffnen(); } }, reduziert ? 50 : 600);
    } else {
      oeffnen();
    }
  }

  function popupInhalt(p) {
    const g = gebietDaten(p.ags);
    const j = String(Z.jahr);
    const div = document.createElement("div");
    div.className = "pop";
    div.dataset.ags = p.ags;
    const anzahl = ebenenDaten().anzahl;
    div.innerHTML = `
      <div class="pop-kopf">
        <div><p class="pop-name">${esc(anzeigeName(p, Z.ebene))}</p>
        <p class="pop-art">${esc(unterzeile(p, Z.ebene))}</p></div>
        <div class="pop-wert"><strong>${fmt(g.index[j], 0)}</strong><span>Index ${Z.jahr}, Rang ${g.rang[j] ?? "–"} von ${anzahl}</span></div>
      </div>
      <div class="reiter" role="tablist">
        <button type="button" role="tab" data-reiter="profil">Profil</button>
        <button type="button" role="tab" data-reiter="verlauf">Verlauf</button>
        <button type="button" role="tab" data-reiter="kennzahlen">Kennzahlen</button>
      </div>
      <div class="pop-flaeche" role="tabpanel"></div>
      <p class="pop-notiz"></p>`;
    div.querySelectorAll(".reiter button").forEach((b) =>
      b.addEventListener("click", () => { Z.reiter = b.dataset.reiter; reiterZeigen(Z.reiter); }));
    return div;
  }

  function reiterZeigen(name) {
    const pop = document.querySelector(".leaflet-popup .pop");
    if (!pop) return;
    pop.querySelectorAll(".reiter button").forEach((b) => b.setAttribute("aria-selected", b.dataset.reiter === name));
    const flaeche = pop.querySelector(".pop-flaeche");
    const notiz = pop.querySelector(".pop-notiz");
    if (Karte.diagramm) { Karte.diagramm.destroy(); Karte.diagramm = null; }
    flaeche.innerHTML = "";
    flaeche.classList.toggle("tabelle", name === "kennzahlen");
    const ags = pop.dataset.ags;
    if (name === "profil") profilZeichnen(flaeche, notiz, ags);
    else if (name === "verlauf") verlaufZeichnen(flaeche, notiz, ags);
    else kennzahlenZeichnen(flaeche, notiz, ags);
    Karte.popup?.update();
  }

  function diagrammGrundlagen() {
    Chart.defaults.font.family = css("--schrift");
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css("--leise");
    Chart.defaults.animation = reduziert ? false : { duration: 300 };
  }

  function profilZeichnen(flaeche, notiz, ags) {
    const g = gebietDaten(ags);
    const j = String(Z.jahr);
    const dims = Z.daten.meta.dimensionen.filter((d) => g.dimensionen[d.id]?.[j] != null);
    const werte = dims.map((d) => g.dimensionen[d.id][j]);
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Profil: " + dims.map((d, i) => `${d.name} ${fmt(werte[i], 0)}`).join(", "));
    flaeche.appendChild(canvas);
    if (dims.length < 3) { profilBalken(canvas, dims, werte, notiz); return; }
    const min = Math.min(90, ...werte) - 6, max = Math.max(110, ...werte) + 6;
    Karte.diagramm = new Chart(canvas, {
      type: "radar",
      data: {
        labels: dims.map((d) => DIM_KURZ[d.id] || d.name),
        datasets: [
          { label: "Oberfranken", data: dims.map(() => 100), borderColor: css("--leise"), borderDash: [4, 4],
            borderWidth: 1.5, pointRadius: 0, fill: false },
          { label: "Gebiet", data: werte, borderColor: css("--s7"), backgroundColor: hexAlpha(css("--s7"), 0.22),
            borderWidth: 2.5, pointRadius: 3.5, pointBackgroundColor: werte.map(farbe), pointBorderColor: css("--tinte"), pointBorderWidth: 1, fill: true },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.r, 0)}` } } },
        scales: { r: {
          min: Math.floor(min / 5) * 5, max: Math.ceil(max / 5) * 5,
          ticks: { stepSize: 5, display: false },
          grid: { color: css("--linie") }, angleLines: { color: css("--linie") },
          pointLabels: { color: css("--tinte"), font: { size: 12, weight: "700" } },
        } },
      },
    });
    notiz.textContent = `Werte: ${dims.map((d, i) => `${DIM_KURZ[d.id] || d.name} ${fmt(werte[i], 0)}`).join(", ")}. Gestrichelt: Durchschnitt Oberfrankens (100); weiter außen ist günstiger.`;
  }

  function profilBalken(canvas, dims, werte, notiz) {
    Karte.diagramm = new Chart(canvas, {
      type: "bar",
      data: { labels: dims.map((d) => d.name), datasets: [{ data: werte.map((w) => w - 100), backgroundColor: werte.map(farbe), borderRadius: 3 }] },
      options: {
        indexAxis: "y", maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(werte[c.dataIndex], 0) } } },
        scales: {
          x: { min: -30, max: 30, grid: { color: (c) => (c.tick.value === 0 ? css("--leise") : css("--linie")) },
               ticks: { callback: (v) => fmt(100 + v, 0) } },
          y: { grid: { display: false }, ticks: { color: css("--tinte"), font: { weight: "700" } } },
        },
      },
    });
    notiz.textContent = `Werte: ${dims.map((d, i) => `${d.name} ${fmt(werte[i], 0)}`).join(", ")}. 100 = Durchschnitt Oberfrankens; rechts ist günstiger.`;
  }

  function verlaufZeichnen(flaeche, notiz, ags) {
    const g = gebietDaten(ags);
    const jahre = Z.daten.meta.jahre.map(String);
    let reihe, referenz, titel, einheitText = "";
    if (Z.merkmal === "index" || Z.merkmal.startsWith("dim:")) {
      reihe = jahre.map((j) => skalenwert(ags, Z.merkmal, j));
      referenz = jahre.map(() => 100);
      titel = merkmalName();
      notiz.textContent = `${titel} im Zeitverlauf. Gestrichelt: Durchschnitt Oberfrankens im jeweiligen Jahr (100).`;
    } else {
      const id = Z.merkmal.slice(4);
      const ind = indikator(id);
      reihe = jahre.map((j) => g.werte[id]?.[j] ?? null);
      referenz = jahre.map((j) => ebenenDaten().referenz[id]?.[j] ?? null);
      titel = ind.name;
      einheitText = ind.einheit;
      notiz.textContent = `${ind.name} (${ind.einheit}). Gestrichelt: Durchschnitt der ${Z.ebene === "kreis" ? "Kreise" : "Gemeinden"} Oberfrankens.`;
    }
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `${titel}: ` + jahre.map((j, i) => `${j} ${fmt(reihe[i])}`).join(", "));
    flaeche.appendChild(canvas);
    const aktiv = jahre.indexOf(String(Z.jahr));
    Karte.diagramm = new Chart(canvas, {
      type: "line",
      data: {
        labels: jahre,
        datasets: [
          { label: "Oberfranken", data: referenz, borderColor: css("--leise"), borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0 },
          { label: "Gebiet", data: reihe, borderColor: css("--s7"), borderWidth: 2.5, tension: 0.25,
            pointRadius: jahre.map((_, i) => (i === aktiv ? 5 : 2)), pointBackgroundColor: css("--s7") },
        ],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}${einheitText ? " " + einheitText : ""}` } } },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 8 } },
          y: { grid: { color: css("--linie") }, ticks: { callback: (v) => fmt(v, Number.isInteger(v) ? 0 : 1) } },
        },
      },
    });
  }

  function kennzahlenZeichnen(flaeche, notiz, ags) {
    const g = gebietDaten(ags);
    const j = String(Z.jahr);
    const zeile = (ind, wert, ref, punktFarbe) => `<tr>
      <th scope="row">${esc(ind.name)}</th>
      <td>${esc(mitEinheit(wert, ind))}<span class="punkt" style="background:${punktFarbe}" aria-hidden="true"></span></td>
      <td class="einheit">${esc(mitEinheit(ref, ind))}</td></tr>`;

    let html = `<table class="kennzahlen"><colgroup><col class="c-name"><col class="c-wert"><col class="c-ref"></colgroup><thead><tr><th>${Z.jahr}</th><th>Wert</th><th>Ø Oberfr.</th></tr></thead><tbody>`;
    for (const id of ebenenDaten().indikatoren) {
      const ind = indikator(id);
      html += zeile(ind, g.werte[id]?.[j], ebenenDaten().referenz[id]?.[j], farbe(skalenwert(ags, "ind:" + id)));
    }
    if (Z.ebene === "gemeinde") {
      const kAgs = ags.slice(0, 5);
      const kg = gebietDaten(kAgs, "kreis");
      const nurKreis = Z.daten.kreis.indikatoren.filter((id) => !Z.daten.gemeinde.indikatoren.includes(id));
      if (kg && nurKreis.length) {
        html += `<tr class="zwischen"><th colspan="3">Nur auf Kreisebene verfügbar (Wert des Kreises)</th></tr>`;
        for (const id of nurKreis) {
          html += zeile(indikator(id), kg.werte[id]?.[j], Z.daten.kreis.referenz[id]?.[j],
            farbe(skalenwert(kAgs, "ind:" + id, Z.jahr, "kreis")));
        }
      }
    }
    flaeche.innerHTML = html + "</tbody></table>";
    notiz.textContent = "Der farbige Punkt zeigt, ob der Wert günstiger (grün) oder ungünstiger (violett) als der Durchschnitt ist.";
  }

  function hexAlpha(farbe, a) {
    const m = farbe.match(/^#([0-9a-f]{6})$/i);
    if (!m) return farbe;
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  }

  // ------------------------------------------------------------ Gesamt
  function aktualisieren() {
    stileSetzen();
    legendeZeichnen();
    ranglisteZeichnen();
    if (Z.auswahl && Karte.map.hasLayer(Karte.popup)) {
      const p = Karte.layerNachAgs.get(Z.auswahl)?.feature.properties;
      if (p) {
        Karte.popup.setContent(popupInhalt(p));
        reiterZeigen(Z.reiter);
      }
    }
  }

  function fussZeichnen() {
    const m = Z.daten.meta;
    const eintraege = new Map();
    for (const ebene of ["kreis", "gemeinde"]) {
      for (const [id, q] of Object.entries(m.quellen?.[ebene] || {})) {
        const ind = indikator(id);
        if (!ind) continue;
        const text = q.code ? `${q.quelle}, ${q.code}${q.feld ? " (" + q.feld + ")" : ""}` : q.quelle;
        const schluessel = `${ind.name}|${text}`;
        const alt = eintraege.get(schluessel);
        eintraege.set(schluessel, { name: ind.name, text, ebenen: [...(alt?.ebenen || []), ebene === "kreis" ? "Kreise" : "Gemeinden"] });
      }
    }
    $("#quellen").innerHTML = [...eintraege.values()]
      .map((e) => `<li>${esc(e.name)}: ${esc(e.text)}, ${esc(e.ebenen.join(" und "))}</li>`).join("")
      + `<li>Amtliche Statistik: © Statistische Ämter des Bundes und der Länder, dl-de/by-2-0</li>`;
    const datum = new Date(m.erstellt).toLocaleDateString("de-DE", { day: "numeric", month: "long", year: "numeric" });
    $("#stand").textContent = `Datenstand: ${datum}`;
    $("#demo-hinweis").hidden = !m.demo;
  }

  async function start() {
    try {
      const { kreise, gemeinden, werte } = await laden();
      Z.kreise = kreise; Z.gemeinden = gemeinden; Z.daten = werte;
      Z.jahr = Math.max(...werte.meta.jahre);
      diagrammGrundlagen();
      karteAnlegen();
      merkmalOptionenAufbauen();
      suchlisteAufbauen();
      steuerungVerbinden();
      flaechenZeichnen();
      fussZeichnen();
      aktualisieren();
      $("#lade").hidden = true;
      // Farbschema-Wechsel des Systems übernehmen
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        diagrammGrundlagen(); stileSetzen(); ranglisteZeichnen();
        if (Z.auswahl) reiterZeigen(Z.reiter);
      });
    } catch (e) {
      const lade = $("#lade");
      lade.classList.add("fehler");
      lade.textContent = `Die Daten konnten nicht geladen werden (${e.message}). Die Seite muss über einen Webserver aufgerufen werden, nicht als lokale Datei.`;
      console.error(e);
    }
  }

  start();
})();
