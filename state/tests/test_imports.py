from app.main import app
from app.state.v1 import state_pb2, state_pb2_grpc


def test_fastapi_app_imports() -> None:
    assert app.title == "aecp-state"


def test_generated_state_grpc_imports() -> None:
    assert state_pb2.DESCRIPTOR.name == "state/v1/state.proto"
    assert state_pb2_grpc.StateServiceStub.__name__ == "StateServiceStub"
