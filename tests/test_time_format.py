from time_format import format_hour, format_range


def test_hours_use_the_12_hour_clock():
    assert format_hour(6) == "6:00 a. m."
    assert format_hour(11) == "11:00 a. m."
    assert format_hour(12) == "12:00 p. m."
    assert format_hour(18) == "6:00 p. m."
    assert format_hour(22) == "10:00 p. m."
    assert format_hour(0) == "12:00 a. m."


def test_ranges():
    assert format_range(18, 22) == "6:00 p. m. a 10:00 p. m."


def test_api_messages_use_am_pm(client):
    r = client.post("/availability", json={"profesor_id": 1, "dia_semana": "Lunes", "hora_inicio": "20:00:00", "hora_fin": "23:00:00"})
    assert r.status_code == 422 and "10:00 p. m." in r.json()["detail"]
