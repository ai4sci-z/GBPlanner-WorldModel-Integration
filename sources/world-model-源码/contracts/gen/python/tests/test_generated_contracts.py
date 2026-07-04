from pathlib import Path
import unittest

from google.protobuf.json_format import Parse

from navlab_contracts.navlab.orchestration.v1.doctor_result_pb2 import DoctorResult
from navlab_contracts.navlab.orchestration.v1 import task_request_pb2, task_result_pb2
from navlab_contracts.navlab.orchestration.v1.task_request_pb2 import TaskRequest
from navlab_contracts.navlab.orchestration.v1.task_result_pb2 import TaskResult
from navlab_contracts.navlab.runtime.v1.process_event_pb2 import ProcessEvent
from navlab_contracts.navlab.runtime.v1.runtime_plan_pb2 import RuntimePlan
from navlab_contracts.navlab.runtime.v1 import service_spec_pb2
from navlab_contracts.navlab.safety.v1.mavlink_ack_pb2 import MavlinkAck
from navlab_contracts.navlab.sensors.v1 import source_evidence_pb2
from navlab_contracts.navlab.sensors.v1.source_evidence_pb2 import SourceEvidence


EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples"


def parse_example(relative: str, message):
    text = (EXAMPLES_DIR / relative).read_text(encoding="utf-8")
    return Parse(text, message, ignore_unknown_fields=True)


class GeneratedContractTests(unittest.TestCase):
    def test_golden_examples_parse_with_generated_python_classes(self):
        request = parse_example("orchestration/sim_task_request.json", TaskRequest())
        self.assertEqual(request.task_id, "hover")
        self.assertEqual(request.runtime_mode, task_request_pb2.RUNTIME_MODE_SIM)

        task_result = parse_example("orchestration/real_task_result.json", TaskResult())
        self.assertEqual(task_result.status, task_result_pb2.TASK_STATUS_BLOCKED)

        doctor = parse_example("orchestration/doctor_result_blocked.json", DoctorResult())
        self.assertTrue(doctor.blocked)

        runtime_plan = parse_example("runtime/sim_runtime_plan.json", RuntimePlan())
        self.assertEqual(runtime_plan.services[0].backend, service_spec_pb2.RUNTIME_BACKEND_DOCKER)

        event = parse_example("runtime/real_process_event.json", ProcessEvent())
        self.assertTrue(event.run_id)

        ack = parse_example("safety/motor_debug_ack_failed.json", MavlinkAck())
        self.assertEqual(ack.command, "ARM")
        self.assertFalse(ack.accepted)

        source = parse_example("sensors/real_source_evidence.json", SourceEvidence())
        self.assertEqual(source.runtime_domain, source_evidence_pb2.RUNTIME_DOMAIN_REAL)


if __name__ == "__main__":
    unittest.main()
