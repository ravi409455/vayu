// Paint the saved look before the app loads (no flash). Signed-out pages stay Light.
// A file, not an inline script, so the content rules (CSP) can forbid inline scripts.
try {
  var p = location.pathname, t = localStorage.getItem("vayu:theme");
  if (p !== "/login" && p.indexOf("/report/verify") !== 0 && p.indexOf("/zip") !== 0 && (t === "light" || t === "dark" || t === "system")) {
    var d = t === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : t;
    document.documentElement.dataset.theme = d;
    document.documentElement.style.colorScheme = d;
  }
} catch (e) {}
