"""Login page agent for Streamlit.

Responsibilities:
- Render a login UI
- Validate credentials via LoginManager
- Flip session_state.authenticated + user_info

This module is used by agents/linkfms_fetch_app.py so that the login page is isolated
from the main telemetry/DTC/KPI UI.
"""

import streamlit as st

from utils.login_auth import LoginManager


def render_login_page(*, title: str = "TLD/XOPS VISUALIZATION TOOL") -> None:
    """Render the login screen.

    Expected session_state keys (set/used by utils.login_auth.LoginManager):
      - authenticated: bool
      - user_info: dict (contains name, role, userid)

    Side effects:
      - On successful login: sets authenticated + user_info and triggers st.rerun().
    """

    st.title(title)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("<p style='text-align: center; color: gray;'>Secure Login</p>", unsafe_allow_html=True)
        st.markdown("---")

        st.subheader("Login")

        username = st.text_input(
            "Username",
            placeholder="Enter your LINKFMS username",
            key="login_username",
        )
        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter your LINKFMS password",
            key="login_password",
        )

        col_login_btn1, col_login_btn2 = st.columns(2)

        with col_login_btn1:
            if st.button("🔓 Login", use_container_width=True, type="primary"):
                if not username or not password:
                    st.error("❌ Please enter both username and password")
                else:
                    if LoginManager.login_user(username, password):
                        st.success(f"✅ Welcome, {st.session_state.user_info['name']}!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password. Please try again.")

        with col_login_btn2:
            st.markdown("")
            st.markdown("")
            st.markdown("*Secure connection to LINKFMS API*")

        st.markdown("---")
        st.markdown(
            "<p style='text-align: center; font-size: 12px; color: gray;'>"
            "🔒 Your credentials are encrypted and not stored. | For support, contact: admin@linkfms.com"
            "</p>",
            unsafe_allow_html=True,
        )

