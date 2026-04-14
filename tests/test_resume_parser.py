import pytest
import json
import sys
from unittest.mock import patch, MagicMock
from resume_parser import parse_and_validate_resume

def test_parse_and_validate_resume_success():
    mock_data = {"name": "John Doe", "experience": []}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai', return_value=mock_json):
        result = parse_and_validate_resume("some text")
        assert result == mock_data

def test_parse_and_validate_resume_retry_then_success():
    mock_data = {"name": "John Doe", "experience": []}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai') as mock_parse:
        # First call returns None, second returns valid JSON
        mock_parse.side_effect = [None, mock_json]
        
        # We need to patch time.sleep to avoid waiting during tests
        with patch('time.sleep'):
            result = parse_and_validate_resume("some text")
            assert result == mock_data
            assert mock_parse.call_count == 2

def test_parse_and_validate_resume_json_error_retry():
    mock_data = {"name": "John Doe", "experience": []}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai') as mock_parse:
        # First call returns malformed JSON, second returns valid JSON
        mock_parse.side_effect = ["{malformed}", mock_json]
        
        with patch('time.sleep'):
            result = parse_and_validate_resume("some text")
            assert result == mock_data
            assert mock_parse.call_count == 2

def test_parse_and_validate_resume_failure_exits():
    with patch('resume_parser.parse_resume_with_ai', return_value=None):
        with patch('time.sleep'):
            with patch('sys.exit') as mock_exit:
                parse_and_validate_resume("some text", max_retries=2)
                mock_exit.assert_called_once_with(1)

def test_parse_and_validate_resume_replaces_empty_with_na():
    mock_data = {"name": "", "experience": None, "skills": ["Python", ""]}
    expected_data = {"name": "NA", "experience": "NA", "skills": ["Python", "NA"]}
    mock_json = json.dumps(mock_data)
    
    with patch('resume_parser.parse_resume_with_ai', return_value=mock_json):
        result = parse_and_validate_resume("some text")
        assert result == expected_data
