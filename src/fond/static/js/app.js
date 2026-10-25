// Fond — kleine dingen die de server niet kan doen: thema, offline-status en
// concepten van je reflectie bewaren. Werkt alles zonder dit script, dan ook goed.
"use strict";

(function () {
  const root = document.documentElement;

  // --- Licht/donker wisselen (onthouden op dit toestel) ---
  document.querySelectorAll("[data-thema-knop]").forEach((knop) => {
    knop.addEventListener("click", () => {
      const donkerNu = root.dataset.thema
        ? root.dataset.thema === "donker"
        : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.thema = donkerNu ? "licht" : "donker";
      try { localStorage.setItem("fond-thema", root.dataset.thema); } catch (e) {}
    });
  });

  // --- Bevestigen voor iets verdwijnt (data-bevestig="vraag") ---
  document.querySelectorAll("form[data-bevestig]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!confirm(form.dataset.bevestig)) event.preventDefault();
    });
  });

  // --- Offline-indicator ---
  function toonStatus() {
    const offline = !navigator.onLine;
    document.querySelectorAll(".offline-label, .offline-uitleg").forEach((el) => { el.hidden = !offline; });
  }
  addEventListener("online", toonStatus);
  addEventListener("offline", toonStatus);
  toonStatus();

  // --- Concept van een reflectie bewaren, zodat niets verloren gaat ---
  document.querySelectorAll("form[data-concept]").forEach((form) => {
    const sleutel = "fond-concept-" + form.dataset.concept;
    const velden = form.querySelectorAll("textarea, input[type=date], input[type=number], input[type=radio]");
    try {
      const concept = JSON.parse(localStorage.getItem(sleutel) || "null");
      if (concept) {
        velden.forEach((veld) => {
          if (!(veld.name in concept)) return;
          if (veld.type === "radio") veld.checked = concept[veld.name] === veld.value;
          else veld.value = concept[veld.name];
        });
      }
    } catch (e) {}
    form.addEventListener("input", () => {
      const data = {};
      new FormData(form).forEach((waarde, naam) => { if (typeof waarde === "string") data[naam] = waarde; });
      try { localStorage.setItem(sleutel, JSON.stringify(data)); } catch (e) {}
    });
    form.addEventListener("submit", (event) => {
      if (!navigator.onLine) {
        event.preventDefault();
        toonStatus();
        form.querySelector(".offline-uitleg")?.scrollIntoView({ block: "center" });
        return;
      }
      try { localStorage.removeItem(sleutel); } catch (e) {}
    });
  });

  // --- Service worker: offline werken ---
  if ("serviceWorker" in navigator && location.pathname !== "/login") {
    navigator.serviceWorker.register("/sw.js").then(async () => {
      const sw = await navigator.serviceWorker.ready;
      // Hooguit eens per uur alle open lessen opnieuw op het toestel zetten.
      let laatst = 0;
      try { laatst = Number(localStorage.getItem("fond-bijgewerkt") || 0); } catch (e) {}
      if (navigator.onLine && Date.now() - laatst > 3600 * 1000) {
        sw.active?.postMessage("bijwerken");
        try { localStorage.setItem("fond-bijgewerkt", String(Date.now())); } catch (e) {}
      }
    }).catch(() => {});
  }
  document.querySelectorAll('form[action="/uitloggen"]').forEach((form) => {
    form.addEventListener("submit", () => {
      navigator.serviceWorker?.controller?.postMessage("vergeten");
      try { localStorage.removeItem("fond-bijgewerkt"); } catch (e) {}
    });
  });
})();
