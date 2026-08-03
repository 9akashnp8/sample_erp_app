from pydantic import BaseModel, Field
from typing import Optional, Literal, List

# Literal (not plain str) for the same class of reason as helpdesk/leave, a
# third one: these values drive a state machine. `status` gates which
# endpoints are legal on a review, and `decision` picks a branch — a typo
# should 422 at the API boundary rather than wedge a review in a status no
# transition can leave.
ReviewStatus = Literal[
    "Draft",
    "Objectives Submitted",
    "Objectives Sent Back",
    "Objectives Approved",
    "Self Assessment Submitted",
    "Completed",
]
ReviewStage = Literal["Objective Setting", "Appraisal", "Completed"]
ObjectiveDecision = Literal["Approve", "Send Back"]

# 1-5 everywhere a rating is accepted. Declared once so the objective and
# competency rating models can't drift apart.
Rating = int


# ---------------- Competencies (reference data) ----------------

class Competency(BaseModel):
    """Read-only reference data — seeded by scripts/build_performance.py.
    There is deliberately no Create/Update model: company core competencies
    are a fixed company-wide list in this sample, not per-review content."""
    id: int
    code: str
    name: str
    description: Optional[str] = None
    active: bool
    created_at: str

    class Config:
        from_attributes = True


# ---------------- Objectives ----------------

class ObjectiveCreate(BaseModel):
    description: str
    weightage: int = Field(..., ge=1, le=100, description="Percentage weight; a review's objectives must total exactly 100 before they can be submitted.")


class ObjectiveUpdate(BaseModel):
    """Partial update of an objective's *definition*. Ratings are deliberately
    not settable here — they go through the self-assessment / manager-assessment
    endpoints, which is what enforces the appraisal-stage state machine."""
    description: Optional[str] = None
    weightage: Optional[int] = Field(None, ge=1, le=100)


class Objective(BaseModel):
    id: int
    review_id: int
    description: str
    weightage: int
    self_rating: Optional[Rating] = None
    self_notes: Optional[str] = None
    manager_rating: Optional[Rating] = None
    manager_notes: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CompetencyRating(BaseModel):
    """A competency rating joined with its competency's code/name, so a
    consumer never has to make a second call to know what was rated."""
    id: int
    review_id: int
    competency_id: int
    competency_code: str
    competency_name: str
    self_rating: Optional[Rating] = None
    self_notes: Optional[str] = None
    manager_rating: Optional[Rating] = None
    manager_notes: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ---------------- Reviews ----------------

class PerformanceReviewCreate(BaseModel):
    """Opens a review cycle. `manager_id` is not accepted — it's snapshotted
    from the employee's current manager, and `status` always starts at
    'Draft' (never caller-suppliable, same as a ticket's 'Open')."""
    employee_id: str
    cycle_year: int = Field(..., ge=2000, le=2100)


class PerformanceReview(BaseModel):
    id: int
    review_ref: str
    employee_id: str
    manager_id: str
    cycle_year: int
    status: ReviewStatus
    stage: ReviewStage  # derived from status in the router, never stored
    objectives_manager_notes: Optional[str] = None
    self_objective_score: Optional[float] = None
    self_competency_score: Optional[float] = None
    self_overall_rating: Optional[float] = None
    manager_objective_score: Optional[float] = None
    manager_competency_score: Optional[float] = None
    manager_overall_rating: Optional[float] = None
    objectives_submitted_at: Optional[str] = None
    objectives_approved_at: Optional[str] = None
    self_assessment_submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PerformanceReviewDetail(PerformanceReview):
    """What GET /performance/reviews/{review_ref} returns — the review plus
    everything hanging off it. This is the call a manager makes to see the
    employee's self-ratings alongside their own before assessing."""
    objectives: List[Objective] = []
    competencies: List[CompetencyRating] = []


# ---------------- Workflow actions ----------------

class ObjectiveReviewRequest(BaseModel):
    """The manager's verdict on submitted objectives. `notes` is required when
    sending back (validated in the router, so the message names the field)
    and optional when approving."""
    decision: ObjectiveDecision
    notes: Optional[str] = None


class ObjectiveRatingInput(BaseModel):
    objective_id: int
    rating: Rating = Field(..., ge=1, le=5)
    notes: Optional[str] = None


class CompetencyRatingInput(BaseModel):
    competency_code: str
    rating: Rating = Field(..., ge=1, le=5)
    notes: Optional[str] = None


class AssessmentRequest(BaseModel):
    """Used for both the self assessment and the manager assessment — the two
    sides rate exactly the same things, only the column written differs.

    `submit=False` saves progress without advancing the workflow (partial
    lists are fine). `submit=True` requires every objective and every active
    competency to be rated, freezes the computed scores onto the review and
    moves it to the next status."""
    objectives: List[ObjectiveRatingInput] = []
    competencies: List[CompetencyRatingInput] = []
    submit: bool = True
