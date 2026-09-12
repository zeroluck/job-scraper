import pytest
import json
import logging
from unittest.mock import patch
from resume_parser import (
    INVALID_JSON,
    SCHEMA_VALIDATION_FAILED,
    TRUNCATED_OUTPUT,
    ResumeParseError,
    extract_first_json_object,
    parse_and_validate_resume,
    _parse_target,
)

def test_parse_and_validate_resume_success():
    mock_data = {"name": "John Doe", "experience": []}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai', return_value=mock_json):
        result = parse_and_validate_resume("some text")
        assert result["name"] == mock_data["name"]
        assert result["experience"] == mock_data["experience"]


def test_resume_parser_bounds_output_and_reasoning():
    with patch("resume_parser.primary_client.generate_content", return_value="{}") as generate:
        from resume_parser import parse_resume_with_ai

        parse_resume_with_ai("resume text")

    assert generate.call_args.kwargs["max_tokens"] == 12000
    assert generate.call_args.kwargs["reasoning_effort"] == "low"

def test_parse_and_validate_resume_retry_then_success():
    mock_data = {"name": "John Doe", "experience": []}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai') as mock_parse:
        # First call returns None, second returns valid JSON
        mock_parse.side_effect = [None, mock_json]
        
        # We need to patch time.sleep to avoid waiting during tests
        with patch('time.sleep'):
            result = parse_and_validate_resume("some text")
            assert result["name"] == mock_data["name"]
            assert result["experience"] == mock_data["experience"]
            assert mock_parse.call_count == 2

def test_parse_and_validate_resume_json_error_retry():
    mock_data = {"name": "John Doe", "experience": []}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai') as mock_parse:
        # First call returns malformed JSON, second returns valid JSON
        mock_parse.side_effect = ["{malformed}", mock_json]
        
        with patch('time.sleep'):
            result = parse_and_validate_resume("some text")
            assert result["name"] == mock_data["name"]
            assert result["experience"] == mock_data["experience"]
            assert mock_parse.call_count == 2


def test_parse_and_validate_resume_accepts_fenced_json_with_preamble():
    response = '''Here is the parsed resume:
```json
{"name": "John Doe", "summary": "Uses {structured} data"}
```
This is the requested output.'''

    with patch('resume_parser.parse_resume_with_ai', return_value=response):
        result = parse_and_validate_resume("some text")

    assert result["name"] == "John Doe"
    assert result["summary"] == "Uses {structured} data"


def test_extract_first_json_object_uses_first_valid_top_level_object():
    response = 'Preamble {not JSON}. Result: {"name": "First"} {"name": "Second"}'

    extracted = extract_first_json_object(response)

    assert json.loads(extracted) == {"name": "First"}


@pytest.mark.parametrize("response", [
    '{"name": "John Doe"',
    '{"name": "John Doe", "links": {"github": "example"}',
])
def test_extract_first_json_object_categorizes_truncated_output(response):
    with pytest.raises(ResumeParseError) as exc_info:
        extract_first_json_object(response)

    assert exc_info.value.category == TRUNCATED_OUTPUT


def test_extract_first_json_object_categorizes_invalid_json():
    with pytest.raises(ResumeParseError) as exc_info:
        extract_first_json_object('{"name": invalid}')

    assert exc_info.value.category == INVALID_JSON


def test_parse_and_validate_resume_retries_schema_validation_failure(caplog):
    invalid_schema = json.dumps({"name": "John Doe", "skills": "Python"})
    valid_data = {"name": "John Doe", "skills": ["Python"]}

    with patch('resume_parser.parse_resume_with_ai') as mock_parse:
        mock_parse.side_effect = [invalid_schema, json.dumps(valid_data)]
        with patch('time.sleep'), caplog.at_level(logging.WARNING):
            result = parse_and_validate_resume("some text")

    assert result["name"] == valid_data["name"]
    assert result["skills"] == valid_data["skills"]
    record = next(record for record in caplog.records if record.event == "resume_parse_failure")
    assert record.parse_category == SCHEMA_VALIDATION_FAILED
    assert record.parse_stage == "schema_validation"


def test_parse_failure_diagnostic_is_structured_and_payload_is_bounded(caplog):
    response = '{"name": invalid, "private": "' + ("secret-value-" * 30) + '"}'

    with patch('resume_parser.parse_resume_with_ai', return_value=response):
        with patch('time.sleep'), patch('sys.exit'), caplog.at_level(logging.WARNING):
            parse_and_validate_resume("some text", max_retries=1)

    record = next(record for record in caplog.records if record.event == "resume_parse_failure")
    assert record.parse_category == INVALID_JSON
    assert record.parse_stage == "json_decode"
    assert record.response_length == len(response)
    assert record.llm_model
    assert len(record.payload_snippet) <= 160
    assert response not in record.getMessage()
    assert "secret-value" not in record.payload_snippet

