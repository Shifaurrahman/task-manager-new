from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.graph.build_graph import pipeline
from app.models import MessageRequest, MessageResponse, WrittenConcept

app = FastAPI(title="Chat-to-knowledge-bundle API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/message", response_model=MessageResponse)
def handle_message(req: MessageRequest) -> MessageResponse:
    result = pipeline.invoke({
        "dashboard_owner": req.dashboard_owner,
        "raw_message": req.message,
        "domain": "",
        "concepts": [],
        "written": [],
    })

    return MessageResponse(
        domain=result["domain"],
        written=[WrittenConcept(**w) for w in result["written"]],
    )


@app.get("/health")
def health():
    return {"status": "ok"}