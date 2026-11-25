import os
import sys
from pathlib import Path

import requests
import streamlit as st

# ==============================
# Configuration
# ==============================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.recommender import movies, recommend

# ==============================
# TMDB API key
# Priority: Streamlit secrets > environment variable
# ==============================
try:
    api_key = st.secrets["TMDB_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    api_key = os.getenv("TMDB_API_KEY")

if api_key:
    os.environ["TMDB_API_KEY"] = str(api_key)

PLACEHOLDER_POSTER = "https://placehold.co/300x450/1f2937/ffffff?text=Poster+Unavailable"


# ==============================
# Poster fetching
# ==============================
@st.cache_data(show_spinner=False)
def _get_poster_url(movie_id, key):
    """Fetch the poster URL from TMDB. Raises on failure so errors are NOT cached."""
    response = requests.get(
        f"https://api.themoviedb.org/3/movie/{movie_id}",
        params={"api_key": key},
        timeout=5,
    )
    response.raise_for_status()
    poster_path = response.json().get("poster_path")
    if not poster_path:
        raise ValueError("No poster available")
    return "https://image.tmdb.org/t/p/w500" + poster_path


def fetch_poster(movie_id):
    """Return a TMDB poster URL, or a placeholder if the request fails."""
    try:
        return _get_poster_url(movie_id, api_key)
    except (requests.RequestException, ValueError):
        return PLACEHOLDER_POSTER


# ==============================
# Page setup and styling
# ==============================
st.set_page_config(
    page_title="Movie Recommender",
    page_icon="🎬",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    [data-testid="stSidebar"] {background-color: #111827;}
    [data-testid="stSidebar"] * {color: #f9fafb;}
    [data-testid="stImage"] img {border-radius: 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================
# Header
# ==============================
st.title("🎬 Movie Recommender System")
st.caption("Find five movies similar to a title from the catalog.")

# ==============================
# Sidebar
# ==============================
with st.sidebar:
    st.header("Choose a movie")
    if not api_key:
        st.warning("TMDB_API_KEY missing. Add it in .streamlit/secrets.toml or Streamlit Cloud > Secrets.")
    selected_movie_name = st.selectbox(
        "Movie",
        options=[""] + sorted(movies["title"].astype(str).unique().tolist()),
        format_func=lambda title: "Select a movie" if title == "" else title,
    )
    recommend_button = st.button("Recommend", type="primary", use_container_width=True)

# ==============================
# Recommendations
# ==============================
if recommend_button:
    if not selected_movie_name:
        st.warning("Please select a movie.")
    else:
        try:
            names, posters = recommend(selected_movie_name, fetch_poster)
            if not names:
                st.info("No recommendations were found.")
            else:
                st.subheader(f"Movies similar to {selected_movie_name}")
                columns = st.columns(len(names))
                for column, name, poster in zip(columns, names, posters):
                    with column:
                        with st.container(border=True):
                            st.image(poster, use_container_width=True)
                            st.markdown(f"**{name}**")
        except (ValueError, IndexError):
            st.error("The selected movie could not be found. Please choose another title.")