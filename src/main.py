from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
import os
from uuid import uuid4
from datetime import datetime

import httpx  # NEW: for async HTTP calls

# ---------- Config ----------

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"  # adjust if needed
DEEPSEEK_MODEL = "deepseek-chat"
PROMPT_PATH = os.getenv("PROMPT_PATH", "prompt.txt")  # NEW: path to prompt file
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")      # NEW: injected via OpenShift secret

# Load system prompt once at startup
def load_prompt() -> str:
    if not os.path.exists(PROMPT_PATH):
        raise RuntimeError(f"Prompt file not found at {PROMPT_PATH}")
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()

SYSTEM_PROMPT = load_prompt()  # NEW


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


# ---------- LLM client (DeepSeek) ----------

async def call_llm(contract_text: str) -> Dict:
    """
    Call DeepSeek API with system prompt from prompt.txt and contract text
    as the user message. Return a JSON dict that matches make_dummy_analysis
    output format (summary, categories, topRisks, document, etc.).

    Here I assume your prompt instructs the model to produce exactly that JSON.
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY env var not set")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": contract_text,
        },
    ]

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        # Optionally:
        # "response_format": {"type": "json_object"},
        # "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(DEEPSEEK_API_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            # Log or raise with more detail
            raise HTTPException(
                status_code=500,
                detail=f"DeepSeek API error: {resp.status_code} {resp.text}",
            )

        data = resp.json()

    # Expecting something like OpenAI-style:
    # data["choices"][0]["message"]["content"] -> JSON string
    content = data["choices"][0]["message"]["content"]

    # If model returns JSON as a string, parse it:
    import json
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # If it doesn't return valid JSON, you can either:
        # - raise an error, or
        # - fall back to some default structure
        raise HTTPException(status_code=500, detail="LLM returned invalid JSON")

    return result


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

    # No truncation here – full text:
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
