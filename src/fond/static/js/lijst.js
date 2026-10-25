"use strict";
// Afvinken gebeurt op je telefoon zelf: in de winkel heb je niet altijd bereik.
(function () {
  const lijst = document.querySelector("[data-lijst]");
  const sleutel = "fond-lijst-" + lijst.dataset.lijst;
  let af;
  try { af = new Set(JSON.parse(localStorage.getItem(sleutel) || "[]")); } catch (e) { af = new Set(); }
  const knoppen = lijst.querySelectorAll("[data-item]");
  const zet = (k) => { const aan = af.has(k.dataset.item); k.classList.toggle("aan", aan); k.setAttribute("aria-pressed", aan); };
  knoppen.forEach((k) => {
    zet(k);
    k.addEventListener("click", () => {
      af.has(k.dataset.item) ? af.delete(k.dataset.item) : af.add(k.dataset.item);
      try { localStorage.setItem(sleutel, JSON.stringify([...af])); } catch (e) {}
      zet(k);
    });
  });
  document.querySelector("[data-wis-vinkjes]").addEventListener("click", () => {
    af.clear(); try { localStorage.removeItem(sleutel); } catch (e) {} knoppen.forEach(zet);
  });
  document.querySelector("[data-kopieer]").addEventListener("click", async (e) => {
    const regels = [];
    lijst.querySelectorAll(".afdeling").forEach((sec) => {
      regels.push("", sec.querySelector("h2").firstChild.textContent.trim());
      sec.querySelectorAll(".boodschap").forEach((b) => {
        regels.push("- " + b.querySelector(".boodschap-naam").textContent + " (" + b.querySelector(".boodschap-nl").textContent.trim() + ")");
      });
    });
    try { await navigator.clipboard.writeText(regels.join("\n").trim()); e.target.textContent = "Gekopieerd ✓"; }
    catch (err) { e.target.textContent = "Kopiëren lukte niet"; }
  });
})();
