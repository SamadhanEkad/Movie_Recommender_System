import os
import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==============================
# Paths and configuration
# ==============================
BACKEND_DIR = Path(__file__).resolve().parent
PLACEHOLDER_POSTER = "https://placehold.co/300x450/1f2937/ffffff?text=Poster+Unavailable"

# TMDB API key is loaded from the environment.
# Set TMDB_API_KEY locally or in Streamlit Cloud > Secrets.


# ==============================
# Data and model loading
# ==============================
@lru_cache(maxsize=1)
def load_recommender_data():
    """Load the movie catalog and similarity matrix once."""
    with open(BACKEND_DIR / "movie_dict.pkl", "rb") as file:
        movies = pd.DataFrame(pickle.load(file))
    with open(BACKEND_DIR / "similarity.pkl", "rb") as file:
        similarity = pickle.load(file)
    return movies, similarity


@lru_cache(maxsize=1)
def get_title_lookup():
    """Build a title lookup once for faster movie matching."""
    movies, _ = load_recommender_data()
    return {
        str(title).lower(): index
        for index, title in zip(movies.index, movies["title"].tolist())
    }


movies, similarity = load_recommender_data()


# ==============================
# Poster fetching
# ==============================
# Reusable session that automatically retries on flaky connections
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,                                  # up to 3 retries per request
            backoff_factor=0.5,                       # wait 0.5s, 1s, 2s between tries
            status_forcelist=[429, 500, 502, 503, 504],
        )
    ),
)


@lru_cache(maxsize=512)
def _get_poster_url(movie_id):
    """Fetch a poster URL from TMDB. Raises on failure so errors are NOT cached."""
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        raise ValueError("TMDB_API_KEY is not set")
    response = _session.get(
        f"https://api.themoviedb.org/3/movie/{movie_id}",
        params={"api_key": api_key},
        timeout=10,
    )
    response.raise_for_status()
    poster_path = response.json().get("poster_path")
    if not poster_path:
        raise ValueError("No poster available")
    return f"https://image.tmdb.org/t/p/w500{poster_path}"


def fetch_poster(movie_id):
    """Return a movie poster URL, or a placeholder if unavailable."""
    try:
        return _get_poster_url(movie_id)
    except (requests.RequestException, ValueError) as error:
        # Printed in the terminal so the real failure reason is visible
        print(f"Poster failed for movie_id={movie_id}: {error}")
        return PLACEHOLDER_POSTER


# ==============================
# Recommendation logic
# ==============================
def recommend(movie, poster_fetcher=None):
    """Return five recommended movie names and poster URLs.

    An optional poster fetcher allows the frontend to provide its
    cached poster function while preserving the backend default.
    """
    movie_index = get_title_lookup().get(str(movie).strip().lower())
    if movie_index is None:
        raise ValueError("Movie not found")

    # Rank movies by similarity (highest first), skip the selected movie itself
    distances = similarity[movie_index]
    ranked_indexes = np.argsort(distances)[::-1]
    top_indexes = [index for index in ranked_indexes if index != movie_index][:5]

    recommended_movies = []
    recommended_posters = []
    poster_fetcher = poster_fetcher or fetch_poster
    for index in top_indexes:
        row = movies.iloc[index]
        recommended_movies.append(str(row["title"]))
        recommended_posters.append(poster_fetcher(int(row["movie_id"])))

    return recommended_movies, recommended_posters