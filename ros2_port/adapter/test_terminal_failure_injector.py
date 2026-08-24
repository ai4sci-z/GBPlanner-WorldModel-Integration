from terminal_failure_injector import controller_ready


def test_controller_ready_requires_bootstrap_and_ready():
    assert controller_ready({"ready": True, "bootstrap_ready": True}) is True
    assert controller_ready({"ready": True, "bootstrap_ready": False}) is False
    assert controller_ready({"ready": False, "bootstrap_ready": True}) is False
    assert controller_ready(None) is False