def test_parse_and_validate_resume_failure_exits():
    with patch('resume_parser.parse_resume_with_ai', return_value=None):
        with patch('time.sleep'):
            with patch('sys.exit') as mock_exit:
                parse_and_validate_resume("some text", max_retries=2)
                mock_exit.assert_called_once_with(1)

def test_parse_and_validate_resume_replaces_empty_with_na():
    mock_data = {"name": "", "summary": None, "skills": ["Python", ""]}
    expected_data = {"name": "NA", "summary": "NA", "skills": ["Python", "NA"]}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai', return_value=mock_json):
        result = parse_and_validate_resume("some text")
        assert {key: result[key] for key in expected_data} == expected_data


@pytest.mark.parametrize("payload", [
    {},
    {"unexpected": "payload"},
    {"name": "NA"},
    {"skills": ["NA"]},
    {"experience": [{}]},
])
def test_parse_and_validate_resume_rejects_unusable_or_unknown_payload(payload):
    with patch('resume_parser.parse_resume_with_ai', return_value=json.dumps(payload)):
        with patch('time.sleep'):
            with pytest.raises(SystemExit):
                parse_and_validate_resume("some text", max_retries=1)


def test_main_fails_when_database_save_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("supabase_utils.download_resume_from_storage", lambda _name: b"pdf")
    monkeypatch.setattr("supabase_utils.save_base_resume", lambda _payload: False)
    monkeypatch.setattr("resume_parser.extract_text_from_pdf", lambda _path: "resume text")
    monkeypatch.setattr("resume_parser.parse_and_validate_resume", lambda _text: {"name": "Jane"})

    from resume_parser import main

    with pytest.raises(RuntimeError, match="Failed to save parsed resume"):
        main()


def test_lane_main_uses_canonical_storage_path_and_atomic_profile_save(monkeypatch):
    parsed = {"name": "Jane", "skills": ["Routing"]}
    sources = []
    saved = []
    monkeypatch.setattr(
        "resume_parser.parse_storage_resume",
        lambda key, **_kwargs: sources.append(key) or parsed,
    )
    monkeypatch.setattr(
        "supabase_utils.save_archetype_resume_profiles",
        lambda profiles: saved.append(profiles) or True,
    )

    from resume_parser import main

    result = main("software_tpm")

    assert sources == ["archetypes/technology_delivery.pdf"]
    assert saved == [{"technology_delivery": parsed}]
    assert result == saved[0]


def test_all_lane_main_stages_every_parse_before_one_save(monkeypatch):
    lanes = ("technology_delivery", "network_infrastructure")
    calls = []
    monkeypatch.setattr(
        "downstream_orchestration.enabled_lane_slugs", lambda _db: lanes
    )
    monkeypatch.setattr("supabase_utils.get_base_resume", lambda: {"name": "Base"})
    monkeypatch.setattr(
        "resume_parser.parse_storage_resume",
        lambda key, **_kwargs: calls.append(("parse", key)) or {"name": key},
    )
    monkeypatch.setattr(
        "supabase_utils.save_archetype_resume_profiles",
        lambda profiles: calls.append(("save", tuple(profiles))) or True,
    )

    from resume_parser import main

    main("all", db=object())

    assert calls == [
        ("parse", "archetypes/technology_delivery.pdf"),
        ("parse", "archetypes/network_infrastructure.pdf"),
        ("save", lanes),
    ]


def test_all_lane_main_does_not_save_partial_results(monkeypatch):
    monkeypatch.setattr(
        "downstream_orchestration.enabled_lane_slugs",
        lambda _db: ("technology_delivery", "network_infrastructure"),
    )
    monkeypatch.setattr("supabase_utils.get_base_resume", lambda: {"name": "Base"})
    parse_calls = iter(({"name": "Jane"}, RuntimeError("missing source")))

    def parse(_key, **_kwargs):
        result = next(parse_calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("resume_parser.parse_storage_resume", parse)
    save = patch("supabase_utils.save_archetype_resume_profiles")
    with save as mock_save, pytest.raises(RuntimeError, match="missing source"):
        from resume_parser import main

        main("all", db=object())
    mock_save.assert_not_called()


def test_parse_target_rejects_unknown_and_path_like_lanes():
    with pytest.raises(ValueError, match="Unknown career lane"):
        _parse_target("../resume.pdf")
