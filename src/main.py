from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
import os
from uuid import uuid4
from datetime import datetime

# ---------- Models ----------

RiskLevel = Literal["low", "medium", "high"]


class CategoryScore(BaseModel):
    name: str
    value: int


class TopRisk(BaseModel):
    id: int
    level: RiskLevel
    category: str
    title: str
    description: str
    section: Optional[str] = None
    impact: Optional[str] = None
    recommendation: Optional[str] = None
    tags: List[str] = []


class Summary(BaseModel):
    overallRisk: RiskLevel
    riskScore: int = Field(ge=0, le=100)
    criticalIssues: int
    mediumIssues: int
    lowIssues: int
    recommendation: str


class IssueDetail(BaseModel):
    id: str
    type: str
    severity: RiskLevel
    snippet: str
    explanation: str
    suggestedFix: Optional[str] = None


class Section(BaseModel):
    id: str
    heading: Optional[str] = None
    text: str
    riskLevel: RiskLevel
    riskTags: List[str] = []
    issues: List[IssueDetail] = []


class DocumentInfo(BaseModel):
    name: str
    date: Optional[str] = None
    parties: List[str] = []
    reviewDate: Optional[str] = None
    analyst: Optional[str] = None


class ReportIssue(BaseModel):
    id: int
    category: str
    severity: str
    title: str
    status: str
    owner: Optional[str] = None
    dueDate: Optional[str] = None


class ExecutiveSummary(BaseModel):
    overallRisk: str
    riskScore: int
    criticalIssues: int
    mediumIssues: int
    lowIssues: int
    recommendation: str


class Report(BaseModel):
    documentInfo: DocumentInfo
    executiveSummary: ExecutiveSummary
    issues: List[ReportIssue]
    mitigationPlan: List[str]
    signingRecommendation: str


class Improvement(BaseModel):
    id: int
    category: str
    level: RiskLevel
    original: str
    improved: str
    rationale: str
    status: Literal["suggested", "accepted", "rejected"] = "suggested"


class Change(BaseModel):
    id: int
    type: Literal["added", "removed", "modified"]
    section: str
    original: Optional[str] = None
    revised: Optional[str] = None
    impact: RiskLevel
    description: str
    status: str


class ContractAnalysis(BaseModel):
    contractId: str
    fileName: str
    uploadedAt: str
    summary: Summary
    categories: List[CategoryScore]
    topRisks: List[TopRisk]
    document: Dict[str, object]
    improvements: List[Improvement]
    changes: List[Change]
    report: Report


class ContractListItem(BaseModel):
    contractId: str
    fileName: str
    uploadedAt: str
    overallRisk: RiskLevel
    riskScore: int


class ContractListResponse(BaseModel):
    items: List[ContractListItem]


class FeedbackRequest(BaseModel):
    issueId: str
    type: Literal["false_positive", "helpful", "not_helpful"]
    comment: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"


# ---------- Placeholder "LLM" client (dummy for now) ----------

async def call_llm(contract_text: str) -> Dict:
    """
    Placeholder function used instead of a real LLM.
    """
    return make_dummy_analysis(contract_text)


# ---------- Simple analyzer & dummy data ----------

