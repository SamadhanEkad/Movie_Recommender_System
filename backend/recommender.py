"""
===========================================================================
RECOMMENDER (Backend runtime module used by frontend/app.py)
===========================================================================
Job of this file
    The notebook (movie_recommender_system.ipynb) BUILDS the model once.
    This file LOADS that model and answers: "which 5 movies are similar?"
    A notebook cannot be imported by Streamlit, so this small module is
    the bridge between the notebook's pickle files and app.py.

Libraries used
    pickle / pandas / numpy : load the saved data and rank similarity scores
    requests                : call the TMDB API to get movie posters
    functools.lru_cache     : load files once, remember poster URLs

Files needed in backend/
    movie_dict.pkl, similarity.pkl   (created by the notebook)

TMDB API key (never write it in code)
    Local          : .streamlit/secrets.toml  ->  TMDB_API_KEY = "your_key"
    Streamlit Cloud: App Settings > Secrets   ->  TMDB_API_KEY = "your_key"
===========================================================================
"""

import os
import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------
# 1. Configuration
# --------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
PLACEHOLDER_POSTER = "https://placehold.co/300x450/1f2937/ffffff?text=Poster+Unavailable"


def get_api_key():
    """Read the TMDB key from Streamlit secrets, else from an environment variable."""
    try:
        import streamlit as st
        return st.secrets["TMDB_API_KEY"]
    except Exception:
        return os.getenv("TMDB_API_KEY")


# --------------------------------------------------------------------------
# 2. Load the model (runs once)
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_recommender_data():
    """Return (movies DataFrame, similarity matrix) saved by the notebook."""
    with open(BACKEND_DIR / "movie_dict.pkl", "rb") as file:
        movies = pd.DataFrame(pickle.load(file))
    with open(BACKEND_DIR / "similarity.pkl", "rb") as file:
        similarity = pickle.load(file)
    return movies, similarity


@lru_cache(maxsize=1)
def get_title_lookup():
    """Map lowercase title -> row number, for fast matching."""
    movies, _ = load_recommender_data()
    return {str(title).lower(): i for i, title in enumerate(movies["title"])}


# app.py imports these two (e.g. movies["title"] fills the dropdown)
movies, similarity = load_recommender_data()


# --------------------------------------------------------------------------
# 3. Poster fetching (TMDB API)
# --------------------------------------------------------------------------
# One shared session that retries automatically on slow / failed connections
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])))


@lru_cache(maxsize=512)
def _get_poster_url(movie_id):
    """Ask TMDB for the poster. Errors are raised, so failures are never cached."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError("TMDB_API_KEY is not set")
    response = _session.get(
        f"https://api.themoviedb.org/3/movie/{movie_id}",
        params={"api_key": api_key}, timeout=10)
    response.raise_for_status()
    poster_path = response.json().get("poster_path")
    if not poster_path:
        raise ValueError("No poster available")
    return f"https://image.tmdb.org/t/p/w500{poster_path}"


def fetch_poster(movie_id):
    """Return the poster URL, or a placeholder image if anything fails."""
    try:
        return _get_poster_url(movie_id)
    except (requests.RequestException, ValueError) as error:
        print(f"Poster failed for movie_id={movie_id}: {error}")
        return PLACEHOLDER_POSTER


# --------------------------------------------------------------------------
# 4. Recommendation
# --------------------------------------------------------------------------
def recommend(movie, poster_fetcher=None):
    """Return (5 movie titles, 5 poster URLs) most similar to `movie`.

    poster_fetcher is optional: app.py can pass its own cached function.
    """
    movie_index = get_title_lookup().get(str(movie).strip().lower())
    if movie_index is None:
        raise ValueError("Movie not found")

    # Highest similarity first; skip the selected movie itself
    ranked = np.argsort(similarity[movie_index])[::-1]
    top5 = [i for i in ranked if i != movie_index][:5]

    get_poster = poster_fetcher or fetch_poster
    names = [str(movies.iloc[i]["title"]) for i in top5]
    posters = [get_poster(int(movies.iloc[i]["movie_id"])) for i in top5]
    return names, posters