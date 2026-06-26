# LINKFMS Login System - Documentation

## Overview

The EV Telemetry Analysis Platform now includes a secure LINKFMS authentication system. Users must login with their LINKFMS credentials before accessing the platform.

## Login Credentials

### Demo User Accounts

The system comes with three pre-configured user accounts for testing:

#### 1. **Administrator**
- **User ID:** `admin`
- **Password:** `linkfms@2024`
- **Role:** Administrator
- **Email:** admin@linkfms.com
- **Name:** Admin User
- **Permissions:** Full access to all features

#### 2. **Data Analyst**
- **User ID:** `analyst`
- **Password:** `analyst@2024`
- **Role:** Data Analyst
- **Email:** analyst@linkfms.com
- **Name:** Data Analyst
- **Permissions:** Full access to data analysis features

#### 3. **Technician**
- **User ID:** `technician`
- **Password:** `tech@2024`
- **Role:** Technician
- **Email:** tech@linkfms.com
- **Name:** Technician User
- **Permissions:** Access to technical features

## Features

### Login Page
- Clean, professional interface
- Demo credentials displayed for reference
- Error handling for invalid credentials
- Session management with timeout (1 hour)

### User Session Management
- Automatic session timeout after 1 hour of inactivity
- User profile display in sidebar
- Quick logout button
- Session time tracking

### Role-Based Access Control
- Administrator (Level 3) - Full access
- Data Analyst (Level 2) - Analysis access
- Technician (Level 1) - Technical access

## How to Login

1. **Start the application:**
   ```bash
   streamlit run app.py
   ```

2. **Enter credentials:**
   - User ID: Enter your LINKFMS user ID
   - Password: Enter your LINKFMS password

3. **Click Login:**
   - Click the "🔓 Login" button
   - If credentials are valid, you'll be redirected to the dashboard
   - Demo credentials are shown on the login page

4. **Use the platform:**
   - Your user profile is displayed in the sidebar
   - Session timeout is 1 hour
   - Use the logout button to end your session

## Security Features

### Implemented
- ✓ User authentication verification
- ✓ Session management with timeout
- ✓ Role-based access control
- ✓ Password verification
- ✓ User profile display
- ✓ Logout functionality

### Recommended for Production
- [ ] Encrypt passwords in database
- [ ] Implement forgot password functionality
- [ ] Enable two-factor authentication
- [ ] Add login attempt tracking/rate limiting
- [ ] Log all user activities
- [ ] Use secure token-based sessions
- [ ] Implement refresh token mechanism
- [ ] Add audit trail for sensitive operations

## Customizing Users

To add or modify users, edit the `LINKFMS_USERS` dictionary in `utils/login_auth.py`:

```python
LINKFMS_USERS = {
    "userid": {
        "password": "password",
        "role": "Role Name",
        "email": "user@linkfms.com",
        "name": "Full Name"
    }
}
```

**Note:** In production, store credentials in a secure database with encrypted passwords.

## Session Timeout

- Default timeout: **1 hour** (3600 seconds)
- Configurable in `utils/login_auth.py`:
  ```python
  SESSION_TIMEOUT = 3600  # Change this value
  ```
- When session expires, user will be prompted to login again

## Sidebar Display

After successful login, the sidebar shows:
- Welcome message with user's first name
- User role
- User ID and email
- Logout button
- Session duration counter

## Error Messages

### Invalid Credentials
```
❌ Invalid User ID or Password. Please try again.
```

### Missing Fields
```
❌ Please enter both User ID and Password
```

### Session Expired
```
⚠️ Your session has expired. Please login again.
```

## Code Integration

The login system is integrated into `app.py`:

```python
# Initialize session
LoginManager.initialize_session()

# Check authentication
if not LoginManager.is_authenticated():
    render_login_page()
    st.stop()

# Check timeout
if not LoginManager.check_session_timeout():
    st.warning("⚠️ Your session has expired. Please login again.")
    st.rerun()
```

## API Reference

### LoginManager Class

#### Methods

**`initialize_session()`**
- Initialize session state variables
- Called at app startup

**`login_user(userid, password)`**
- Authenticate user and create session
- Returns: `True` if successful, `False` otherwise

**`logout_user()`**
- Clear user session and authentication state

**`is_authenticated()`**
- Check if user is currently logged in
- Returns: `True` if authenticated, `False` otherwise

**`get_current_user()`**
- Get current user's information
- Returns: User info dict or `None`

**`verify_credentials(userid, password)`**
- Verify username and password
- Returns: Tuple of (is_valid, user_info)

**`check_session_timeout()`**
- Check if session is still valid
- Returns: `True` if valid, `False` if timed out

**`get_user_role()`**
- Get current user's role
- Returns: Role string or `None`

**`has_permission(required_role)`**
- Check if user has required role/permission
- Returns: `True` if authorized, `False` otherwise

## Testing the Login System

### Test Valid Login
1. User ID: `admin`
2. Password: `linkfms@2024`
3. Expected: Dashboard loads, user profile shows "Admin User"

### Test Invalid Login
1. User ID: `admin`
2. Password: `wrong_password`
3. Expected: Error message "Invalid User ID or Password"

### Test Session Timeout
1. Login successfully
2. Wait for 1 hour (or modify timeout value for testing)
3. Expected: Session expires, redirect to login page

## Support

For issues or questions about the login system:
1. Check that User ID and Password match demo credentials
2. Verify internet connection
3. Clear browser cache and cookies
4. Try incognito/private browsing mode
5. Check Streamlit server logs for errors

---

**Version:** 1.0  
**Last Updated:** May 2026  
**Author:** LINKFMS Development Team