def make_dummy_analysis(text: str) -> Dict:
    t = text.lower()
    if "unlimited liability" in t:
        risk_level: RiskLevel = "high"
        score = 80
    elif "as is" in t:
        risk_level = "medium"
        score = 65
    else:
        risk_level = "low"
        score = 30

    now = datetime.utcnow().isoformat() + "Z"

    return {
        "summary": {
            "overallRisk": risk_level,
            "riskScore": score,
            "criticalIssues": 1 if risk_level == "high" else 0,
            "mediumIssues": 2 if risk_level != "low" else 0,
            "lowIssues": 1,
            "recommendation": (
                "Significant revision required before signing."
                if risk_level == "high"
                else "Review recommended before signing."
            ),
        },
        "categories": [
            {"name": "Liability", "value": 8},
            {"name": "Payment Terms", "value": 5},
            {"name": "Termination", "value": 3},
            {"name": "IP Rights", "value": 6},
        ],
        "topRisks": [
            {
                "id": 1,
                "level": risk_level,
                "category": "Liability",
                "title": "Potentially unlimited liability",
                "description": "Contract may expose the company to broad liability.",
                "section": "Section 8.2",
                "impact": (
                    "Critical financial exposure" if risk_level == "high" else "Moderate exposure"
                ),
                "recommendation": "Introduce liability cap aligned with contract value.",
                "tags": ["liability", "indemnity"],
            }
        ],
        "document": {
            "title": "Uploaded Contract",
            "sections": [
                {
                    "id": "s1",
                    "heading": "Full text",
                    "text": text,  # ← FULL TEXT, no truncation
                    "riskLevel": risk_level,
                    "riskTags": ["liability"] if risk_level != "low" else [],
                    "issues": (
                        [
                            {
                                "id": "iss1",
                                "type": "liability",
                                "severity": risk_level,
                                "snippet": text[:200],
                                "explanation": "Potentially unfavorable liability language.",
                                "suggestedFix": "Cap liability and clarify exclusions.",
                            }
                        ]
                        if risk_level != "low"
                        else []
                    ),
                }
            ],
        },
        "improvements": [
            {
                "id": 1,
                "category": "Liability",
                "level": risk_level,
                "original": "Provider shall be liable for any and all damages...",
                "improved": "Provider's total liability under this agreement shall be limited to...",
                "rationale": "Introduces standard commercial liability cap.",
                "status": "suggested",
            }
        ],
        "changes": [
            {
                "id": 1,
                "type": "modified",
                "section": "Section 4.1 - Liability",
                "original": "Provider shall be liable for any and all damages...",
                "revised": "Provider's total liability under this agreement shall be limited to...",
                "impact": risk_level,
                "description": "Added liability cap to protect against unlimited exposure.",
                "status": "recommended",
            }
        ],
        "report": {
            "documentInfo": {
                "name": "Uploaded Contract",
                "date": None,
                "parties": [],
                "reviewDate": now.split("T")[0],
                "analyst": "RedGuard AI",
            },
            "executiveSummary": {
                "overallRisk": risk_level.capitalize(),
                "riskScore": score,
                "criticalIssues": 1 if risk_level == "high" else 0,
                "mediumIssues": 2 if risk_level != "low" else 0,
                "lowIssues": 1,
                "recommendation": (
                    "Significant revision required before signing."
                    if risk_level == "high"
                    else "Review recommended before signing."
                ),
            },
            "issues": [
                {
                    "id": 1,
                    "category": "Liability",
                    "severity": "Critical" if risk_level == "high" else "Medium",
                    "title": "Liability exposure",
                    "status": "Unresolved",
                    "owner": "Legal",
                    "dueDate": None,
                }
            ],
            "mitigationPlan": [
                "Introduce liability cap aligned with contract value.",
                "Clarify IP ownership of background vs foreground IP.",
            ],
            "signingRecommendation": (
                "Do not sign until high severity issues are resolved."
                if risk_level == "high"
                else "Proceed after addressing medium-risk items."
            ),
        },
    }


# ---------- Text extraction ----------

def extract_text_from_file(upload: UploadFile) -> str:
    filename = upload.filename or ""
    ext = filename.lower().split(".")[-1]
    data = upload.file.read()

    if ext == "txt":
        return data.decode("utf-8", errors="ignore")

    if ext == "pdf":
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if ext in ("docx", "doc"):
        from io import BytesIO
        import docx

        doc = docx.Document(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)

    raise HTTPException(status_code=400, detail="Unsupported file type")


# ---------- App + in-memory store ----------

app = FastAPI(title="RedGuard Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTRACTS: Dict[str, ContractAnalysis] = {}
FEEDBACK: Dict[str, List[FeedbackRequest]] = {}


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    return HealthResponse()


@app.post("/api/contracts/analyze", response_model=ContractAnalysis)
async def analyze_contract(file: UploadFile = File(...)):
    text = extract_text_from_file(file)

    if len(text) < 50:
        raise HTTPException(status_code=400, detail="Document too short")

    # NO TRUNCATION HERE
    # text = text[:20000]

    llm_result = await call_llm(text)

    contract_id = str(uuid4())
    uploaded_at = datetime.utcnow().isoformat() + "Z"

    analysis = ContractAnalysis(
        contractId=contract_id,
        fileName=file.filename or "document",
        uploadedAt=uploaded_at,
        summary=Summary(**llm_result["summary"]),
        categories=[CategoryScore(**c) for c in llm_result.get("categories", [])],
        topRisks=[TopRisk(**r) for r in llm_result.get("topRisks", [])],
        document=llm_result.get("document", {}),
        improvements=[Improvement(**imp) for imp in llm_result.get("improvements", [])],
        changes=[Change(**ch) for ch in llm_result.get("changes", [])],
        report=Report(**llm_result["report"]),
    )
    CONTRACTS[contract_id] = analysis
    return analysis


@app.get("/api/contracts", response_model=ContractListResponse)
async def list_contracts():
    items = [
        ContractListItem(
            contractId=cid,
            fileName=contract.fileName,
            uploadedAt=contract.uploadedAt,
            overallRisk=contract.summary.overallRisk,
            riskScore=contract.summary.riskScore,
        )
        for cid, contract in CONTRACTS.items()
    ]
    return ContractListResponse(items=items)


@app.get("/api/contracts/{contract_id}", response_model=ContractAnalysis)
async def get_contract(contract_id: str):
    contract = CONTRACTS.get(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


@app.post("/api/contracts/{contract_id}/feedback")
async def submit_feedback(contract_id: str, feedback: FeedbackRequest):
    if contract_id not in CONTRACTS:
        raise HTTPException(status_code=404, detail="Contract not found")
    FEEDBACK.setdefault(contract_id, []).append(feedback)
    return {"status": "ok"}
