# Scheduler API Tester

A friendlier Swagger for the Nokia Scheduler backend — test all 79 endpoints
with a clean sidebar picker, form inputs, request preview, curl copy, response
inspector, and per-session call history.

## Run

```bash
pip install streamlit requests
streamlit run api_tester/app.py
```

Make sure the backend is up at the URL set in the sidebar (default
`http://localhost:8000`).

## Files

- `app.py` — the Streamlit UI
- `endpoints.py` — auto-extracted endpoint catalog (edit if a route changes)
