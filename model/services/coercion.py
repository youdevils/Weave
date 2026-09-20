from model.models.attribute_definition import AttributeDefinition


def coerce_attribute_value(
    data_type,
    raw_value,
):
    """
    Coerce a raw form value into a Python value suitable for storage in
    an Object/Relationship's `attributes` JSON blob, following the same
    per-data-type conventions as
    object_type_editor.py's _coerce_default_value.

    Raises ValueError when the text cannot be read as `data_type`. Whether
    a value is *acceptable* (choices, ranges, required, ...) is never
    decided here; that stays with model.services.validation.
    """

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()

    if raw_value in (None, ""):
        return None

    if data_type == AttributeDefinition.DataType.NUMBER:

        try:

            if "." in str(raw_value):
                return float(raw_value)

            return int(raw_value)

        except (TypeError, ValueError):
            raise ValueError("Value must be a number.")

    if data_type == AttributeDefinition.DataType.BOOLEAN:

        value = str(raw_value).strip().lower()

        if value in {"true", "1", "yes", "on"}:
            return True

        if value in {"false", "0", "no", "off"}:
            return False

        raise ValueError("Value must be true or false.")

    return raw_value
