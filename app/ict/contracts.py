"""Payload JSON da fronteira HTTP: não presume o formato de uma zona."""

type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]
