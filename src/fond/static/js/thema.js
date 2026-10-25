// Thema vóór het tekenen zetten, zodat de pagina niet eerst licht opflitst.
// Bewust een apart, klein en blokkerend script (geen inline script: zie de CSP).
try {
  const t = localStorage.getItem("fond-thema");
  if (t) document.documentElement.dataset.thema = t;
} catch (e) {}
