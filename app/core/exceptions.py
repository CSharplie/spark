class NotAuthenticated(Exception):
    """Raised by get_current_user; handled in app.main to redirect to /login."""
