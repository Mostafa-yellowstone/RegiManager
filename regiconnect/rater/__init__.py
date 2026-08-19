"""Regi Rater bounded context — comparative rating on top of RegiConnect.

Does not replace CRM, Quote Pipeline, Policy, or Finance.
"""

from .orchestrator import rating_results, resume_pending_jobs, start_rating
from .quotes import append_quote_version
from .requests import add_rating_job, create_rating_request, transition_rating_request
from .select import select_quote
from .state import IllegalRatingTransition, RatingRequestStatus

__all__ = [
    "IllegalRatingTransition",
    "RatingRequestStatus",
    "add_rating_job",
    "append_quote_version",
    "create_rating_request",
    "rating_results",
    "resume_pending_jobs",
    "select_quote",
    "start_rating",
    "transition_rating_request",
]
