"""Authentication and login management for LINKFMS users."""

import streamlit as st
from datetime import datetime, timedelta
import hashlib
from typing import Optional, Tuple


# NOTE: Login is validated against LINKFMS API (HTTP Basic Auth).
# We intentionally do NOT use a local username/password database.



class LoginManager:
    """Manages user authentication and session management."""
    
    SESSION_TIMEOUT = 3600  # 1 hour in seconds
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password for security."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_credentials(userid: str, password: str) -> Tuple[bool, Optional[dict]]:
        """Verify user credentials by attempting an authenticated LINKFMS GraphQL request.

        LINKFMS authentication is done using HTTP Basic Auth at the GraphQL endpoint.
        We validate credentials by calling a lightweight query and checking for auth errors.
        """
        try:
            import requests
            from requests.auth import HTTPBasicAuth

            API_URL = "https://www.linkfms.com/fms/graphql"

            # Lightweight query: request __typename (no business data)
            # If auth is invalid, LINKFMS will return GraphQL/HTTP error.
            query = """
            query q { __typename }
            """

            resp = requests.post(
                API_URL,
                json={"operationName": "q", "query": query, "variables": {}},
                auth=HTTPBasicAuth(userid, password),
                timeout=20,
            )

            if resp.status_code != 200:
                return False, None

            data = resp.json()
            if isinstance(data, dict) and data.get("errors"):
                # Most auth failures show up as GraphQL errors.
                return False, None

            # Success: we store minimal profile (no role from API available here)
            return True, {
                "userid": userid,
                "name": userid,
                "role": "LINKFMS User",
                "email": "",
                "login_time": datetime.now(),
                "username": userid,
                "password": password,
            }
        except Exception:
            return False, None

    
    @staticmethod
    def initialize_session() -> None:
        """Initialize session state variables."""
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'user_info' not in st.session_state:
            st.session_state.user_info = None
        if 'login_time' not in st.session_state:
            st.session_state.login_time = None
    
    @staticmethod
    def login_user(userid: str, password: str) -> bool:
        """
        Authenticate and login user.
        
        Args:
            userid: Username/User ID
            password: Password
            
        Returns:
            True if login successful, False otherwise
        """
        is_valid, user_info = LoginManager.verify_credentials(userid, password)
        
        if is_valid:
            st.session_state.authenticated = True
            st.session_state.user_info = user_info
            st.session_state.login_time = datetime.now()
            return True
        
        return False
    
    @staticmethod
    def logout_user() -> None:
        """Logout current user."""
        st.session_state.authenticated = False
        st.session_state.user_info = None
        st.session_state.login_time = None
    
    @staticmethod
    def is_authenticated() -> bool:
        """Check if user is currently authenticated."""
        return st.session_state.get('authenticated', False)
    
    @staticmethod
    def get_current_user() -> Optional[dict]:
        """Get current authenticated user info."""
        return st.session_state.get('user_info', None)
    
    @staticmethod
    def check_session_timeout() -> bool:
        """
        Check if session has timed out.
        
        Returns:
            True if session is still valid, False if timed out
        """
        if not st.session_state.get('authenticated', False):
            return False
        
        login_time = st.session_state.get('login_time')
        if login_time is None:
            return False
        
        elapsed = (datetime.now() - login_time).total_seconds()
        
        if elapsed > LoginManager.SESSION_TIMEOUT:
            LoginManager.logout_user()
            return False
        
        return True


def render_login_page() -> None:
    """Render the login page."""
    # Initialize session
    LoginManager.initialize_session()
    
    # Set page config
    st.set_page_config(
        page_title="LINKFMS Login",
        page_icon="🔐",
        layout="centered"
    )
    
    # Custom CSS for login page
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px;
            margin: 50px auto;
            padding: 40px;
            border-radius: 10px;
            background-color: #f8f9fa;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-title {
            font-size: 2.5em;
            margin: 0;
            color: #1f77b4;
        }
        .login-subtitle {
            color: #666;
            margin: 10px 0 0 0;
            font-size: 1.1em;
        }
        .credentials-info {
            background-color: #e3f2fd;
            border-left: 4px solid #1976d2;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .login-footer {
            text-align: center;
            margin-top: 20px;
            color: #999;
            font-size: 0.9em;
        }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div class="login-container">
            <div class="login-header">
                <h1 class="login-title">🔐 LINKFMS</h1>
                <p class="login-subtitle">EV Telemetry Analysis Platform</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Login form
        st.markdown("### Login")
        
        userid = st.text_input(
            "User ID",
            placeholder="Enter your LINKFMS User ID",
            help="Your LINKFMS username"
        )
        
        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter your password",
            help="Your LINKFMS password"
        )
        
        login_button = st.button(
            "🔓 Login",
            use_container_width=True,
            type="primary"
        )
        
        if login_button:
            if not userid or not password:
                st.error("❌ Please enter both User ID and Password")
            else:
                if LoginManager.login_user(userid, password):
                    st.success("✓ Login successful! Redirecting...")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Invalid User ID or Password. Please try again.")
        
        # Demo credentials info
        st.markdown("""
        <div class="credentials-info">
            <strong>Demo Credentials:</strong><br>
            • <strong>Admin:</strong> admin / linkfms@2024<br>
            • <strong>Analyst:</strong> analyst / analyst@2024<br>
            • <strong>Technician:</strong> technician / tech@2024
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="login-footer">
            <p>LINKFMS EV Telemetry Analysis Platform | v1.0<br>
            © 2026 LINKFMS. All rights reserved.</p>
        </div>
        """, unsafe_allow_html=True)


def render_user_profile() -> None:
    """Render user profile in sidebar."""
    user = LoginManager.get_current_user()
    
    if user:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 👤 User Profile")
        
        col1, col2 = st.sidebar.columns([3, 1])
        
        with col1:
            st.sidebar.write(f"**Name:** {user['name']}")
            st.sidebar.write(f"**Role:** {user['role']}")
            st.sidebar.write(f"**Email:** {user['email']}")
        
        with col2:
            if st.sidebar.button("🚪 Logout", use_container_width=True):
                LoginManager.logout_user()
                st.rerun()
        
        # Session info
        login_time = st.session_state.get('login_time')
        if login_time:
            elapsed = (datetime.now() - login_time).total_seconds()
            minutes = int(elapsed // 60)
            st.sidebar.caption(f"Logged in for: {minutes}m {int(elapsed % 60)}s")


def require_login(func):
    """Decorator to require login for accessing functions."""
    def wrapper(*args, **kwargs):
        if not LoginManager.is_authenticated():
            render_login_page()
            st.stop()
        
        # Check session timeout
        if not LoginManager.check_session_timeout():
            st.warning("⚠️ Your session has expired. Please login again.")
            render_login_page()
            st.stop()
        
        return func(*args, **kwargs)
    
    return wrapper


def get_user_role() -> Optional[str]:
    """Get current user's role."""
    user = LoginManager.get_current_user()
    return user['role'] if user else None


def has_permission(required_role: str) -> bool:
    """Check if user has required role/permission."""
    user = LoginManager.get_current_user()
    if not user:
        return False
    
    # Role hierarchy
    roles = {
        'Administrator': 3,
        'Data Analyst': 2,
        'Technician': 1
    }
    
    user_level = roles.get(user['role'], 0)
    required_level = roles.get(required_role, 0)
    
    return user_level >= required_level
