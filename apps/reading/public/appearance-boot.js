// Parser-blocking appearance restoration, permitted by the self-origin CSP.
(function () {
  var d = document.documentElement;
  var mm = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
  function read(k) {
    try {
      return window.localStorage.getItem(k);
    } catch (e) {
      return null;
    }
  }
  function apply() {
    var p = d.getAttribute("data-theme-pref");
    var dark = p === "dark" || (p !== "light" && !!mm && mm.matches);
    d.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#211E19" : "#F3EBDD");
  }
  var t = read("antiek.theme");
  d.setAttribute("data-theme-pref", t === "light" || t === "dark" ? t : "system");
  var m = read("antiek.motion");
  if (m === "reduce" || m === "full") d.setAttribute("data-motion", m);
  d.setAttribute("data-reading-light", read("antiek.reading-light") === "soft" ? "soft" : "standard");
  apply();
  if (mm && mm.addEventListener) mm.addEventListener("change", apply);
})();
