# Signal Check

A small Flask app that searches published fact-checks using RSS instead of
training on a local CSV.

## Run locally

1. Install the packages with `pip install -r requirements.txt`.
2. Run `python app.py` from this directory and open `http://127.0.0.1:5000`.

The app fetches the [Snopes fact-check RSS feed](https://www.snopes.com/fact-check/feed/)
when a claim is submitted, then compares the text with feed titles and summaries
locally. The submitted text is not sent to Snopes or a search provider. No CSV or
API key is required; internet access is required.

Matching items are evidence to review, not a truth verdict. A missing match does
not establish that a claim is true or false. Snopes is currently the only
configured feed, so coverage is limited to its published and recent checks.
Feed failures are shown in the app rather than reported as a no-match result.
