# TLD/XOPS VISUALIZATION TOOL - Agent Task Notes

Goal: Streamlit app with a **login page first**.
- App title: **TLD/XOPS VISUALIZATION TOOL**
- Fields: username/password (same as LINKFMS creds)
- After successful login: show the main visualization UI.

Current status:
- `agents/linkfms_fetch_app.py` needs repair.
- `agents/linkfms_fetch_app.py.backup` contains a prior implementation with `show_login_page()` and `show_main_app()`.

Next implementation approach:
1. Ensure `agents/linkfms_fetch_app.py` has syntactically correct Streamlit code.
2. Set title to **TLD/XOPS VISUALIZATION TOOL**.
3. Keep login flow as the entry screen.
4. After login, render the existing telemetry/DTC/KPI/visualization controls.

