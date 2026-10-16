from scripts import dev_server


def test_log_message_accepts_an_int_status_code_as_log_error_passes_it(capsys):
    handler = dev_server.BriefingRequestHandler.__new__(dev_server.BriefingRequestHandler)
    handler.log_message("code %d, message %s", 404, "Not Found")      # used to raise TypeError -> ERR_EMPTY_RESPONSE
    handler.log_message('"%s" %s %s', "GET /api/briefing HTTP/1.1", "200", "-")
    assert "GET /api/briefing" in capsys.readouterr().out
