from app.schemas.agent import AgentThreadResumeRequest


def test_resume_contract_accepts_approve_and_reject():
    assert AgentThreadResumeRequest(decision="approve").decision == "approve"
    assert AgentThreadResumeRequest(decision="reject", note="ok").decision == "reject"
