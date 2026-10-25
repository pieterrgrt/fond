// Kookmodus: stap voor stap, timers die doorlopen, en een scherm dat aan blijft.
// Alle staat (welke stap, lopende timers, afgevinkte ingrediënten) staat op het
// toestel zelf, zodat herladen of even wegklikken niets kwijtmaakt.
"use strict";

(function () {
  const koken = document.querySelector(".koken");
  if (!koken) return;
  const les = koken.dataset.les;
  const dias = [...koken.querySelectorAll("[data-dia]")];
  const teller = koken.querySelector("[data-teller]");
  const vorige = koken.querySelector("[data-vorige]");
  const volgende = koken.querySelector("[data-volgende]");
  const timerBak = koken.querySelector("[data-timers]");

  const opslag = {
    lees(sleutel, standaard) {
      try { return JSON.parse(localStorage.getItem(`fond-${sleutel}-${les}`)) ?? standaard; } catch (e) { return standaard; }
    },
    schrijf(sleutel, waarde) {
      try { localStorage.setItem(`fond-${sleutel}-${les}`, JSON.stringify(waarde)); } catch (e) {}
    },
  };

  // --- Stappen ---
  let huidige = Math.min(opslag.lees("stap", 0), dias.length - 1);

  function toon(index) {
    huidige = Math.max(0, Math.min(index, dias.length - 1));
    dias.forEach((dia, i) => { dia.hidden = i !== huidige; });
    teller.textContent = String(huidige + 1);
    vorige.disabled = huidige === 0;
    volgende.hidden = huidige === dias.length - 1;
    vorige.style.gridColumn = volgende.hidden ? "1 / -1" : "";
    opslag.schrijf("stap", huidige);
    dias[huidige].scrollTop = 0;
    window.scrollTo(0, 0);
  }
  vorige.addEventListener("click", () => toon(huidige - 1));
  volgende.addEventListener("click", () => toon(huidige + 1));
  addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea")) return;
    if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); toon(huidige + 1); }
    if (e.key === "ArrowLeft") toon(huidige - 1);
  });

  // Vegen met een knokkel of pols: horizontaal genoeg, en niet te verticaal.
  let startX = null, startY = null;
  koken.addEventListener("touchstart", (e) => { startX = e.touches[0].clientX; startY = e.touches[0].clientY; }, { passive: true });
  koken.addEventListener("touchend", (e) => {
    if (startX === null) return;
    const dx = e.changedTouches[0].clientX - startX, dy = e.changedTouches[0].clientY - startY;
    if (Math.abs(dx) > 70 && Math.abs(dx) > 2 * Math.abs(dy)) toon(huidige + (dx < 0 ? 1 : -1));
    startX = null;
  }, { passive: true });

  // --- Mise en place afvinken ---
  const klaar = new Set(opslag.lees("klaar", []));
  koken.querySelectorAll("[data-klaar]").forEach((knop) => {
    const zet = () => {
      knop.classList.toggle("aan", klaar.has(knop.dataset.klaar));
      knop.setAttribute("aria-pressed", klaar.has(knop.dataset.klaar));
    };
    zet();
    knop.addEventListener("click", () => {
      klaar.has(knop.dataset.klaar) ? klaar.delete(knop.dataset.klaar) : klaar.add(knop.dataset.klaar);
      opslag.schrijf("klaar", [...klaar]);
      zet();
    });
  });

  // --- Timers ---
  // Een timer onthoudt zijn eindtijd (niet de resterende tijd), zodat hij klopt
  // ook als de telefoon even op slot ging of de pagina herladen werd.
  let timers = opslag.lees("timers", []);
  let audio = null;

  function geluid() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const nu = audio.currentTime;
      [0, 0.35, 0.7].forEach((t) => {
        const osc = audio.createOscillator(), gain = audio.createGain();
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.0001, nu + t);
        gain.gain.exponentialRampToValueAtTime(0.4, nu + t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, nu + t + 0.25);
        osc.connect(gain).connect(audio.destination);
        osc.start(nu + t);
        osc.stop(nu + t + 0.3);
      });
    } catch (e) {}
  }

  function opmaak(ms) {
    const s = Math.max(0, Math.ceil(ms / 1000));
    const u = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return (u ? `${u}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(r).padStart(2, "0")}`;
  }

  function bewaar() { opslag.schrijf("timers", timers); }

  function teken() {
    const nu = Date.now();
    timerBak.replaceChildren(...timers.map((t) => {
      const rest = t.pauze ?? t.eind - nu;
      const af = rest <= 0;
      const el = document.createElement("div");
      el.className = "timer" + (af ? " af" : "") + (t.pauze != null ? " pauze" : "");
      el.innerHTML = `<span class="timer-label"></span><span class="timer-tijd">${af ? "klaar!" : opmaak(rest)}</span>`;
      el.querySelector(".timer-label").textContent = t.label;
      const knoppen = document.createElement("span");
      knoppen.className = "timer-knoppen";
      if (!af) {
        const p = document.createElement("button");
        p.type = "button"; p.textContent = t.pauze != null ? "▶" : "❚❚";
        p.setAttribute("aria-label", t.pauze != null ? "Verder" : "Pauze");
        p.onclick = () => {
          if (t.pauze != null) { t.eind = Date.now() + t.pauze; t.pauze = null; } else { t.pauze = t.eind - Date.now(); }
          bewaar(); teken();
        };
        const plus = document.createElement("button");
        plus.type = "button"; plus.textContent = "+1"; plus.setAttribute("aria-label", "Een minuut erbij");
        plus.onclick = () => { if (t.pauze != null) t.pauze += 60000; else t.eind += 60000; bewaar(); teken(); };
        knoppen.append(p, plus);
      }
      const weg = document.createElement("button");
      weg.type = "button"; weg.textContent = "✕"; weg.setAttribute("aria-label", af ? "Uitzetten" : "Stoppen");
      weg.onclick = () => { timers = timers.filter((x) => x !== t); bewaar(); teken(); };
      knoppen.append(weg);
      el.append(knoppen);
      return el;
    }));
    timerBak.hidden = timers.length === 0;
  }

  function tik() {
    const nu = Date.now();
    let afgelopen = false;
    timers.forEach((t) => {
      if (t.pauze == null && t.eind <= nu && !t.gemeld) { t.gemeld = true; afgelopen = true; }
    });
    if (afgelopen) { bewaar(); }
    // Blijf piepen zolang er een afgelopen timer niet is uitgezet (elke 4 s).
    const rinkelt = timers.some((t) => t.gemeld && t.pauze == null);
    if (rinkelt && (afgelopen || nu - (tik.laatst || 0) > 4000)) {
      tik.laatst = nu;
      geluid();
      navigator.vibrate?.([300, 150, 300, 150, 300]);
    }
    teken();
  }

  koken.querySelectorAll("[data-timer]").forEach((knop) => {
    knop.addEventListener("click", () => {
      // Browsers spelen pas geluid af na een tik; dit is die tik.
      try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); } catch (e) {}
      const ms = Number(knop.dataset.timer) * 1000;
      timers.push({ label: knop.dataset.label, eind: Date.now() + ms, pauze: null });
      bewaar();
      teken();
    });
  });

  setInterval(tik, 250);
  tik();

  // --- Scherm aan houden (Wake Lock API) ---
  const wlKnop = koken.querySelector("[data-wakelock]");
  const wlTekst = koken.querySelector("[data-wakelock-tekst]");
  let slot = null;

  async function houdAan() {
    if (!("wakeLock" in navigator)) {
      wlKnop.classList.add("uit");
      wlTekst.textContent = "let op";
      wlKnop.title = "Deze browser kan het scherm niet aan houden. Zet tijdelijk de automatische schermvergrendeling uit.";
      return;
    }
    try {
      slot = await navigator.wakeLock.request("screen");
      wlKnop.classList.remove("uit");
      wlTekst.textContent = "scherm aan";
      slot.addEventListener("release", () => {
        wlKnop.classList.add("uit");
        wlTekst.textContent = "scherm uit";
      });
    } catch (e) {
      // Bijvoorbeeld: batterijbesparing, of de pagina was niet zichtbaar.
      wlKnop.classList.add("uit");
      wlTekst.textContent = "scherm uit";
    }
  }
  wlKnop.addEventListener("click", houdAan);
  // Het slot vervalt als je wegklikt; bij terugkomen opnieuw aanvragen.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") { houdAan(); tik(); }
  });
  houdAan();

  // Klaar met koken: de volgende keer begin je weer bij het begin.
  koken.querySelector(".dia-eind a")?.addEventListener("click", () => {
    opslag.schrijf("stap", 0);
    opslag.schrijf("klaar", []);
  });

  toon(huidige);
})();
