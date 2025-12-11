from bson import ObjectId
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    """Custom ObjectId compatible with Pydantic v2."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type, handler: GetCoreSchemaHandler
    ):
        def validate(value):
            if isinstance(value, ObjectId):
                return value
            if ObjectId.is_valid(value):
                return ObjectId(value)
            raise ValueError("Invalid ObjectId")

        return core_schema.no_info_after_validator_function(
            validate,
            core_schema.union_schema(
                [core_schema.is_instance_schema(ObjectId), core_schema.str_schema()]
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema_obj, handler: GetJsonSchemaHandler
    ):
        json_schema = handler(core_schema_obj)
        json_schema.update(type="string")
        return json_schema


