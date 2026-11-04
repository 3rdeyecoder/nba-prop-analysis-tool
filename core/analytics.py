"""Google Analytics 4 tag.

st.html(..., unsafe_allow_javascript=True) runs the script on the app page itself (not in an
iframe). Streamlit reruns app.py on every click, so the script guards itself and loads the
Google tag only once per browser visit. Switching NBA/NFL/MLB changes the URL without a page
reload; GA4's "page changes based on browser history events" setting counts those as page views.

Local runs (localhost) are skipped so your own testing doesn't show up in your reports.
"""
import streamlit as st

from core.config import GA_MEASUREMENT_ID

_TAG = """
<script>
(function () {
  if (window.__playmakerGaLoaded) return;      // already loaded on this visit
  window.__playmakerGaLoaded = true;
  var s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=__ID__";
  document.head.appendChild(s);
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", "__ID__");
})();
</script>
"""


def _is_local() -> bool:
    try:
        host = (st.context.headers.get("host") or "").lower()
    except Exception:  # noqa: BLE001 - no request context (e.g. tests)
        return True
    # No host (tests, scripts) or a local address -> don't track.
    return not host or host.startswith(("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))


def add_google_analytics() -> None:
    if not GA_MEASUREMENT_ID or _is_local():
        return
    st.html(_TAG.replace("__ID__", GA_MEASUREMENT_ID), unsafe_allow_javascript=True)


_EVENT = """
<script>
(function () {
  var key = __KEY__;
  try {                                   // send once per browser tab, even if the page reruns or reloads
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
  } catch (e) {
    if (window[key]) return;
    window[key] = true;
  }
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag("event", __NAME__, __PARAMS__);
})();
</script>
"""


def track_event(name: str, params: dict, once_key: str) -> None:
    """Send a Google Analytics event (e.g. a finished Call It puzzle). Skipped locally."""
    import json

    if not GA_MEASUREMENT_ID or _is_local():
        return
    html = (_EVENT.replace("__KEY__", json.dumps(f"pl_ev_{once_key}"))
                  .replace("__NAME__", json.dumps(name))
                  .replace("__PARAMS__", json.dumps(params)))
    st.html(html, unsafe_allow_javascript=True)
