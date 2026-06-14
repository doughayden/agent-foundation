"""Eval-lane conftest: load the real environment for live model inference.

The eval lane runs the agent against the real LLM, so it needs the genuine
``.env`` values (Vertex AI project, location, GOOGLE_GENAI_USE_VERTEXAI) and
real Application Default Credentials. The root ``tests/conftest.py`` skips its
collection-time auth/dotenv mocks when the invocation targets only this lane.

``load_dotenv()`` is a silent no-op when no ``.env`` exists (CI sets the same
variables directly on the job environment).
"""

from dotenv import load_dotenv

load_dotenv()
