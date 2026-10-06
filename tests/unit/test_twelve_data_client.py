from unittest.mock import Mock, call

from financial_data_platform.providers.twelve_data.client import (
    TwelveDataClient,
    TwelveDataClientError,
)

import pytest

import requests


def test_fetch_daily_time_series_returns_provider_payload():
    expected_payload = {
        "meta": {
            "symbol": "AAPL",
            "interval": "1day",
        },
        "values": [
            {
                "datetime": "2026-09-25",
                "open": "100.00",
                "high": "105.00",
                "low": "99.00",
                "close": "104.00",
                "volume": "123456",
            }
        ],
        "status": "ok",
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = expected_payload

    mock_session = Mock()
    mock_session.get.return_value = mock_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
    )

    payload = client.fetch_daily_time_series("AAPL")

    assert payload == expected_payload


def test_fetch_daily_time_series_sends_expected_request():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.return_value = mock_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
    )

    client.fetch_daily_time_series("AAPL")

    mock_session.get.assert_called_once_with(
        TwelveDataClient.BASE_URL,
        params={
            "symbol": "AAPL",
            "interval": "1day",
            "apikey": "test-api-key",
        },
        timeout=10,
    )


def test_client_rejects_empty_api_key():
    try:
        TwelveDataClient(api_key="")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")



def test_fetch_daily_time_series_rejects_non_retryable_client_error():
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    mock_session = Mock()
    mock_session.get.return_value = mock_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
    )

    with pytest.raises(
        TwelveDataClientError,
        match="HTTP 400",
    ):
        client.fetch_daily_time_series("AAPL")

    assert mock_session.get.call_count == 1


def test_fetch_daily_time_series_retries_rate_limit_response():
    rate_limited_response = Mock()
    rate_limited_response.status_code = 429

    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.side_effect = [
        rate_limited_response,
        successful_response,
    ]

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        sleep=Mock(),
    )

    payload = client.fetch_daily_time_series("AAPL")

    assert payload["status"] == "ok"
    assert mock_session.get.call_count == 2


def test_fetch_daily_time_series_stops_after_rate_limit_retries():
    rate_limited_response = Mock()
    rate_limited_response.status_code = 429

    mock_session = Mock()
    mock_session.get.return_value = rate_limited_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        max_retries=2,
        sleep=Mock(),
    )

    with pytest.raises(
        TwelveDataClientError,
        match="after retries with HTTP 429",
    ):
        client.fetch_daily_time_series("AAPL")

    assert mock_session.get.call_count == 3


def test_client_rejects_negative_max_retries():
    with pytest.raises(
        ValueError,
        match="max_retries must not be negative",
    ):
        TwelveDataClient(
            api_key="test-api-key",
            max_retries=-1,
        )


def test_fetch_daily_time_series_retries_server_error():
    server_error_response = Mock()
    server_error_response.status_code = 503

    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.side_effect = [
        server_error_response,
        successful_response,
    ]

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        sleep=Mock(),
    )

    payload = client.fetch_daily_time_series("AAPL")

    assert payload["status"] == "ok"
    assert mock_session.get.call_count == 2


def test_fetch_daily_time_series_stops_after_server_error_retries():
    server_error_response = Mock()
    server_error_response.status_code = 503

    mock_session = Mock()
    mock_session.get.return_value = server_error_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        max_retries=2,
        sleep=Mock(),
    )

    with pytest.raises(
        TwelveDataClientError,
        match="after retries with HTTP 503",
    ):
        client.fetch_daily_time_series("AAPL")

    assert mock_session.get.call_count == 3


def test_fetch_daily_time_series_retries_timeout():
    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.side_effect = [
        requests.Timeout("request timed out"),
        successful_response,
    ]

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        sleep=Mock(),
    )

    payload = client.fetch_daily_time_series("AAPL")

    assert payload["status"] == "ok"
    assert mock_session.get.call_count == 2


def test_fetch_daily_time_series_stops_after_timeout_retries():
    mock_session = Mock()
    mock_session.get.side_effect = requests.Timeout("request timed out")

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        max_retries=2,
        sleep=Mock(),
    )

    with pytest.raises(
        TwelveDataClientError,
        match="after network retries",
    ):
        client.fetch_daily_time_series("AAPL")

    assert mock_session.get.call_count == 3


def test_fetch_daily_time_series_retries_connection_error():
    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.side_effect = [
        requests.ConnectionError("connection failed"),
        successful_response,
    ]

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        sleep=Mock(),
    )

    payload = client.fetch_daily_time_series("AAPL")

    assert payload["status"] == "ok"
    assert mock_session.get.call_count == 2


def test_fetch_daily_time_series_rejects_provider_error_payload():
    error_payload = {
        "status": "error",
        "code": 400,
        "message": "Invalid symbol",
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = error_payload

    mock_session = Mock()
    mock_session.get.return_value = mock_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
    )

    with pytest.raises(
        TwelveDataClientError,
        match="provider returned an error",
    ):
        client.fetch_daily_time_series("INVALID")



def test_fetch_daily_time_series_rejects_malformed_json():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    mock_session = Mock()
    mock_session.get.return_value = mock_response

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
    )

    with pytest.raises(
        TwelveDataClientError,
        match="invalid JSON",
    ):
        client.fetch_daily_time_series("AAPL")



def test_fetch_daily_time_series_waits_between_retries():
    rate_limited_response = Mock()
    rate_limited_response.status_code = 429

    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.side_effect = [
        rate_limited_response,
        successful_response,
    ]

    mock_sleep = Mock()

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        sleep=mock_sleep,
    )

    client.fetch_daily_time_series("AAPL")

    mock_sleep.assert_called_once_with(1.0)


def test_fetch_daily_time_series_uses_exponential_backoff():
    rate_limited_response = Mock()
    rate_limited_response.status_code = 429

    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    mock_session = Mock()
    mock_session.get.side_effect = [
        rate_limited_response,
        rate_limited_response,
        successful_response,
    ]

    mock_sleep = Mock()

    client = TwelveDataClient(
        api_key="test-api-key",
        session=mock_session,
        max_retries=2,
        sleep=mock_sleep,
    )

    client.fetch_daily_time_series("AAPL")

    assert mock_sleep.call_args_list == [
        call(1),
        call(2),
    ]
