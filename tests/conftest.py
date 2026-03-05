"""Configure test environment: mock streamlit before any app module imports."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

# Build a minimal streamlit stub so app modules can be imported without a
# running Streamlit server.  The decorator @st.cache_data must be transparent
# (i.e. return the function unchanged) for tests to call the real function.
_st_stub = ModuleType("streamlit")
_st_stub.cache_data = lambda *args, **kwargs: (
    (lambda fn: fn)
    if not args
    else args[0]  # handle @st.cache_data and @st.cache_data(ttl=…)
)
_st_stub.warning = MagicMock()
_st_stub.error = MagicMock()
_st_stub.info = MagicMock()

sys.modules.setdefault("streamlit", _st_stub)
