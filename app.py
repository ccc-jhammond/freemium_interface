import io
import zipfile
from datetime import date, timedelta

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Page setup (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Coupa Invoice Downloader",  # Browser tab title
    page_icon="📄",                         # Tab icon - can replace with corporate logo
    layout="wide",                          # Full-width layout
    initial_sidebar_state="collapsed",      # Hide sidebar
)

BRAND_HEX = "#ff5500"  # update to your brand HEX colour

# ---------------------------------------------------------------------------
# Custom CSS
# NOTE: CSS comments must use /* ... */ -- a "#" comment inside <style>
# breaks the rule and the button colour will not apply.
# ---------------------------------------------------------------------------
st.markdown(
    f"""
<style>
    .stButton>button {{
        background-color: {BRAND_HEX};  /* brand colour button */
        color: #ffffff;                 /* white text */
        font-weight: bold;
        border: none;
    }}
    .stButton>button:hover {{
        filter: brightness(0.92);
        color: #ffffff;
    }}
    .top-right {{
        position: absolute;
        top: 10px;
        right: 20px;
        color: {BRAND_HEX};
    }}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="top-right">Coupa Invoice Downloader</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Coupa helpers
# ---------------------------------------------------------------------------
def get_token(base_url: str, client_id: str, client_secret: str, scope: str) -> str:
    """OAuth2 client-credentials token from Coupa."""
    resp = requests.post(
        f"{base_url}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_invoices(base_url: str, token: str, start: date, end: date, limit: int = 50):
    """Page through invoices created in the date range."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    offset, results = 0, []
    while True:
        resp = requests.get(
            f"{base_url}/api/invoices",
            headers=headers,
            params={
                "created-at[gt_or_eq]": start.isoformat(),
                "created-at[lt_or_eq]": end.isoformat(),
                "limit": limit,
                "offset": offset,
            },
            timeout=60,
        )
        resp.raise_for_status()
        page = resp.json()
        results.extend(page)
        if len(page) < limit:
            return results
        offset += limit


def download_invoice_file(base_url: str, token: str, invoice_id: int) -> bytes:
    """TODO: confirm the image-scan/attachment endpoint for your Coupa release."""
    raise NotImplementedError("Wire up the invoice file endpoint for your instance.")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("📄 Coupa Invoice Downloader")

with st.form("downloader"):
    c1, c2 = st.columns(2)
    with c1:
        base_url = st.text_input("Coupa instance URL", placeholder="https://yourcompany.coupahost.com")
        client_id = st.text_input("OAuth client ID")
        client_secret = st.text_input("OAuth client secret", type="password")
    with c2:
        scope = st.text_input("OAuth scope", value="core.invoice.read")
        start = st.date_input("From", value=date.today() - timedelta(days=30))
        end = st.date_input("To", value=date.today())
    submitted = st.form_submit_button("Fetch invoices")

if submitted:
    if not all([base_url, client_id, client_secret]):
        st.error("Instance URL, client ID, and client secret are required.")
    else:
        try:
            with st.spinner("Authenticating and fetching invoices..."):
                token = get_token(base_url.rstrip("/"), client_id, client_secret, scope)
                st.session_state["invoices"] = list_invoices(base_url.rstrip("/"), token, start, end)
                st.session_state["token"] = token
                st.session_state["base_url"] = base_url.rstrip("/")
        except requests.HTTPError as e:
            st.error(f"Coupa returned an error: {e.response.status_code} {e.response.text[:300]}")
        except Exception as e:
            st.error(f"Something went wrong: {e}")

invoices = st.session_state.get("invoices")
if invoices is not None:
    st.success(f"Found {len(invoices)} invoices")
    st.dataframe(
        [
            {
                "id": i.get("id"),
                "invoice #": i.get("invoice-number"),
                "supplier": (i.get("supplier") or {}).get("name"),
                "status": i.get("status"),
                "total": i.get("total-with-taxes"),
            }
            for i in invoices
        ],
        use_container_width=True,
    )

    if invoices and st.button("Download all as ZIP"):
        buf = io.BytesIO()
        try:
            with zipfile.ZipFile(buf, "w") as zf, st.spinner("Building ZIP..."):
                for inv in invoices:
                    data = download_invoice_file(
                        st.session_state["base_url"], st.session_state["token"], inv["id"]
                    )
                    zf.writestr(f"{inv.get('invoice-number', inv['id'])}.pdf", data)
            st.download_button("Save ZIP", buf.getvalue(), "coupa_invoices.zip", "application/zip")
        except NotImplementedError as e:
            st.warning(str(e))
