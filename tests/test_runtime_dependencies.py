import streamlit
from streamlit_echarts import st_echarts


def test_echarts_component_imports_on_the_locked_streamlit_runtime():
    """A chart dependency must not silently upgrade the approved Streamlit baseline."""
    assert callable(st_echarts)
    assert streamlit.__version__ == "1.37.1"
