"""Nestflix recommendation engine.

Two tiers, per CLAUDE.md:

* **Content-based** (``features`` + ``taste_profile``) always runs and is cold-start safe.
* **Learned re-ranker** (``model``) — a lightweight "will I finish this?" logistic
  regression that activates only past a watch-count threshold and auto-retrains.

``rows`` assembles the explainable home-screen rows from both.
"""
